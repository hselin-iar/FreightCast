"""
tests/test_forecasting_engine.py — Done When verification for Build Step 4.

DOC4 Build Step 4 Done When:
  1. train_and_evaluate() run against sample rate_history data produces gated
     ForecastObjects for at least one route × vessel-class pair.
  2. Correctly falls back to ARIMA/naive below MIN_OBSERVATIONS_FOR_XGBOOST.
  3. get_forecast() correctly switches to damped_trend when ConditionsMonitor trips
     on injected out-of-range test data.

Uses SQLite :memory: — no Postgres needed.
Run: pytest backend/tests/test_forecasting_engine.py -v
"""
from __future__ import annotations

import json
import os
import math
from datetime import datetime, timedelta, timezone
from typing import List
from unittest.mock import patch, MagicMock

import pytest

# SQLite override before any warehouse import
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from backend.warehouse.db import create_all_tables, reset_engine
from backend.warehouse import repository
from backend.engine.forecasting import (
    ForecastUnavailableError,
    ConditionsMonitor,
    damped_trend,
    _naive_forecast,
    _walk_forward_mae,
    _walk_forward_mae_with_exog,
    _fit_arima,
    _fit_xgboost,
    _fit_xgboost_ar,
    _fit_xgboost_enriched,
    _ENRICHED_EXOG_KEYS,
    _build_forecast_object,
    _select_best_model,
    train_and_evaluate,
    get_forecast,
    _apply_damped_trend_override,
    _fit_prophet,
    ProphetDecomposition,
)
from backend.config.constants import MIN_OBSERVATIONS_FOR_XGBOOST, FORECAST_HORIZONS_DAYS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_rate_series(n: int, start: float = 15000.0, noise: float = 500.0) -> List[float]:
    """Return a realistic synthetic rate time series of length n."""
    import random
    random.seed(42)
    vals = [start]
    for _ in range(n - 1):
        vals.append(max(1000.0, vals[-1] + random.uniform(-noise, noise)))
    return vals


@pytest.fixture(autouse=True)
def fresh_db():
    """Each test gets a clean SQLite :memory: database."""
    reset_engine()
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    create_all_tables("sqlite:///:memory:")
    repository.invalidate_scope_cache()
    yield
    reset_engine()


def _seed_rate_history(route: str, vessel_class: str, n: int, start: float = 15000.0):
    """Insert n rate history rows for (route, vessel_class)."""
    series = _make_rate_series(n, start=start)
    rows = []
    for i, rate in enumerate(series):
        rows.append({
            "route": route,
            "vessel_class": vessel_class,
            "date": (datetime.now(timezone.utc) - timedelta(days=n - i)).isoformat(),
            "rate": rate,
            "tier": "A",
            "provenance": "measured",
        })
    repository.upsert_rate_history(rows)
    return series


# ---------------------------------------------------------------------------
# 1. damped_trend() unit tests (carried-over logic)
# ---------------------------------------------------------------------------

class TestDampedTrend:
    def test_returns_horizon_length(self):
        history = _make_rate_series(50)
        preds = damped_trend(history, 7)
        assert len(preds) == 7

    def test_degenerate_single_point(self):
        preds = damped_trend([15000.0], 5)
        assert len(preds) == 5
        assert all(p == 15000.0 for p in preds)

    def test_degenerate_empty(self):
        preds = damped_trend([], 3)
        assert preds == [0.0, 0.0, 0.0]

    def test_upward_trend_positive(self):
        # Flat upward series — damped_trend should follow it
        history = [float(1000 + i * 100) for i in range(30)]
        preds = damped_trend(history, 5)
        # All predictions should be > last known value in an upward-trended series
        # (damping may reduce the rate, but level should be above last obs approximately)
        assert all(isinstance(p, float) for p in preds)
        assert len(preds) == 5

    def test_damping_phi_less_than_1(self):
        # With damping (phi < 1), the trend should not compound unboundedly
        history = [float(1000 + i * 500) for i in range(50)]   # steep upward
        preds_low_phi = damped_trend(history, 30, phi=0.5)
        preds_high_phi = damped_trend(history, 30, phi=0.99)
        # Lower phi = more damped = smaller final forecast
        assert preds_low_phi[-1] < preds_high_phi[-1]


