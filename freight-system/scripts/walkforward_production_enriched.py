"""
scripts/walkforward_production_enriched.py
------------------------------------------
Re-runs the expanding-window walk-forward on the real 164-point drycargo_5tc_c5.csv
series and reports MAE / RMSE / MAPE for:
  Naive | Damped Trend | ARIMA | Enriched XGBoost (with oil/iron-ore features)

Run from freight-system/:
  python3 scripts/walkforward_production_enriched.py
"""
from __future__ import annotations

import math
import os
import sys
import warnings
from pathlib import Path
from typing import List, Dict

# ---------------------------------------------------------------------------
# Setup: make backend importable and silence noisy warnings
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
warnings.filterwarnings("ignore")

import pandas as pd
import numpy as np

# ---------------------------------------------------------------------------
# Load the real 5TC series
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).parent.parent.parent  # FrieghtCast/
C5_CSV = REPO_ROOT / "freight_optimization" / "data" / "raw" / "freight" / "drycargo_5tc_c5.csv"

if not C5_CSV.exists():
    sys.exit(f"ERROR: {C5_CSV} not found. Run from freight-system/ with freight_optimization sibling.")

df_rates = pd.read_csv(C5_CSV, parse_dates=["report_date"]).sort_values("report_date")
df_rates = df_rates.dropna(subset=["capesize_5tc_usd_per_day"]).reset_index(drop=True)
history = df_rates["capesize_5tc_usd_per_day"].tolist()
rate_dates = df_rates["report_date"]
print(f"\nRate series: {len(history)} observations  ({rate_dates.min().date()} → {rate_dates.max().date()})")

# ---------------------------------------------------------------------------
# Load and align exogenous features (Brent, WTI, Iron Ore)
# ---------------------------------------------------------------------------
MARKET_DIR = REPO_ROOT / "freight_optimization" / "data" / "raw" / "market"

def _load_and_align(csv_name: str, col_map: List[tuple], rate_df: pd.DataFrame) -> Dict[str, List[float]]:
    """Load one market CSV and merge_asof-align its derived columns to rate_df dates."""
    path = MARKET_DIR / csv_name
    result: Dict[str, List[float]] = {}
    if not path.exists():
        print(f"  WARN: {path.name} not found — skipping {[c[1] for c in col_map]}")
        return result
    raw = pd.read_csv(path, parse_dates=["date"]).sort_values("date")
    rate_sorted = rate_df[["report_date"]].rename(columns={"report_date": "date"}).sort_values("date")
    for col, key in col_map:
        if col not in raw.columns:
            # Derive returns / changes on the fly from price column
            if "price" in raw.columns:
                if col == "return_1d":
                    raw["return_1d"] = raw["price"].pct_change()
                elif col == "change_7d":
                    raw["change_7d"] = raw["price"].pct_change(7)
                elif "change_1m" in col:
                    raw["change_1m"] = raw["price"].pct_change(21)
                elif "change_3m" in col:
                    raw["change_3m"] = raw["price"].pct_change(63)
                elif "ma_3m" in col:
                    raw["ma_3m"] = raw["price"].rolling(63).mean()
        if col not in raw.columns:
            print(f"  WARN: col '{col}' not in {csv_name} — skipping {key}")
            continue
        exog_sub = raw[["date", col]].dropna().copy()
        merged = pd.merge_asof(rate_sorted, exog_sub, on="date", direction="backward")
        vals = merged[col].tolist()
        if not any(pd.isna(v) for v in vals):
            result[key] = [float(v) for v in vals]
        else:
            n_miss = sum(1 for v in vals if pd.isna(v))
            print(f"  WARN: {key} has {n_miss}/{len(vals)} NaN after asof — excluded from enriched set")
    return result


SOURCE_MAP = {
    "brent_historical.csv": [
        ("price", "brent"), ("return_1d", "brent_return_1d"), ("change_7d", "brent_change_7d"),
    ],
    "wti_historical.csv": [
        ("price", "wti"), ("return_1d", "wti_return_1d"), ("change_7d", "wti_change_7d"),
    ],
    "iron_ore_historical.csv": [
        ("iron_ore_price", "iron_ore"),
        ("iron_ore_change_1m", "iron_ore_change_1m"),
        ("iron_ore_change_3m", "iron_ore_change_3m"),
        ("iron_ore_ma_3m", "iron_ore_ma_3m"),
    ],
}

print("\nLoading exogenous features (merge_asof backward):")
aligned_exog: Dict[str, List[float]] = {}
for csv_name, col_map in SOURCE_MAP.items():
    aligned_exog.update(_load_and_align(csv_name, col_map, df_rates))

REQUIRED = {
    "brent", "brent_return_1d", "brent_change_7d",
    "wti", "wti_return_1d", "wti_change_7d",
    "iron_ore", "iron_ore_change_1m", "iron_ore_change_3m", "iron_ore_ma_3m",
}
enriched_viable = REQUIRED.issubset(aligned_exog.keys())
print(f"  Enriched path viable: {enriched_viable}  (loaded {len(aligned_exog)} sources)")

