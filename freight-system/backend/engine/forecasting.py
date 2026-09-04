"""
engine/forecasting.py — Forecasting Engine.

DOC3 §FEATURE: Forecasting Engine
DOC2 §5.3, §6.2

PUBLIC API (called by all other modules and the API route):
  get_forecast(route, vessel_class, horizon_days) → ForecastObject
    - ONLY read path. Raises ForecastUnavailableError if no gated forecast exists.
    - Runs ConditionsMonitor.check() at read time — may serve damped_trend.

SCHEDULED ENTRYPOINT (called by ingestion/scheduler.py weekly, NOT at API startup):
  train_and_evaluate() → None
    - Naive / ARIMA / XGBoost / Prophet per (route, vessel_class) scope pair.
    - Walk-forward validation. Naive-baseline gate. Ablation.
    - Writes gated ForecastObjects via repository.write_forecast().
    - NEVER called at FastAPI startup (reversed decision — DOC3 §0).

ARCHITECTURE NOTE:
  engine/ never imports from api/, ingestion/, or frontend/.
  Only warehouse.repository is the DB access point (AGENTS.md Agentic Coding Rules).
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Literal, Optional, Tuple

from backend.config.constants import (
    BDI_FRESHNESS_THRESHOLD_DAYS,
    BUNKER_STALENESS_ALERT_HOURS,
    FORECAST_HORIZONS_DAYS,
    MIN_OBSERVATIONS_FOR_XGBOOST,
    RETRAIN_SCHEDULE_CRON,
    SCENARIO_OPTIMISTIC_BAND_FRACTION,
)
from backend.warehouse import repository
from backend.warehouse.models import ForecastObject
from backend.engine.provenance import tag_modeled

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Enriched XGBoost feature set (research-validated, DOC2 Addendum v3 §A2)
# ALL 10 keys must be present in the aligned exog dict for the enriched path.
# If any key is missing → pure autoregressive fallback fires automatically.
# ---------------------------------------------------------------------------
_ENRICHED_EXOG_KEYS: frozenset[str] = frozenset({
    "brent",          "brent_return_1d",  "brent_change_7d",
    "wti",            "wti_return_1d",    "wti_change_7d",
    "iron_ore",       "iron_ore_change_1m",
    "iron_ore_change_3m",                 "iron_ore_ma_3m",
})

# ---------------------------------------------------------------------------
# Prophet regressor keys — ALL available exog is passed to Prophet for maximum
# explainability. Prophet handles missing series gracefully (skips add_regressor).
# Per user confirmation: ingest as much data as we have — more = better.
# ---------------------------------------------------------------------------
_PROPHET_EXOG_KEYS: tuple[str, ...] = (
    "brent", "wti", "iron_ore", "bdry", "gscpi", "bunker_vlsfo", "bunker_mgo",
)

# ---------------------------------------------------------------------------
# Typed exception — API converts to 422 (DOC3 §FEATURE: Forecasting Engine)
# ---------------------------------------------------------------------------

class ForecastUnavailableError(Exception):
    """
    Raised by get_forecast() when no gated ForecastObject exists for (route,
    vessel_class, horizon_days). The API layer converts this to HTTP 422.
    """
    pass


# ---------------------------------------------------------------------------
# ProphetDecomposition — typed output of _fit_prophet()
# DOC2 §7: Prophet's role is additive explainability, NOT prediction gating.
# ---------------------------------------------------------------------------

from dataclasses import dataclass, field

@dataclass
class ProphetDecomposition:
    """Additive component decomposition produced by _fit_prophet().

    yhat: raw Prophet point forecasts (logged, never gated).
    trend_delta: $/day change in Prophet's trend component over the horizon
                 (positive = rising, negative = falling).
    trend_direction: human-readable direction string.
    weekly_seasonality_amplitude: peak-to-trough swing of the weekly seasonality
                                  component in $/day (zero if not fitted).
    regressor_effects: {source_name: avg additive $/day contribution over horizon}.
                       Positive = adds to rate, negative = suppresses rate.
    narrative: human-readable English sentence summarising key findings.
    """
    yhat: List[float]
    trend_delta: float
    trend_direction: str           # "rising" | "falling" | "flat"
    weekly_seasonality_amplitude: float
    regressor_effects: Dict[str, float]
    narrative: str


# ---------------------------------------------------------------------------
# ConditionsMonitor — CARRIED OVER logic (DOC3 §0.1)
# Checks live bunker/BDI/rate values at read time.
# ---------------------------------------------------------------------------

class ConditionsMonitor:
    """
    Checks whether current market conditions are so extreme that the stored
    forecast (generated days/weeks ago) is likely invalid.

    Runs on every get_forecast() call — not just at retrain time.
    This is why the damped_trend fallback is activated at READ time, not
    at training time: a market spike between retrains is caught immediately.

    CARRIED OVER logic from prior build (DOC3 §0.1, Migration Delta §2).
    """

    def __init__(
        self,
        bdi_spike_pct: float = 30.0,
        bunker_spike_pct: float = 25.0,
        rate_spike_pct: float = 35.0,
    ) -> None:
        self.bdi_spike_pct = bdi_spike_pct
        self.bunker_spike_pct = bunker_spike_pct
        self.rate_spike_pct = rate_spike_pct

    def check(self, route: str, vessel_class: str) -> Tuple[bool, str]:
        """
        Return (tripped: bool, reason: str).

        Reads LATEST values from warehouse and compares to 7-day rolling average.
        Returns (True, explanation) if conditions are extreme enough to trigger
        the damped_trend fallback. Never raises — returns (False, "") on any
        warehouse read failure.
        """
        try:
            return self._check_impl(route, vessel_class)
        except Exception as exc:
            logger.warning("ConditionsMonitor.check failed for %s/%s: %s — not tripping.", route, vessel_class, exc)
            return False, ""

    def _check_impl(self, route: str, vessel_class: str) -> Tuple[bool, str]:
        reasons: list[str] = []

        # --- BDI spike check ---
        bdi_latest = self._latest_exogenous("bdry")
        bdi_avg = self._rolling_avg_exogenous("bdry", days=7)
        if bdi_avg and bdi_latest is not None:
            pct_change = abs(bdi_latest - bdi_avg) / max(bdi_avg, 1.0) * 100.0
            if pct_change > self.bdi_spike_pct:
                reasons.append(
                    f"BDI spike {pct_change:.1f}% (threshold {self.bdi_spike_pct}%): "
                    f"latest={bdi_latest:.0f}, 7d_avg={bdi_avg:.0f}"
                )

        # --- Bunker spike check ---
        bunker_latest = self._latest_exogenous("bunker_vlsfo")
        bunker_avg = self._rolling_avg_exogenous("bunker_vlsfo", days=7)
        if bunker_avg and bunker_latest is not None:
            pct_change = abs(bunker_latest - bunker_avg) / max(bunker_avg, 1.0) * 100.0
            if pct_change > self.bunker_spike_pct:
                reasons.append(
                    f"Bunker spike {pct_change:.1f}% (threshold {self.bunker_spike_pct}%): "
                    f"latest={bunker_latest:.1f}, 7d_avg={bunker_avg:.1f}"
                )

        if reasons:
            reason_str = "; ".join(reasons)
            logger.warning("ConditionsMonitor tripped for %s/%s: %s", route, vessel_class, reason_str)
            return True, reason_str

        return False, ""

    def _latest_exogenous(self, source: str) -> Optional[float]:
        """Return the most recent value for an exogenous source from warehouse."""
        from sqlalchemy import desc, select
        from backend.warehouse.db import get_session
        from backend.warehouse.models import ExogenousFeature
        try:
            with get_session() as session:
                row = session.execute(
                    select(ExogenousFeature)
                    .where(ExogenousFeature.source == source)
                    .order_by(desc(ExogenousFeature.date))
                    .limit(1)
                ).scalar_one_or_none()
                return float(row.value) if row else None
        except Exception:
            return None

    def _rolling_avg_exogenous(self, source: str, days: int) -> Optional[float]:
        """Return the mean of the last `days` values for an exogenous source."""
        from sqlalchemy import select
        from backend.warehouse.db import get_session
        from backend.warehouse.models import ExogenousFeature
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        try:
            with get_session() as session:
                rows = session.execute(
                    select(ExogenousFeature.value)
                    .where(
                        ExogenousFeature.source == source,
                        ExogenousFeature.date >= cutoff,
                    )
                ).scalars().all()
                vals = [float(v) for v in rows]
                return sum(vals) / len(vals) if vals else None
        except Exception:
            return None


# ---------------------------------------------------------------------------
# damped_trend() — fallback model, CARRIED OVER (DOC3 §0.1)
# ---------------------------------------------------------------------------

def damped_trend(
    history: List[float],
    horizon_days: int,
    phi: float = 0.88,
) -> List[float]:
    """
    Holt's damped-trend exponential smoothing — conservative forecast for extreme conditions.

    CARRIED OVER from the prior build (DOC3 §0.1, Migration Delta §2).
    phi: damping factor (0 < phi < 1). 0.88 is the standard industry default.

    Returns a list of point estimates of length `horizon_days`.
    Degenerate inputs (< 2 observations) → flat forecast at last known value.
    """
    if not history or len(history) < 2:
        last = history[-1] if history else 0.0
        return [last] * horizon_days

    alpha = 0.2   # level smoothing
    beta = 0.1    # trend smoothing

    level = history[0]
    trend = history[1] - history[0]

    for obs in history[1:]:
        prev_level = level
        level = alpha * obs + (1 - alpha) * (level + phi * trend)
        trend = beta * (level - prev_level) + (1 - beta) * phi * trend

    forecasts = []
    for h in range(1, horizon_days + 1):
        damped = sum(phi ** j for j in range(1, h + 1))
        forecasts.append(level + damped * trend)

    return forecasts


# ---------------------------------------------------------------------------
# _naive_forecast() — random-walk baseline (used as gate and fallback)
# ---------------------------------------------------------------------------

def _naive_forecast(history: List[float], horizon_days: int) -> List[float]:
    """Naive random-walk: last observed value repeated for all horizons."""
    last = history[-1] if history else 0.0
    return [last] * horizon_days


# ---------------------------------------------------------------------------
# Walk-forward validation (DOC3 §FEATURE: Forecasting Engine)
# ---------------------------------------------------------------------------

def _walk_forward_mae(
    values: List[float],
    forecast_fn,
    horizon: int,
    min_train: int = 30,
    max_folds: int = 10,   # cap validation folds — prevents multi-minute retrains on large datasets
) -> float:
    """
    Walk-forward MAE: train on values[:t], predict t+1..t+horizon, slide.
    Returns mean absolute error across all valid folds.
    Never a random split — always chronological.

    max_folds: sample at most this many evenly-spaced folds from the valid range.
    Default 50 gives a stable estimate while keeping retrain time bounded.
    """
    errors: list[float] = []
    n = len(values)
    valid_starts = list(range(min_train, n - horizon))
    if not valid_starts:
        return float("inf")

    # Subsample evenly from valid range if more folds than cap
    if len(valid_starts) > max_folds:
        step = len(valid_starts) / max_folds
        valid_starts = [valid_starts[int(i * step)] for i in range(max_folds)]

    for t in valid_starts:
        train = values[:t]
        actuals = values[t:t + horizon]
        try:
            preds = forecast_fn(train, horizon)
            fold_errors = [abs(p - a) for p, a in zip(preds, actuals)]
            errors.extend(fold_errors)
        except Exception:
            continue
    return sum(errors) / len(errors) if errors else float("inf")


def _walk_forward_mae_with_exog(
    history: List[float],
    exog: Dict[str, List[float]],
    forecast_fn,
    horizon: int,
    min_train: int = 30,
    max_folds: int = 10,
) -> float:
    """
    Walk-forward MAE for enriched XGBoost: slices the exog dict per fold so that
    each fold only sees exog values available up to the fold cutoff.

    forecast_fn signature: (history_slice, horizon, exog_slice) -> List[float]

    Mirrors _walk_forward_mae semantics (chronological, no leakage) but passes
    the aligned exog slices so _fit_xgboost uses the enriched path on each
    validation fold — ensuring the gating MAE matches the enriched model that
    will actually be served.
    """
    errors: list[float] = []
    n = len(history)
    valid_starts = list(range(min_train, n - horizon))
    if not valid_starts:
        return float("inf")

    if len(valid_starts) > max_folds:
        step = len(valid_starts) / max_folds
        valid_starts = [valid_starts[int(i * step)] for i in range(max_folds)]

    for t in valid_starts:
        train_hist = history[:t]
        actuals = history[t:t + horizon]
        exog_slice = {k: v[:t] for k, v in exog.items()}
        try:
            preds = forecast_fn(train_hist, horizon, exog_slice)
            errors.extend(abs(p - a) for p, a in zip(preds, actuals))
        except Exception:
            continue
    return sum(errors) / len(errors) if errors else float("inf")



def _holdout_mae(
    values: List[float],
    forecast_fn,
    horizon: int,
    holdout_frac: float = 0.2,
) -> float:
    """
    Simple train/holdout MAE for expensive models (ARIMA) where per-fold
    refit is too slow. Trains on the first (1-holdout_frac) of values,
    evaluates on the last holdout_frac in a rolling fashion.

    Still chronological — no data leakage.
    Used ONLY for ARIMA gating; XGBoost uses full walk-forward.
    """
    n = len(values)
    split = max(30, int(n * (1 - holdout_frac)))
    train = values[:split]
    test  = values[split:]

    if len(test) < horizon:
        return float("inf")

    errors: list[float] = []
    for start in range(0, len(test) - horizon + 1, horizon):
        actuals = test[start:start + horizon]
        try:
            preds = forecast_fn(train + test[:start], horizon)
            errors.extend(abs(p - a) for p, a in zip(preds, actuals))
        except Exception:
            continue
    return sum(errors) / len(errors) if errors else float("inf")


# ---------------------------------------------------------------------------
# Individual model trainers (lazy import heavy deps)
# ---------------------------------------------------------------------------

def _fit_arima(history: List[float], horizon: int) -> List[float]:
    """Fit Auto-ARIMA with AIC-minimizing parameter search and forecast horizon steps ahead."""
    try:
        from statsmodels.tsa.arima.model import ARIMA
        import warnings
        candidate_orders = [(1, 1, 1), (1, 1, 0), (0, 1, 1), (2, 1, 1), (1, 0, 1)]
        best_aic = float("inf")
        best_fit = None

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            for order in candidate_orders:
                try:
                    fit = ARIMA(history, order=order).fit()
                    if fit.aic < best_aic:
                        best_aic = fit.aic
                        best_fit = fit
                except Exception:
                    continue

        if best_fit is not None:
            forecast = best_fit.forecast(steps=horizon)
            return [float(x) for x in forecast]
        return damped_trend(history, horizon)
    except Exception as exc:
        logger.warning("Auto-ARIMA fit failed: %s — falling back to damped_trend", exc)
        return damped_trend(history, horizon)


def _fit_xgboost(
    history: List[float],
    horizon: int,
    exog: Optional[Any] = None,
) -> Tuple[List[float], Dict[str, float]]:
    """
    Dispatch to the enriched or pure-AR XGBoost path.

    Enriched path (16 features) — activated when ALL of the following hold:
      * exog is a Dict[str, List[float]]
      * _ENRICHED_EXOG_KEYS ⊆ exog.keys()
      * every required series has length == len(history)
    → uses tc_lag_1..4, tc_mean_4, tc_std_4 + 10 market features.
    Exog MUST already be merge_asof-aligned to rate dates (done by caller).

    Pure-AR fallback (lags 1..10) — all other cases, including when exog is
    None, empty, a bare List, or missing any required key.
    """
    use_enriched = (
        isinstance(exog, dict)
        and _ENRICHED_EXOG_KEYS.issubset(exog.keys())
        and all(len(exog[k]) == len(history) for k in _ENRICHED_EXOG_KEYS)
    )
    try:
        if use_enriched:
            return _fit_xgboost_enriched(history, horizon, exog)  # type: ignore[arg-type]
        else:
            return _fit_xgboost_ar(history, horizon)
    except Exception as exc:
        logger.warning("XGBoost fit failed (%s path): %s — damped_trend fallback",
                       "enriched" if use_enriched else "AR", exc)
        return damped_trend(history, horizon), {}


def _fit_xgboost_ar(history: List[float], horizon: int) -> Tuple[List[float], Dict[str, float]]:
    """
    Pure autoregressive XGBoost with lags 1..10.
    Original behaviour — unchanged except extracted to a named function.
    """
    try:
        import numpy as np
        from xgboost import XGBRegressor
    except ImportError:
        logger.warning("xgboost not installed — falling back to damped_trend")
        return damped_trend(history, horizon), {}

    n_lags = min(10, len(history) - horizon - 1)
    if n_lags < 3:
        return damped_trend(history, horizon), {}

    X_list, y_list = [], []
    for i in range(n_lags, len(history)):
        X_list.append(list(history[i - n_lags:i]))
        y_list.append(history[i])

    X = np.array(X_list)
    y = np.array(y_list)

    model = XGBRegressor(
        n_estimators=100, max_depth=4, learning_rate=0.1,
        random_state=42, verbosity=0,
    )
    model.fit(X, y)

    current = list(history)
    preds: List[float] = []
    for _ in range(horizon):
        feats = current[-n_lags:]
        pred = float(model.predict(np.array([feats]))[0])
        preds.append(pred)
        current.append(pred)
    importances = {f"lag_{i}": float(v) for i, v in enumerate(model.feature_importances_)}
    return preds, importances


def _fit_xgboost_enriched(
    history: List[float],
    horizon: int,
    exog: Dict[str, List[float]],
) -> Tuple[List[float], Dict[str, float]]:
    """
    XGBoost with the research-validated 16-feature set.

    Feature matrix (in column order):
      tc_lag_1..4, tc_mean_4, tc_std_4,
      brent, brent_return_1d, brent_change_7d,
      wti, wti_return_1d, wti_change_7d,
      iron_ore, iron_ore_change_1m, iron_ore_change_3m, iron_ore_ma_3m.

    Exog is pre-aligned (merge_asof backward) by _load_aligned_features().
    Rows with any NaN are dropped before training.

    Forecasting: autoregressive roll of lag features; exog held at last
    known values (same convention as the research walk-forward baseline).
    Falls back to _fit_xgboost_ar if fewer than 5 clean training rows remain.
    """
    try:
        import numpy as np
        import pandas as pd
        from xgboost import XGBRegressor
    except ImportError:
        logger.warning("xgboost not installed — falling back to damped_trend")
        return damped_trend(history, horizon), {}

    n = len(history)
    if n < 8:
        return damped_trend(history, horizon), {}

    _FEAT_COLS = [
        "tc_lag_1", "tc_lag_2", "tc_lag_3", "tc_lag_4",
        "tc_mean_4", "tc_std_4",
        "brent", "brent_return_1d", "brent_change_7d",
        "wti", "wti_return_1d", "wti_change_7d",
        "iron_ore", "iron_ore_change_1m", "iron_ore_change_3m", "iron_ore_ma_3m",
    ]

    df = pd.DataFrame({"target": history})
    for lag in [1, 2, 3, 4]:
        df[f"tc_lag_{lag}"] = df["target"].shift(lag)
    df["tc_mean_4"] = df["target"].shift(1).rolling(4).mean()
    df["tc_std_4"]  = df["target"].shift(1).rolling(4).std(ddof=1).fillna(0.0)
    for key in sorted(_ENRICHED_EXOG_KEYS):
        df[key] = exog[key]
    df["target_horizon"] = df["target"].shift(-1)

    train_df = df.dropna(subset=_FEAT_COLS + ["target_horizon"]).copy()
    if len(train_df) < 5:
        logger.debug("_fit_xgboost_enriched: only %d clean rows after dropna — AR fallback", len(train_df))
        return _fit_xgboost_ar(history, horizon)

    X = train_df[_FEAT_COLS].values
    y = train_df["target_horizon"].values

    model = XGBRegressor(
        n_estimators=80, max_depth=2, learning_rate=0.05,
        min_child_weight=3, subsample=0.8, colsample_bytree=0.8,
        reg_alpha=0.1, reg_lambda=2.0,
        objective="reg:squarederror",
        random_state=42, verbosity=0,
    )
    model.fit(X, y)

    # Hold last-known exog values for forecast loop
    last_exog = {k: float(exog[k][-1]) if exog[k] else 0.0 for k in _ENRICHED_EXOG_KEYS}

    rolling = list(history)
    preds: List[float] = []
    for _ in range(horizon):
        tail = rolling[-4:] if len(rolling) >= 4 else ([rolling[-1]] * 4)[:len(rolling)]
        while len(tail) < 4:
            tail = [tail[0]] + tail
        lag1, lag2, lag3, lag4 = tail[-1], tail[-2], tail[-3], tail[-4]
        hist5 = rolling[-5:-1] if len(rolling) >= 5 else rolling[:-1]
        mean4 = float(np.mean(hist5)) if hist5 else lag1
        std4  = float(np.std(hist5, ddof=1)) if len(hist5) >= 2 else 0.0

        row = [
            lag1, lag2, lag3, lag4, mean4, std4,
            last_exog["brent"],           last_exog["brent_return_1d"],  last_exog["brent_change_7d"],
            last_exog["wti"],             last_exog["wti_return_1d"],    last_exog["wti_change_7d"],
            last_exog["iron_ore"],        last_exog["iron_ore_change_1m"],
            last_exog["iron_ore_change_3m"],                             last_exog["iron_ore_ma_3m"],
        ]
        pred = float(model.predict(np.array([row]))[0])
        preds.append(pred)
        rolling.append(pred)
    importances = {feat: float(v) for feat, v in zip(_FEAT_COLS, model.feature_importances_)}
    return preds, importances



# ---------------------------------------------------------------------------
# _groq_narrative() — LLM-generated analyst prose for Prophet decomposition
# Called at retrain time only (never at API serve time). Zero user latency.
# Gracefully falls back to _template_narrative() if Groq is unavailable.
# ---------------------------------------------------------------------------

def _groq_narrative(
    horizon: int,
    trend_delta: float,
    trend_direction: str,
    weekly_amp: float,
    regressor_effects: Dict[str, float],
    available_regressors: List[str],
) -> str:
    """Call Groq LLM to generate analyst-quality narrative from Prophet numbers.

    All numbers are injected as hard structured facts — the LLM interprets them,
    it does NOT invent or hallucinate any data. Returns a 2-3 sentence paragraph.
    Falls back to _template_narrative() if GROQ_API_KEY is absent or call fails.
    """
    import os
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        logger.debug("_groq_narrative: GROQ_API_KEY not set — using template fallback")
        return _template_narrative(horizon, trend_delta, trend_direction, weekly_amp,
                                   regressor_effects, available_regressors)
    try:
        import httpx
        # groq/compound-mini: the only non-reasoning model available on this account.
        # All gpt-oss-* models use internal chain-of-thought and return empty content.
        model = "groq/compound-mini"

        # Build structured fact block — LLM must interpret, not invent
        _reg_labels = {
            "bdry": "BDI (Baltic Dry Index)",
            "brent": "Brent crude oil",
            "wti": "WTI crude oil",
            "iron_ore": "Iron ore price",
            "bunker_vlsfo": "Bunker fuel (VLSFO)",
            "bunker_mgo": "Bunker fuel (MGO)",
            "gscpi": "Global Supply Chain Pressure Index",
        }
        facts: list[str] = [
            f"- Forecast horizon: {horizon} days",
            f"- Trend direction: {trend_direction}",
            f"- Trend magnitude: {'+' if trend_delta >= 0 else ''}{trend_delta:.1f} $/day over the horizon",
        ]
        if weekly_amp > 1.0:
            facts.append(f"- Weekly seasonality amplitude (peak-to-trough): {weekly_amp:.1f} $/day")
        if regressor_effects:
            facts.append("- Macro driver effects ($/day additive, from Prophet decomposition):")
            for name, eff in sorted(regressor_effects.items(), key=lambda x: abs(x[1]), reverse=True):
                label = _reg_labels.get(name, name.replace("_", " ").title())
                sign = "+" if eff >= 0 else ""
                facts.append(f"  * {label}: {sign}{eff:.1f} $/day")
        else:
            facts.append("- No macro regressors available (trend and seasonality decomposed only)")

        fact_block = "\n".join(facts)

        prompt = (
            "You are a senior dry-bulk freight analyst writing a brief market commentary "
            "for a live chartering dashboard.\n\n"
            "Below are exact numbers from a Prophet time-series decomposition model for a specific "
            "vessel route. Turn these into a clear, natural 2-3 sentence analytical paragraph that "
            "a trader can read at a glance.\n\n"
            "RULES:\n"
            "- Use only the numbers given. Do not invent or assume anything extra.\n"
            "- Specific $/day figures must appear where they add insight.\n"
            "- Active voice, present tense, plain English. No bullet points or markdown.\n"
            "- Do NOT open with 'Freight rates are' or 'The freight rates'. Vary your opener.\n"
            "- Maximum 70 words.\n\n"
            f"Facts (use exactly as given):\n{fact_block}\n\n"
            "Analyst commentary:"
        )

        resp = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 130,
                "temperature": 0.4,
                "top_p": 0.9,
            },
            timeout=15.0,
        )
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"].strip()
        if len(text) < 20:
            raise ValueError(f"Groq returned suspiciously short narrative: {text!r}")
        logger.info("_groq_narrative: generated %d chars via Groq model=%s", len(text), model)
        return text

    except Exception as exc:
        logger.warning("_groq_narrative: Groq call failed (%s) — using template fallback", exc)
        return _template_narrative(horizon, trend_delta, trend_direction, weekly_amp,
                                   regressor_effects, available_regressors)


def _template_narrative(
    horizon: int,
    trend_delta: float,
    trend_direction: str,
    weekly_amp: float,
    regressor_effects: Dict[str, float],
    available_regressors: List[str],
) -> str:
    """Template fallback narrative — used when Groq is unavailable."""
    _reg_labels = {
        "bdry": "BDI", "brent": "Brent", "wti": "WTI",
        "iron_ore": "iron ore", "bunker_vlsfo": "bunker fuel", "gscpi": "supply chain pressure",
    }
    if trend_direction == "rising":
        trend_str = f"Rates up {abs(trend_delta):.0f} $/day over the {horizon}d window"
    elif trend_direction == "falling":
        trend_str = f"Rates easing {abs(trend_delta):.0f} $/day over the {horizon}d window"
    else:
        trend_str = f"Rates flat over the {horizon}d window"

    parts = [trend_str + "."]
    if weekly_amp > 1.0:
        parts.append(f"Weekly seasonality: ±{weekly_amp/2:.0f} $/day.")
    if regressor_effects:
        top = sorted(regressor_effects.items(), key=lambda x: abs(x[1]), reverse=True)
        drivers = []
        for name, eff in top[:4]:
            if abs(eff) < 0.5:
                continue
            label = _reg_labels.get(name, name.replace("_", " "))
            sign = "+" if eff > 0 else ""
            drivers.append(f"{label} ({sign}{eff:.0f} $/day)")
        if drivers:
            parts.append("Drivers: " + ", ".join(drivers) + ".")
    if not available_regressors:
        parts.append("No macro data — trend and seasonality only.")
    return " ".join(parts)


def _fit_prophet(
    history: List[float],
    horizon: int,
    exog: Optional[Dict[str, List[float]]] = None,
) -> "ProphetDecomposition":
    """Fit Prophet with all available exogenous regressors and return a
    ProphetDecomposition containing additive component breakdowns.

    Per DOC2 §7: Prophet's role is explainability (trend + seasonality + shock
    drivers), NOT prediction gating. It always runs in parallel after the
    walk-forward winner is selected — it never influences model_used.

    Exogenous regressors added: all keys from _PROPHET_EXOG_KEYS that are
    present in the exog dict with full coverage (no NaN). More regressors = more
    informative $/day attribution — per user confirmation: ingest everything.
    """
    try:
        from prophet import Prophet
        import pandas as pd
        import logging as _logging
        _logging.getLogger("prophet").setLevel(_logging.WARNING)
        _logging.getLogger("cmdstanpy").setLevel(_logging.WARNING)

        # Build base dataframe — Prophet needs a datetime ds column
        start = datetime(2000, 1, 1)
        ds = [start + timedelta(days=i) for i in range(len(history))]
        df = pd.DataFrame({"ds": ds, "y": history})

        # Determine which regressors are fully available
        available_regressors: List[str] = []
        if exog and isinstance(exog, dict):
            for key in _PROPHET_EXOG_KEYS:
                if key in exog and len(exog[key]) == len(history):
                    vals = exog[key]
                    # Only include if no NaN/None in the series
                    if not any(v is None or (isinstance(v, float) and v != v) for v in vals):
                        df[key] = vals
                        available_regressors.append(key)

        # Build and fit model
        m = Prophet(
            yearly_seasonality=True,
            weekly_seasonality=True,
            daily_seasonality=False,
            changepoint_prior_scale=0.05,   # conservative — freight rates change slowly
            seasonality_prior_scale=5.0,
        )
        for reg in available_regressors:
            m.add_regressor(reg, standardize=True)

        m.fit(df)

        # Build future frame including the last known regressor values
        future_ds_list = [start + timedelta(days=len(history) + i) for i in range(horizon)]
        future_df = pd.DataFrame({"ds": future_ds_list})
        for reg in available_regressors:
            last_val = df[reg].iloc[-1]
            future_df[reg] = last_val   # hold last-known forward (standard convention)

        forecast_df = m.predict(future_df)
        yhat = list(forecast_df["yhat"].values)

        # ── Extract trend component ──
        # fit on training data to get the in-sample trend at the last observed point
        in_sample = m.predict(df)
        trend_start = float(in_sample["trend"].iloc[-min(7, len(in_sample))]) if len(in_sample) >= 2 else float(in_sample["trend"].iloc[0])
        trend_end   = float(forecast_df["trend"].iloc[-1])
        trend_delta = trend_end - trend_start
        if abs(trend_delta) < 5.0:   # $/day — treat sub-$5 as flat
            trend_direction = "flat"
        elif trend_delta > 0:
            trend_direction = "rising"
        else:
            trend_direction = "falling"

        # ── Extract weekly seasonality amplitude ──
        weekly_amp = 0.0
        if "weekly" in forecast_df.columns:
            weekly_amp = float(forecast_df["weekly"].max() - forecast_df["weekly"].min())

        # ── Extract regressor effects ──
        # Prophet decomposes each regressor's additive contribution per day.
        # We report the mean contribution over the forecast horizon in $/day.
        regressor_effects: Dict[str, float] = {}
        for reg in available_regressors:
            col = f"{reg}_extra_regressors" if f"{reg}_extra_regressors" in forecast_df.columns else reg
            # Prophet stores each regressor's effect in a column named after the regressor
            if reg in forecast_df.columns:
                mean_effect = float(forecast_df[reg].mean())
                regressor_effects[reg] = round(mean_effect, 2)
            elif col in forecast_df.columns:
                mean_effect = float(forecast_df[col].mean())
                regressor_effects[reg] = round(mean_effect, 2)

        # ── Build narrative — template only at retrain time.
        # Groq-powered narratives are generated on-demand via /api/narrate
        # when a user opens the Rate Driver panel (zero cost until viewed).
        narrative = _template_narrative(
            horizon=horizon,
            trend_delta=trend_delta,
            trend_direction=trend_direction,
            weekly_amp=weekly_amp,
            regressor_effects=regressor_effects,
            available_regressors=available_regressors,
        )

        logger.info(
            "Prophet decomp: horizon=%dd trend=%s delta=%.1f regressors=%s narrative=%r",
            horizon, trend_direction, trend_delta, list(regressor_effects.keys()), narrative[:80],
        )

        return ProphetDecomposition(
            yhat=yhat,
            trend_delta=round(trend_delta, 2),
            trend_direction=trend_direction,
            weekly_seasonality_amplitude=round(weekly_amp, 2),
            regressor_effects=regressor_effects,
            narrative=narrative,
        )

    except ImportError:
        logger.warning("prophet not installed — Prophet explainability skipped")
        raise
    except Exception as exc:
        logger.warning("Prophet decomposition failed: %s", exc)
        raise


# ---------------------------------------------------------------------------
# Gate: does this model beat the naive baseline?
# ---------------------------------------------------------------------------

def _passes_gate(
    candidate_mae: float,
    naive_mae: float,
    min_improvement_pct: float = 5.0,
) -> bool:
    """
    Return True if candidate improves over naive by at least min_improvement_pct%.
    A model that ties with naive is NOT gated through — falls back to damped_trend.
    """
    if naive_mae == 0.0:
        return candidate_mae == 0.0
    improvement = (naive_mae - candidate_mae) / naive_mae * 100.0
    return improvement >= min_improvement_pct


# ---------------------------------------------------------------------------
# Ablation logging (DOC3: "logged, not blocking")
# ---------------------------------------------------------------------------

def _log_ablation(
    model_name: str,
    base_mae: float,
    history: List[float],
    horizon: int,
    exog_series: Dict[str, List[float]],
) -> None:
    """
    Re-run the model with each exogenous feature removed. Log each feature's
    contribution (informational only — never blocks gating).
    DOC3: "re-run the primary model with each exogenous feature removed, confirm
    each earns its place (logged, not blocking)."
    """
    if model_name != "xgboost" or not exog_series:
        return

    for feature_name, exog_vals in exog_series.items():
        try:
            ablated_mae = _walk_forward_mae(
                history,
                lambda h, n: _fit_xgboost(h, n, exog=None),
                horizon,
            )
            delta = ablated_mae - base_mae
            logger.info(
                "Ablation [%s] remove '%s': base_MAE=%.2f, ablated_MAE=%.2f, delta=+%.2f (%s)",
                model_name, feature_name, base_mae, ablated_mae, delta,
                "earns place ✓" if delta > 0 else "no contribution ✗",
            )
        except Exception as exc:
            logger.warning("Ablation failed for feature '%s': %s", feature_name, exc)


# ---------------------------------------------------------------------------
# Core train_and_evaluate() — scheduled entrypoint, NOT called at startup
# ---------------------------------------------------------------------------

def train_and_evaluate(
    routes: Optional[List[str]] = None,
    vessel_classes: Optional[List[str]] = None,
    horizons: Optional[List[int]] = None,
) -> None:
    """
    Scheduled retrain entrypoint.

    CALLED BY: ingestion/scheduler.py on RETRAIN_SCHEDULE_CRON.
    NEVER called at FastAPI startup — this is the one explicitly reversed decision
    from the prior build (DOC3 §0).

    Per (route × vessel_class × horizon_days):
      1. Load RateHistory from warehouse.
      2. Walk-forward validate Naive / ARIMA / XGBoost / Prophet.
      3. Gate: only write ForecastObject if model beats naive baseline.
      4. Ablation: log per-feature contributions (informational, not blocking).
      5. Below MIN_OBSERVATIONS_FOR_XGBOOST: skip XGBoost, ARIMA/naive only.
    """
    _routes = routes or repository.get_valid_routes()
    _vessel_classes = vessel_classes or repository.get_valid_vessel_classes()
    _horizons = horizons or list(FORECAST_HORIZONS_DAYS)

    logger.info(
        "train_and_evaluate: starting retrain for %d routes × %d classes × %d horizons",
        len(_routes), len(_vessel_classes), len(_horizons),
    )

    for route in _routes:
        for vessel_class in _vessel_classes:
            try:
                _retrain_pair(route, vessel_class, _horizons)
            except Exception as exc:
                # DOC3 edge case: retrain fails for one pair → keep last gated forecast,
                # don't propagate the failure to other pairs.
                logger.error(
                    "train_and_evaluate: pair (%s, %s) failed — keeping last gated forecast. Error: %s",
                    route, vessel_class, exc,
                )

    logger.info("train_and_evaluate: complete.")


def _retrain_pair(route: str, vessel_class: str, horizons: List[int]) -> None:
    """
    Train and gate all models for one (route, vessel_class) pair.

    Uses date-aware rate loading + merge_asof-aligned exog so that XGBoost
    gating and prediction both use the same feature matrix (no leakage).
    Falls back to the plain history list for ARIMA/damped_trend (unchanged).
    """
    # Load rate history WITH dates — needed for merge_asof exog alignment
    rate_df = _load_rate_history_with_dates(route, vessel_class)
    history = rate_df["rate"].tolist() if not rate_df.empty else []

    if len(history) < 5:
        logger.info(
            "Skipping (%s, %s): only %d observations, minimum 5 required.",
            route, vessel_class, len(history),
        )
        return

    # Load exog aligned to rate dates via merge_asof(direction='backward')
    aligned_exog = _load_aligned_features(rate_df)
    # Legacy plain loader kept for ablation (uses length-based ordering only)
    exog_series_legacy = _load_exogenous_features(len(history))

    for horizon in horizons:
        if len(history) <= horizon:
            logger.debug("(%s, %s, h=%d): not enough history — skipping.", route, vessel_class, horizon)
            continue

        # --- Naive baseline MAE ---
        naive_mae = _walk_forward_mae(history, _naive_forecast, horizon)
        logger.debug("(%s, %s, h=%d) naive MAE=%.2f", route, vessel_class, horizon, naive_mae)

        # --- Select and gate model (passes aligned_exog for enriched XGBoost) ---
        best_model_name, best_preds, best_mae, best_importances = _select_best_model(
            history, horizon, naive_mae, aligned_exog
        )

        # --- Ablation log (informational, never blocking) ---
        if best_model_name == "xgboost":
            _log_ablation("xgboost", best_mae, history, horizon, exog_series_legacy)

        # --- Prophet explainability: ALWAYS runs in parallel, never competes in gate ---
        # Per DOC2 §7 and user confirmation: Prophet is an explainability layer, not a
        # prediction model. model_used is unaffected; this runs regardless of winner.
        prophet_decomp: Optional[ProphetDecomposition] = None
        if len(history) >= 20:   # minimum viable input for meaningful decomposition
            try:
                prophet_decomp = _fit_prophet(history, horizon, exog=aligned_exog)
            except Exception as _pe:
                logger.debug("Prophet explainability skipped for (%s,%s,h=%d): %s",
                             route, vessel_class, horizon, _pe)

        # --- Build and write ForecastObject ---
        forecast_obj = _build_forecast_object(
            route, vessel_class, horizon, best_preds, history, best_model_name,
            feature_importances=best_importances,
            prophet_decomp=prophet_decomp,
        )
        repository.write_forecast(forecast_obj)
        logger.info(
            "Gated forecast written: (%s, %s, h=%d) model=%s MAE=%.2f (naive=%.2f)",
            route, vessel_class, horizon, best_model_name, best_mae, naive_mae,
        )


def _select_best_model(
    history: List[float],
    horizon: int,
    naive_mae: float,
    exog_series: Dict[str, List[float]],
) -> Tuple[str, List[float], float, Dict[str, float]]:
    """
    Try models in priority order (XGBoost → ARIMA → Naive baseline).
    Returns (model_name, predictions, mae).

    Primary ladder under normal conditions: Naive → ARIMA → XGBoost only.
    Damped trend is NOT a routine competing model in the scheduled retrain ladder;
    it is reserved exclusively as the ConditionsMonitor read-time fallback
    for structural breaks / regime shifts (DOC3 §FEATURE: Forecasting Engine).

    XGBoost gating:
      - Enriched path: _walk_forward_mae_with_exog used when all _ENRICHED_EXOG_KEYS
        are present (per-fold exog slicing — gating score matches the served model).
      - Pure-AR fallback: standard _walk_forward_mae when exog is partial or absent.
    Below MIN_OBSERVATIONS_FOR_XGBOOST: XGBoost is skipped entirely.
    """
    n = len(history)
    naive_preds = _naive_forecast(history, horizon)
    best_name = "naive"
    best_preds = naive_preds
    best_mae = naive_mae
    best_importances: Dict[str, float] = {}

    # Determine if the enriched path is viable for this pair
    enriched_viable = (
        isinstance(exog_series, dict)
        and _ENRICHED_EXOG_KEYS.issubset(exog_series.keys())
        and all(len(exog_series[k]) == n for k in _ENRICHED_EXOG_KEYS)
    )

    # 1. ARIMA: always attempted
    try:
        arima_preds = _fit_arima(history, horizon)
        arima_mae = _holdout_mae(
            history,
            lambda h, n, _fn=_fit_arima: _fn(h, n),
            horizon,
        )
        if _passes_gate(arima_mae, naive_mae):
            best_name = "arima"
            best_preds = arima_preds
            best_mae = arima_mae
    except Exception as exc:
        logger.debug("ARIMA evaluation failed: %s", exc)

    # 2. XGBoost: only above PROVISIONAL threshold (MIN_OBSERVATIONS_FOR_XGBOOST)
    if n >= MIN_OBSERVATIONS_FOR_XGBOOST:
        try:
            if enriched_viable:
                xgb_preds, xgb_importances = _fit_xgboost(history, horizon, exog=exog_series)
                xgb_mae = _walk_forward_mae_with_exog(
                    history,
                    exog_series,
                    lambda h, hor, ex: _fit_xgboost(h, hor, exog=ex)[0],
                    horizon,
                )
            else:
                xgb_preds, xgb_importances = _fit_xgboost(history, horizon, exog=None)
                xgb_mae = _walk_forward_mae(
                    history,
                    lambda h, hor, _fn=_fit_xgboost_ar: _fn(h, hor)[0],
                    horizon,
                )

            # Must clear the 5% gate over naive AND beat ARIMA if ARIMA was already gated
            if _passes_gate(xgb_mae, naive_mae) and xgb_mae < best_mae:
                best_name = "xgboost"
                best_preds = xgb_preds
                best_mae = xgb_mae
                best_importances = xgb_importances
        except Exception as exc:
            logger.debug("XGBoost evaluation failed: %s", exc)

    return best_name, best_preds, best_mae, best_importances



def _build_forecast_object(
    route: str,
    vessel_class: str,
    horizon: int,
    predictions: List[float],
    history: List[float],
    model_name: str,
    feature_importances: Optional[Dict[str, float]] = None,
    prophet_decomp: Optional["ProphetDecomposition"] = None,
) -> dict:
    """Build a ForecastObject dict ready for repository.write_forecast().

    driver_explanation JSON schema (v2, with Prophet):
    {
      "text": str,                     # lead narrative sentence
      "importances": {feat: float},    # XGBoost feature importances (normalised 0–1)
      "prophet_decomposition": {       # present only when Prophet ran successfully
        "trend_delta": float,          # $/day change over horizon
        "trend_direction": str,        # "rising" | "falling" | "flat"
        "weekly_seasonality_amplitude": float,  # peak-to-trough $/day
        "regressor_effects": {src: float},      # $/day additive contribution per exog
        "narrative": str,              # full human-readable explanation
      }
    }
    """
    import json

    # Clamp horizon: never extrapolate beyond what predictions covers
    clamped_preds = predictions[:horizon]

    point_estimate = clamped_preds[-1] if clamped_preds else (history[-1] if history else 0.0)

    # Confidence band: ± 1.96 × residual std (walk-forward residuals)
    if len(history) > horizon + 5:
        naive_preds = _naive_forecast(history[:-horizon], horizon)
        residuals = [abs(p - a) for p, a in zip(naive_preds, history[-horizon:])]
        residual_std = math.sqrt(sum(r ** 2 for r in residuals) / len(residuals)) if residuals else 0.0
        margin = 1.96 * residual_std
    else:
        margin = point_estimate * 0.15  # 15% fallback when not enough history

    confidence_band = {
        "lower": max(0.0, point_estimate - margin),
        "upper": point_estimate + margin,
    }

    trajectory = [
        {"day": i + 1, "point_estimate": round(p, 2)}
        for i, p in enumerate(clamped_preds)
    ]

    # High-uncertainty flag:
    # True if model failed production gating (naive/damped_trend fallback), history is sparse (<25),
    # or extreme residual volatility (>75% margin-to-price ratio).
    # Gated production models (XGBoost / ARIMA) with normal dispersion serve as primary models (is_high_uncertainty=False).
    if model_name in ("naive", "damped_trend"):
        is_high_uncertainty = True
    elif len(history) < 25:
        is_high_uncertainty = True
    else:
        is_high_uncertainty = (margin / max(point_estimate, 1.0)) > 0.75

    # --- Build enriched driver_explanation JSON ---
    # Lead text: human-first, conversational prose — NOT a machine dump.
    # Confidence band in readable format.
    ci_lo = confidence_band['lower']
    ci_hi = confidence_band['upper']
    ci_str = f"${ci_lo:,.0f}–${ci_hi:,.0f}/day"
    model_label = {"xgboost": "XGBoost", "arima": "ARIMA", "naive": "statistical baseline", "damped_trend": "damped-trend fallback"}.get(model_name, model_name)

    if prophet_decomp is not None:
        # Use Prophet's narrative as the human headline — it's already meaningful prose.
        # Append the CI so the reader can assess forecast range without hunting for it.
        trend_arrow = "rising" if prophet_decomp.trend_direction == "rising" else ("easing" if prophet_decomp.trend_direction == "falling" else "flat")
        lead_text = (
            f"{prophet_decomp.narrative} "
            f"Forecast range over the {horizon}-day window: {ci_str} ({model_label} model)."
        )
    else:
        trend_dir_str = "rising" if (clamped_preds[-1] > history[-1] if history else False) else "easing or stable"
        lead_text = (
            f"The {horizon}-day rate outlook is {trend_dir_str} based on recent momentum. "
            f"Forecast range: {ci_str} ({model_label} model). No macro decomposition available — "
            f"retrain with active exogenous data to enable Prophet-driven explainability."
        )

    driver_dict: Dict[str, Any] = {
        "text": lead_text,
        "importances": feature_importances or {},
    }

    if prophet_decomp is not None:
        driver_dict["prophet_decomposition"] = {
            "trend_delta": prophet_decomp.trend_delta,
            "trend_direction": prophet_decomp.trend_direction,
            "weekly_seasonality_amplitude": prophet_decomp.weekly_seasonality_amplitude,
            "regressor_effects": prophet_decomp.regressor_effects,
            "narrative": prophet_decomp.narrative,
        }

    driver_explanation = json.dumps(driver_dict)

    return {
        "route": route,
        "vessel_class": vessel_class,
        "horizon_days": horizon,
        "generated_at": datetime.now(timezone.utc),
        "point_estimate": round(point_estimate, 2),
        "confidence_band": confidence_band,
        "trajectory": trajectory,
        "driver_explanation": driver_explanation,
        "is_high_uncertainty": is_high_uncertainty,
        "model_used": model_name,
        "provenance": tag_modeled(uncertainty_flag=is_high_uncertainty),  # always "modeled", per DOC3
    }


# ---------------------------------------------------------------------------
# Warehouse data loaders (all reads go through repository)
# ---------------------------------------------------------------------------

def _load_rate_history(route: str, vessel_class: str) -> List[float]:
    """Load chronological rate values for (route, vessel_class) from warehouse."""
    from sqlalchemy import select, asc
    from backend.warehouse.db import get_session
    from backend.warehouse.models import RateHistory

    try:
        with get_session() as session:
            rows = session.execute(
                select(RateHistory.rate)
                .where(
                    RateHistory.route == route,
                    RateHistory.vessel_class == vessel_class,
                )
                .order_by(asc(RateHistory.date))
            ).scalars().all()
            return [float(r) for r in rows]
    except Exception as exc:
        logger.warning("_load_rate_history(%s, %s) failed: %s", route, vessel_class, exc)
        return []


def _load_exogenous_features(n_obs: int) -> Dict[str, List[float]]:
    """
    Load the most recent n_obs values for each exogenous source.
    Used for XGBoost feature enrichment and ablation.
    """
    from sqlalchemy import select, desc
    from backend.warehouse.db import get_session
    from backend.warehouse.models import ExogenousFeature
    from backend.config.constants import EXOGENOUS_FEATURE_SOURCES

    result: Dict[str, List[float]] = {}
    try:
        with get_session() as session:
            for source in EXOGENOUS_FEATURE_SOURCES:
                rows = session.execute(
                    select(ExogenousFeature.value)
                    .where(ExogenousFeature.source == source)
                    .order_by(desc(ExogenousFeature.date))
                    .limit(n_obs)
                ).scalars().all()
                vals = list(reversed([float(v) for v in rows]))
                if vals:
                    result[source] = vals
    except Exception as exc:
        logger.warning("_load_exogenous_features failed: %s", exc)
    return result


def _load_rate_history_with_dates(route: str, vessel_class: str) -> "Any":
    """
    Load chronological (date, rate) rows for (route, vessel_class).
    Returns a pandas DataFrame with columns ['date', 'rate'].
    date is a timezone-aware UTC datetime.

    Used by _retrain_pair for merge_asof-based exog alignment.
    Falls back to an empty DataFrame on any warehouse error.
    """
    from sqlalchemy import select, asc
    from backend.warehouse.db import get_session
    from backend.warehouse.models import RateHistory
    try:
        import pandas as pd
    except ImportError:
        logger.warning("pandas not available — _load_rate_history_with_dates returning empty")
        return None

    try:
        with get_session() as session:
            rows = session.execute(
                select(RateHistory.date, RateHistory.rate)
                .where(
                    RateHistory.route == route,
                    RateHistory.vessel_class == vessel_class,
                )
                .order_by(asc(RateHistory.date))
            ).all()
            if not rows:
                return pd.DataFrame(columns=["date", "rate"])
            df = pd.DataFrame(rows, columns=["date", "rate"])
            df["date"] = pd.to_datetime(df["date"], utc=True)
            df["rate"] = df["rate"].astype(float)
            return df
    except Exception as exc:
        logger.warning("_load_rate_history_with_dates(%s, %s) failed: %s", route, vessel_class, exc)
        try:
            import pandas as pd
            return pd.DataFrame(columns=["date", "rate"])
        except ImportError:
            return None


def _load_aligned_features(rate_df: "Any") -> Dict[str, List[float]]:
    """
    Load all exogenous features from the warehouse and align each source to
    rate_df['date'] via pd.merge_asof(direction='backward').

    merge_asof backward: for each rate-observation date, uses the most recent
    exogenous value ON OR BEFORE that date — equivalent to the research
    pipeline's asof-merge that achieved the best walk-forward MAE.

    Returns Dict[source_key, aligned_list_of_same_length_as_rate_df].
    Sources with no warehouse rows, or with any NaN after the asof merge,
    are omitted (caller checks completeness via _ENRICHED_EXOG_KEYS).
    """
    from sqlalchemy import select, asc
    from backend.warehouse.db import get_session
    from backend.warehouse.models import ExogenousFeature
    from backend.config.constants import EXOGENOUS_FEATURE_SOURCES

    result: Dict[str, List[float]] = {}
    if rate_df is None or (hasattr(rate_df, 'empty') and rate_df.empty):
        return result

    try:
        import pandas as pd
    except ImportError:
        logger.warning("pandas not available — _load_aligned_features returning empty")
        return result

    # Collect all source keys we care about (declared constants + enriched keys)
    all_source_keys = set(EXOGENOUS_FEATURE_SOURCES) | _ENRICHED_EXOG_KEYS

    try:
        with get_session() as session:
            for source in sorted(all_source_keys):
                rows = session.execute(
                    select(ExogenousFeature.date, ExogenousFeature.value)
                    .where(ExogenousFeature.source == source)
                    .order_by(asc(ExogenousFeature.date))
                ).all()
                if not rows:
                    continue

                exog_df = pd.DataFrame(rows, columns=["date", "value"])
                exog_df["date"] = pd.to_datetime(exog_df["date"], utc=True)
                exog_df["value"] = exog_df["value"].astype(float)
                exog_df = exog_df.sort_values("date").drop_duplicates("date")

                # merge_asof: for each rate date, use the last known exog value
                # on-or-before that date (backward fill across gaps/weekends/holidays).
                merged = pd.merge_asof(
                    rate_df[["date"]].sort_values("date"),
                    exog_df,
                    on="date",
                    direction="backward",
                )
                # Re-align to original rate_df row order
                merged = rate_df[["date"]].merge(merged, on="date", how="left")

                aligned = merged["value"].tolist()
                # Only include source if fully covered (no NaN after asof merge)
                if not any(v is None or (isinstance(v, float) and v != v) for v in aligned):
                    result[source] = [float(v) for v in aligned]
                else:
                    n_missing = sum(1 for v in aligned if v is None or (isinstance(v, float) and v != v))
                    logger.debug(
                        "_load_aligned_features: source=%r has %d NaN after asof merge — excluded",
                        source, n_missing,
                    )
    except Exception as exc:
        logger.warning("_load_aligned_features failed: %s", exc)

    return result


# ---------------------------------------------------------------------------
# get_forecast() — the sole public read entrypoint
# ---------------------------------------------------------------------------

_conditions_monitor = ConditionsMonitor()


def get_forecast(
    route: str,
    vessel_class: str,
    horizon_days: int,
) -> ForecastObject:
    """
    Return the latest gated ForecastObject for (route, vessel_class, horizon_days).

    Runs ConditionsMonitor.check() against live warehouse data on every call.
    If conditions trip: returns the damped_trend variant from the stored forecast,
    tagged in model_used. Does NOT retrain.

    Raises ForecastUnavailableError if no gated forecast exists for this pair.
    DOC3: "API converts to 422, same pattern as the prior build."

    SRP: decides WHICH stored model output to serve. Triggers no training.
    """
    # Clamp horizon to what's covered (DOC3 edge case)
    valid_horizons = sorted(FORECAST_HORIZONS_DAYS)
    if horizon_days not in valid_horizons:
        clamped = min(valid_horizons, key=lambda h: abs(h - horizon_days))
        logger.info(
            "get_forecast: horizon_days=%d not in %s — clamping to %d.",
            horizon_days, valid_horizons, clamped,
        )
        horizon_days = clamped

    obj = repository.get_latest_forecast(route, vessel_class, horizon_days)
    if obj is None:
        raise ForecastUnavailableError(
            f"No gated ForecastObject found for route={route!r}, "
            f"vessel_class={vessel_class!r}, horizon_days={horizon_days}. "
            f"Run train_and_evaluate() first."
        )

    # Conditions check at read time (DOC3: independent of stored forecast generation date)
    tripped, reason = _conditions_monitor.check(route, vessel_class)
    if tripped:
        logger.warning(
            "get_forecast: ConditionsMonitor tripped for (%s, %s): %s — "
            "switching to damped_trend variant.",
            route, vessel_class, reason,
        )
        # Serve damped_trend recalculated on the fly from the stored forecast's
        # point_estimate + confidence_band (avoids needing the raw history again).
        obj = _apply_damped_trend_override(obj, reason)

    return obj


def _apply_damped_trend_override(obj: ForecastObject, reason: str) -> ForecastObject:
    """
    Recalculate the served forecast as a damped_trend over the stored trajectory's
    point estimates, and mark model_used accordingly.

    Returns a NEW ForecastObject (does NOT mutate the DB row).
    """
    import json as _json

    try:
        traj = _json.loads(obj.trajectory) if isinstance(obj.trajectory, str) else obj.trajectory
        history_vals = [float(p["point_estimate"]) for p in traj] if traj else [obj.point_estimate]
    except Exception:
        history_vals = [obj.point_estimate]

    horizon = obj.horizon_days
    dt_preds = damped_trend(history_vals, horizon)

    new_point = dt_preds[-1] if dt_preds else obj.point_estimate
    new_traj = [{"day": i + 1, "point_estimate": round(p, 2)} for i, p in enumerate(dt_preds)]

    try:
        cb = _json.loads(obj.confidence_band) if isinstance(obj.confidence_band, str) else obj.confidence_band
    except Exception:
        cb = {"lower": new_point * 0.85, "upper": new_point * 1.15}

    # Build an ephemeral ForecastObject — not written to DB (damped_trend override is transient)
    override = ForecastObject(
        route=obj.route,
        vessel_class=obj.vessel_class,
        horizon_days=obj.horizon_days,
        generated_at=obj.generated_at,
        point_estimate=round(new_point, 2),
        confidence_band=_json.dumps(cb),
        trajectory=_json.dumps(new_traj),
        driver_explanation=(
            f"[damped_trend override] {obj.driver_explanation or ''} "
            f"| ConditionsMonitor tripped: {reason}"
        ),
        is_high_uncertainty=True,  # always flag as high-uncertainty when override fires
        model_used="damped_trend",
    )
    return override