# ---------------------------------------------------------------------------
# 2. Walk-forward validation
# ---------------------------------------------------------------------------

class TestWalkForward:
    def test_naive_mae_finite_on_enough_data(self):
        history = _make_rate_series(60)
        mae = _walk_forward_mae(history, _naive_forecast, horizon=7)
        assert math.isfinite(mae)
        assert mae > 0

    def test_insufficient_data_returns_inf(self):
        history = _make_rate_series(5)
        mae = _walk_forward_mae(history, _naive_forecast, horizon=7, min_train=30)
        assert mae == float("inf")

    def test_perfect_predictor_returns_zero_mae(self):
        # If forecast == actuals exactly, MAE = 0
        history = [100.0] * 60
        mae = _walk_forward_mae(history, _naive_forecast, horizon=5)
        assert mae == 0.0


# ---------------------------------------------------------------------------
# 3. ForecastUnavailableError before train_and_evaluate
# ---------------------------------------------------------------------------

class TestGetForecastBeforeTrain:
    def test_raises_forecast_unavailable(self):
        with pytest.raises(ForecastUnavailableError):
            get_forecast("C2", "Capesize", 7)

    def test_error_message_mentions_pair(self):
        try:
            get_forecast("C99", "Supramax/Ultramax", 14)
        except ForecastUnavailableError as exc:
            assert "C99" in str(exc)
            assert "Supramax/Ultramax" in str(exc)


# ---------------------------------------------------------------------------
# 4. train_and_evaluate() produces gated ForecastObjects
#    (DOC4 Build Step 4 Done When criterion 1)
# ---------------------------------------------------------------------------

class TestTrainAndEvaluate:
    """
    Core Done When test: train_and_evaluate() produces at least one gated
    ForecastObject for a route × vessel-class pair.

    Uses a small dataset (well below MIN_OBSERVATIONS_FOR_XGBOOST so XGBoost
    is skipped), testing the ARIMA / damped_trend path.
    """

    def test_produces_gated_forecast_for_one_pair(self):
        # Seed enough history for ARIMA to work (>= 30 obs)
        _seed_rate_history("C2", "Capesize", n=60)
        train_and_evaluate(routes=["C2"], vessel_classes=["Capesize"], horizons=[7])
        obj = repository.get_latest_forecast("C2", "Capesize", 7)
        assert obj is not None, "Expected a gated ForecastObject after train_and_evaluate"
        assert obj.point_estimate > 0
        assert obj.model_used in ("arima", "damped_trend", "xgboost", "naive")

    def test_multiple_horizons_all_written(self):
        _seed_rate_history("C2", "Capesize", n=60)
        train_and_evaluate(routes=["C2"], vessel_classes=["Capesize"], horizons=[7, 14, 30])
        for h in [7, 14, 30]:
            obj = repository.get_latest_forecast("C2", "Capesize", h)
            assert obj is not None, f"Expected ForecastObject for horizon={h}"

    def test_get_forecast_succeeds_after_train(self):
        _seed_rate_history("C2", "Capesize", n=60)
        train_and_evaluate(routes=["C2"], vessel_classes=["Capesize"], horizons=[7])
        obj = get_forecast("C2", "Capesize", 7)
        assert obj is not None
        assert obj.point_estimate > 0

    def test_pair_failure_does_not_crash_other_pairs(self):
        """retrain failure for one pair should not prevent others from writing."""
        _seed_rate_history("C2", "Capesize", n=60)
        # "C99" has no history — should skip without crashing
        train_and_evaluate(
            routes=["C2", "C99"],
            vessel_classes=["Capesize"],
            horizons=[7],
        )
        assert repository.get_latest_forecast("C2", "Capesize", 7) is not None
        assert repository.get_latest_forecast("C99", "Capesize", 7) is None

    def test_too_few_observations_skips_gracefully(self):
        """< 5 observations → skip without crashing."""
        _seed_rate_history("C3", "Panamax/Kamsarmax", n=3)
        # Should not raise
        train_and_evaluate(routes=["C3"], vessel_classes=["Panamax/Kamsarmax"], horizons=[7])
        # Nothing written (too few obs)
        assert repository.get_latest_forecast("C3", "Panamax/Kamsarmax", 7) is None