# ---------------------------------------------------------------------------
# Walk-forward evaluation
# ---------------------------------------------------------------------------
from backend.engine.forecasting import (
    damped_trend, _naive_forecast, _fit_arima,
    _fit_xgboost, _ENRICHED_EXOG_KEYS,
)
from backend.config.constants import MIN_OBSERVATIONS_FOR_XGBOOST

HORIZON = 7
MIN_TRAIN = 50
MAX_FOLDS = 50


def _metrics(actuals: List[float], preds: List[float]) -> tuple:
    errors = [abs(p - a) for p, a in zip(preds, actuals)]
    sq_err = [(p - a) ** 2 for p, a in zip(preds, actuals)]
    pct_err = [abs(p - a) / max(abs(a), 1.0) * 100 for p, a in zip(preds, actuals)]
    mae  = sum(errors) / len(errors)
    rmse = math.sqrt(sum(sq_err) / len(sq_err))
    mape = sum(pct_err) / len(pct_err)
    return mae, rmse, mape


def walk_forward(name: str, forecast_fn) -> tuple:
    all_actuals, all_preds = [], []
    n = len(history)
    valid_starts = list(range(MIN_TRAIN, n - HORIZON))
    if len(valid_starts) > MAX_FOLDS:
        step = len(valid_starts) / MAX_FOLDS
        valid_starts = [valid_starts[int(i * step)] for i in range(MAX_FOLDS)]

    fold_count = 0
    for t in valid_starts:
        train = history[:t]
        actuals = history[t:t + HORIZON]
        try:
            preds = forecast_fn(train, t)
            all_actuals.extend(actuals)
            all_preds.extend(preds[:len(actuals)])
            fold_count += 1
        except Exception as e:
            pass  # skip failing folds

    if not all_actuals:
        return (float("inf"), float("inf"), float("inf"), 0)
    mae, rmse, mape = _metrics(all_actuals, all_preds)
    return mae, rmse, mape, fold_count


print(f"\nRunning expanding-window walk-forward (horizon={HORIZON}d, min_train={MIN_TRAIN}, max_folds={MAX_FOLDS})...\n")

results = []

# Naive
mae, rmse, mape, folds = walk_forward(
    "Naive",
    lambda train, t: _naive_forecast(train, HORIZON)
)
results.append(("Naive", mae, rmse, mape, folds, "—"))

# Damped Trend
mae, rmse, mape, folds = walk_forward(
    "Damped Trend",
    lambda train, t: damped_trend(train, HORIZON)
)
naive_mae = results[0][1]
pct_vs_naive = (naive_mae - mae) / naive_mae * 100 if naive_mae > 0 else 0
results.append(("Damped Trend", mae, rmse, mape, folds, f"{pct_vs_naive:+.1f}%"))

# ARIMA
mae, rmse, mape, folds = walk_forward(
    "ARIMA",
    lambda train, t: _fit_arima(train, HORIZON)
)
pct_vs_naive = (naive_mae - mae) / naive_mae * 100 if naive_mae > 0 else 0
results.append(("ARIMA", mae, rmse, mape, folds, f"{pct_vs_naive:+.1f}%"))

# Enriched XGBoost (if viable)
if enriched_viable:
    def _enriched_fn(train: List[float], t: int) -> List[float]:
        exog_slice = {k: v[:t] for k, v in aligned_exog.items()}
        return _fit_xgboost(train, HORIZON, exog=exog_slice)

    mae, rmse, mape, folds = walk_forward("XGBoost (enriched)", _enriched_fn)
    pct_vs_naive = (naive_mae - mae) / naive_mae * 100 if naive_mae > 0 else 0
    gated = "✓ PASS" if pct_vs_naive >= 5.0 else "✗ FAIL"
    results.append(("XGBoost (enriched)", mae, rmse, mape, folds, f"{pct_vs_naive:+.1f}%  {gated}"))
else:
    results.append(("XGBoost (enriched)", float("inf"), float("inf"), float("inf"), 0, "N/A (missing exog)"))

# ---------------------------------------------------------------------------
# Print table
# ---------------------------------------------------------------------------
print("=" * 80)
print(f"{'Model':<22} {'MAE':>10} {'RMSE':>10} {'MAPE':>8} {'Folds':>6}  vs Naive")
print("-" * 80)
for name, mae, rmse, mape, folds, tag in results:
    mae_s  = f"{mae:>10,.0f}"  if math.isfinite(mae)  else f"{'∞':>10}"
    rmse_s = f"{rmse:>10,.0f}" if math.isfinite(rmse) else f"{'∞':>10}"
    mape_s = f"{mape:>7.1f}%" if math.isfinite(mape) else f"{'∞':>8}"
    print(f"{name:<22} {mae_s} {rmse_s} {mape_s} {folds:>6}  {tag}")
print("=" * 80)
print()
print("Gate rule: model must beat Naive by ≥5% MAE to be selected.")
print(f"MIN_OBSERVATIONS_FOR_XGBOOST = {MIN_OBSERVATIONS_FOR_XGBOOST} (PROVISIONAL)")
print()