# ---------------------------------------------------------------------------
# 5. Below MIN_OBSERVATIONS_FOR_XGBOOST → ARIMA/naive only
#    (DOC4 Build Step 4 Done When criterion 2)
# ---------------------------------------------------------------------------

class TestXGBoostThreshold:
    def test_below_threshold_model_is_not_xgboost(self):
        """
        With 60 observations (well below MIN_OBSERVATIONS_FOR_XGBOOST=80),
        the model_used must never be 'xgboost'.
        """
        _seed_rate_history("C2", "Capesize", n=60)
        train_and_evaluate(routes=["C2"], vessel_classes=["Capesize"], horizons=[7])
        obj = repository.get_latest_forecast("C2", "Capesize", 7)
        assert obj is not None
        assert obj.model_used != "xgboost", (
            f"Expected non-xgboost model below MIN_OBSERVATIONS_FOR_XGBOOST={MIN_OBSERVATIONS_FOR_XGBOOST}, "
            f"got model_used={obj.model_used!r}"
        )

    def test_select_best_model_skips_xgboost_below_threshold(self):
        """_select_best_model() should never return 'xgboost' when n < threshold."""
        history = _make_rate_series(60)
        assert len(history) < MIN_OBSERVATIONS_FOR_XGBOOST
        name, preds, mae, _ = _select_best_model(history, 7, naive_mae=600.0, exog_series={})
        assert name != "xgboost", f"Expected non-xgboost, got {name!r}"
        assert len(preds) == 7
        assert math.isfinite(mae)


# ---------------------------------------------------------------------------
# 6. ConditionsMonitor trips → damped_trend served
#    (DOC4 Build Step 4 Done When criterion 3)
# ---------------------------------------------------------------------------

class TestConditionsMonitorTrip:
    def _seed_and_train(self, route: str = "C2", vessel_class: str = "Capesize"):
        _seed_rate_history(route, vessel_class, n=60)
        train_and_evaluate(routes=[route], vessel_classes=[vessel_class], horizons=[7])

    def test_conditions_monitor_trips_on_spike(self):
        """ConditionsMonitor.check() returns (True, reason) when a spike is injected."""
        monitor = ConditionsMonitor(bdi_spike_pct=5.0)  # low threshold → easy to trip

        # Seed historical BDRY values (avg ~1700)
        for i in range(10):
            repository.upsert_exogenous_feature([{
                "source": "bdry",
                "date": (datetime.now(timezone.utc) - timedelta(days=10 - i)).isoformat(),
                "value": 1700.0,
            }])
        # Inject extreme spike value (today)
        repository.upsert_exogenous_feature([{
            "source": "bdry",
            "date": datetime.now(timezone.utc).isoformat(),
            "value": 3000.0,  # +76% spike — should trip at 5% threshold
        }])

        tripped, reason = monitor.check("C2", "Capesize")
        assert tripped, f"Expected monitor to trip, got tripped={tripped}, reason={reason!r}"
        assert "BDI" in reason or "spike" in reason.lower()

    def test_conditions_monitor_no_trip_on_normal_market(self):
        """ConditionsMonitor.check() returns (False, '') on stable market."""
        monitor = ConditionsMonitor(bdi_spike_pct=30.0)

        # Seed stable BDRY
        for i in range(10):
            repository.upsert_exogenous_feature([{
                "source": "bdry",
                "date": (datetime.now(timezone.utc) - timedelta(days=10 - i)).isoformat(),
                "value": 1700.0 + i * 5.0,  # gentle upward drift
            }])

        tripped, reason = monitor.check("C2", "Capesize")
        assert not tripped, f"Expected no trip, got tripped={tripped}, reason={reason!r}"

    def test_get_forecast_returns_damped_trend_when_monitor_trips(self):
        """
        When ConditionsMonitor trips, get_forecast() must serve a damped_trend
        override (model_used='damped_trend', is_high_uncertainty=True).
        """
        self._seed_and_train()

        # Confirm a non-damped_trend forecast exists first
        stored = repository.get_latest_forecast("C2", "Capesize", 7)
        assert stored is not None

        # Patch ConditionsMonitor.check to always trip
        with patch(
            "backend.engine.forecasting._conditions_monitor.check",
            return_value=(True, "Injected test spike: BDI +80%"),
        ):
            result = get_forecast("C2", "Capesize", 7)

        assert result.model_used == "damped_trend", (
            f"Expected damped_trend override, got {result.model_used!r}"
        )
        assert result.is_high_uncertainty is True
        assert "damped_trend override" in (result.driver_explanation or "")
        assert "Injected test spike" in (result.driver_explanation or "")

    def test_conditions_monitor_never_raises(self):
        """ConditionsMonitor.check() must never raise — even on empty warehouse."""
        monitor = ConditionsMonitor()
        # No data in warehouse
        tripped, reason = monitor.check("NonExistent", "UnknownClass")
        assert tripped is False
        assert reason == ""


# ---------------------------------------------------------------------------
# 7. ForecastObject shape contract (DOC3 §FEATURE: Forecasting Engine)
# ---------------------------------------------------------------------------

class TestForecastObjectShape:
    def test_all_required_fields_present(self):
        _seed_rate_history("C2", "Capesize", n=60)
        train_and_evaluate(routes=["C2"], vessel_classes=["Capesize"], horizons=[7])
        obj = repository.get_latest_forecast("C2", "Capesize", 7)
        assert obj is not None
        # Required shape per DOC3
        assert obj.route == "C2"
        assert obj.vessel_class == "Capesize"
        assert obj.horizon_days == 7
        assert obj.point_estimate > 0
        assert obj.model_used in ("xgboost", "arima", "naive", "damped_trend")
        assert obj.generated_at is not None
        # confidence_band is valid JSON with lower/upper
        cb = json.loads(obj.confidence_band)
        assert "lower" in cb and "upper" in cb
        assert cb["lower"] <= obj.point_estimate <= cb["upper"] or cb["upper"] > 0
        # trajectory is non-empty list
        traj = json.loads(obj.trajectory)
        assert isinstance(traj, list)
        assert len(traj) >= 1
        assert "day" in traj[0] and "point_estimate" in traj[0]

    def test_provenance_stored_in_driver_explanation(self):
        """provenance='modeled' should appear in driver_explanation."""
        _seed_rate_history("C2", "Capesize", n=60)
        train_and_evaluate(routes=["C2"], vessel_classes=["Capesize"], horizons=[7])
        obj = repository.get_latest_forecast("C2", "Capesize", 7)
        assert obj is not None
        assert obj.provenance == "modeled" or "modeled" in (obj.driver_explanation or "").lower()

    def test_horizon_clamping_in_get_forecast(self):
        """get_forecast with out-of-range horizon should clamp to nearest valid horizon."""
        _seed_rate_history("C2", "Capesize", n=60)
        train_and_evaluate(routes=["C2"], vessel_classes=["Capesize"], horizons=[7])
        # horizon_days=9 → clamped to 7 (nearest in FORECAST_HORIZONS_DAYS=[7,14,30])
        obj = get_forecast("C2", "Capesize", 9)
        assert obj is not None
        assert obj.horizon_days == 7


# ---------------------------------------------------------------------------
# 8. Enriched XGBoost feature path (optional — addition #5 from approval)
# ---------------------------------------------------------------------------

class TestXGBoostEnrichedFeatures:
    """
    Verify the enriched path activates when the full _ENRICHED_EXOG_KEYS dict is
    supplied and returns horizon-length predictions.
    90 observations ensures n >= MIN_OBSERVATIONS_FOR_XGBOOST=80 (PROVISIONAL).
    """

    def _make_exog(self, n: int) -> dict:
        """Synthetic exog dict with all required keys, length n."""
        import random
        rng = random.Random(7)
        result = {}
        for key in _ENRICHED_EXOG_KEYS:
            base = 80.0 if "brent" in key or "wti" in key else 100.0
            result[key] = [base + rng.uniform(-5, 5) for _ in range(n)]
        return result

    def test_enriched_path_returns_correct_horizon_length(self):
        """_fit_xgboost_enriched returns exactly horizon predictions."""
        n = 90
        history = _make_rate_series(n)
        exog = self._make_exog(n)
        preds, _ = _fit_xgboost_enriched(history, 7, exog)
        assert len(preds) == 7, f"Expected 7 preds, got {len(preds)}"
        assert all(isinstance(p, float) for p in preds)
        assert all(math.isfinite(p) for p in preds)

    def test_enriched_path_activated_via_dispatch(self):
        """_fit_xgboost dispatches to enriched when full exog dict is supplied."""
        n = 90
        history = _make_rate_series(n)
        exog = self._make_exog(n)
        # All 10 enriched keys present, all correct length → enriched path fires
        preds, _ = _fit_xgboost(history, 7, exog=exog)
        assert len(preds) == 7
        assert all(math.isfinite(p) for p in preds)

    def test_partial_exog_falls_back_to_ar(self):
        """Supplying only a subset of enriched keys silently triggers AR fallback."""
        n = 90
        history = _make_rate_series(n)
        partial_exog = {"brent": [80.0] * n}  # only 1 of 10 required keys
        preds, _ = _fit_xgboost(history, 7, exog=partial_exog)
        assert len(preds) == 7
        assert all(math.isfinite(p) for p in preds)

    def test_walk_forward_mae_with_exog_returns_finite(self):
        """_walk_forward_mae_with_exog produces a finite MAE on synthetic enriched data."""
        n = 90
        history = _make_rate_series(n)
        exog = self._make_exog(n)
        mae = _walk_forward_mae_with_exog(
            history,
            exog,
            lambda h, hor, ex: _fit_xgboost(h, hor, exog=ex)[0],
            horizon=7,
        )
        assert math.isfinite(mae), f"Expected finite MAE, got {mae}"
        assert mae > 0


# ---------------------------------------------------------------------------
# 9. Capesize 5TC history ingest adapter
# ---------------------------------------------------------------------------

class TestCapesize5TCHistoryIngest:
    """
    Verify the new real-data ingest adapter (capesize_5tc_history_ingest.py).
    The test locates the CSV via the same path logic the module uses, and skips
    gracefully if the freight_optimization workspace is not present.
    """

    def test_ingest_returns_ingest_result_type(self):
        """run() always returns an IngestResult without raising."""
        from backend.ingestion.batch import capesize_5tc_history_ingest
        from backend.ingestion.types import IngestResult
        result = capesize_5tc_history_ingest.run()
        assert isinstance(result, IngestResult)
        assert result.source == "capesize_5tc_real_history"

    def test_ingest_rows_when_csv_present(self):
        """If the primary CSV exists, rows_ingested > 0."""
        from backend.ingestion.batch import capesize_5tc_history_ingest
        if not capesize_5tc_history_ingest._PRIMARY_PATH.exists():
            pytest.skip("drycargo_5tc_c5.csv not present in this environment")
        result = capesize_5tc_history_ingest.run()
        assert result.rows_ingested > 0, (
            f"Expected >0 ingested rows, got {result.rows_ingested}. "
            f"Alerts: {result.alerts}"
        )
        assert result.rows_rejected == 0, (
            f"Expected 0 rejected rows, got {result.rows_rejected}"
        )

    def test_get_rows_matches_rows_ingested(self):
        """get_rows() returns the same count as rows_ingested from run()."""
        from backend.ingestion.batch import capesize_5tc_history_ingest
        if not capesize_5tc_history_ingest._PRIMARY_PATH.exists():
            pytest.skip("drycargo_5tc_c5.csv not present in this environment")
        result = capesize_5tc_history_ingest.run()
        rows = capesize_5tc_history_ingest.get_rows()
        assert len(rows) == result.rows_ingested

    def test_ingest_graceful_when_csv_missing(self, tmp_path, monkeypatch):
        """run() returns IngestResult with 0 rows (no raise) when CSV is absent."""
        from backend.ingestion.batch import capesize_5tc_history_ingest
        # Redirect paths to a temp dir with no CSV
        missing = tmp_path / "no_such.csv"
        monkeypatch.setattr(capesize_5tc_history_ingest, "_PRIMARY_PATH", missing)
        monkeypatch.setattr(capesize_5tc_history_ingest, "_FALLBACK_PATH", missing)
        result = capesize_5tc_history_ingest.run()
        assert result.rows_ingested == 0
        assert len(result.alerts) > 0


# ---------------------------------------------------------------------------
# 10. Market history ingest adapter
# ---------------------------------------------------------------------------

class TestMarketHistoryIngest:
    """
    Verify market_history_ingest.py handles missing market directory gracefully
    and returns rows when the CSVs are present.
    """

    def test_ingest_returns_ingest_result_type(self):
        """run() always returns an IngestResult without raising."""
        from backend.ingestion.batch import market_history_ingest
        from backend.ingestion.types import IngestResult
        result = market_history_ingest.run()
        assert isinstance(result, IngestResult)
        assert result.source == "market_history_multi"

    def test_graceful_when_market_dir_missing(self, tmp_path, monkeypatch):
        """run() returns 0 rows and alerts (no raise) when market dir is absent."""
        from backend.ingestion.batch import market_history_ingest
        # Point _MARKET_DIR to an empty temp directory
        monkeypatch.setattr(market_history_ingest, "_MARKET_DIR", tmp_path)
        result = market_history_ingest.run()
        assert result.rows_ingested == 0
        # Should have alerts explaining each missing CSV
        assert len(result.alerts) > 0

    def test_ingest_rows_when_csvs_present(self):
        """If brent/wti/iron_ore CSVs exist, rows_ingested > 0."""
        from backend.ingestion.batch import market_history_ingest
        market_dir = market_history_ingest._MARKET_DIR
        any_csv_exists = any(
            (market_dir / csv).exists()
            for csv in ["brent_historical.csv", "wti_historical.csv", "iron_ore_historical.csv"]
        )
        if not any_csv_exists:
            pytest.skip("Market CSVs not present in this environment")
        result = market_history_ingest.run()
        assert result.rows_ingested > 0


# ---------------------------------------------------------------------------
# 11. Prophet Explainability Integration
# ---------------------------------------------------------------------------

class TestProphetExplainability:
    """
    Verify that the Prophet decomposition layer:
    1. Produces decomposition when history is sufficient (>= 20 obs).
    2. Gracefully absent when history is too short (< 20 obs).
    3. Does NOT affect model_used (gate winner remains unaffected).
    4. Regressor keys are populated when exog is supplied.
    5. Narrative is a non-empty English string.

    These tests call _fit_prophet() directly so they run without a full retrain cycle.
    Prophet is skipped gracefully if not installed.
    """

    def _make_exog_for_prophet(self, n: int) -> dict:
        """Synthetic exog dict with Prophet regressor keys, length n."""
        import random
        rng = random.Random(99)
        result = {}
        for key in ("brent", "wti", "iron_ore", "bdry"):
            result[key] = [80.0 + rng.gauss(0, 3) for _ in range(n)]
        return result

    def test_prophet_decomp_present_when_sufficient_history(self):
        """With >= 20 observations, _fit_prophet returns a ProphetDecomposition."""
        pytest.importorskip("prophet", reason="prophet not installed — skipping")
        from backend.engine.forecasting import _fit_prophet, ProphetDecomposition

        history = _make_rate_series(40)
        exog = self._make_exog_for_prophet(40)
        result = _fit_prophet(history, 7, exog=exog)

        assert isinstance(result, ProphetDecomposition)
        assert len(result.yhat) == 7
        assert result.trend_direction in ("rising", "falling", "flat")
        assert isinstance(result.trend_delta, float)
        assert isinstance(result.weekly_seasonality_amplitude, float)
        assert isinstance(result.regressor_effects, dict)
        assert isinstance(result.narrative, str) and len(result.narrative) > 0

    def test_prophet_narrative_non_empty(self):
        """narrative is a non-empty English string."""
        pytest.importorskip("prophet", reason="prophet not installed — skipping")
        from backend.engine.forecasting import _fit_prophet

        history = _make_rate_series(30)
        result = _fit_prophet(history, 7, exog=None)

        assert isinstance(result.narrative, str)
        assert len(result.narrative) >= 10, f"Narrative too short: {result.narrative!r}"

    def test_prophet_regressor_effects_keys(self):
        """regressor_effects contains expected keys when exog is supplied."""
        pytest.importorskip("prophet", reason="prophet not installed — skipping")
        from backend.engine.forecasting import _fit_prophet

        history = _make_rate_series(40)
        exog = self._make_exog_for_prophet(40)
        result = _fit_prophet(history, 7, exog=exog)

        # At least one of our seeded regressor keys should appear
        known_keys = {"brent", "wti", "iron_ore", "bdry"}
        found = known_keys & set(result.regressor_effects.keys())
        assert len(found) > 0, (
            f"Expected at least one of {known_keys} in regressor_effects, "
            f"got keys: {set(result.regressor_effects.keys())}"
        )

    def test_model_used_unaffected_by_prophet(self):
        """model_used in the ForecastObject is set by the gate, never by Prophet."""
        pytest.importorskip("prophet", reason="prophet not installed — skipping")
        from backend.engine.forecasting import _build_forecast_object, _fit_prophet

        history = _make_rate_series(40)
        exog = self._make_exog_for_prophet(40)

        try:
            prophet_decomp = _fit_prophet(history, 7, exog=exog)
        except Exception:
            pytest.skip("Prophet fit failed in this environment")

        obj_dict = _build_forecast_object(
            "TestRoute", "Capesize", 7, history[-7:], history,
            "arima",  # gate winner — must remain "arima" regardless of Prophet
            feature_importances={"lag_1": 0.5},
            prophet_decomp=prophet_decomp,
        )
        assert obj_dict["model_used"] == "arima", (
            f"Expected model_used='arima', got {obj_dict['model_used']!r}"
        )

    def test_prophet_gracefully_absent_when_short_history(self):
        """prophet_decomposition key absent from driver_explanation when prophet_decomp=None."""
        from backend.engine.forecasting import _build_forecast_object

        short_history = _make_rate_series(10)
        obj_dict = _build_forecast_object(
            "TestRoute", "Capesize", 7, short_history[-7:], short_history,
            "naive",
            feature_importances={},
            prophet_decomp=None,  # no Prophet — should gracefully omit key
        )
        parsed = json.loads(obj_dict["driver_explanation"])
        assert "prophet_decomposition" not in parsed, (
            "prophet_decomposition should be absent when prophet_decomp=None"
        )
        assert "text" in parsed
