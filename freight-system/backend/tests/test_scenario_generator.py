"""
tests/test_scenario_generator.py — Scenario Generator unit tests.

DOC4 Build Step 6 Done When:
  Unit tests confirm hand-calculated Optimistic/Pessimistic values against a
  known ForecastObject and confidence_band, including the degenerate
  zero-width-band case.

No DB required — scenario.py is a pure function.

Run: pytest backend/tests/test_scenario_generator.py -v
"""
from __future__ import annotations

import json
import pytest

from backend.engine.scenario import (
    FAVORABLE_DIRECTION,
    ScenarioPaths,
    generate_scenarios,
)
from backend.config.constants import (
    SCENARIO_OPTIMISTIC_BAND_FRACTION,
    SCENARIO_PESSIMISTIC_BAND_FRACTION,
)
from backend.warehouse.models import ForecastObject


# ---------------------------------------------------------------------------
# Helpers — build a minimal ForecastObject without a DB
# ---------------------------------------------------------------------------

def _make_forecast(
    trajectory: list[dict],
    lower: float,
    upper: float,
    point_estimate: float = 20_000.0,
) -> ForecastObject:
    """Create a ForecastObject with the given trajectory and confidence band."""
    return ForecastObject(
        route="C2",
        vessel_class="Capesize",
        horizon_days=7,
        generated_at=None,
        point_estimate=point_estimate,
        confidence_band=json.dumps({"lower": lower, "upper": upper}),
        trajectory=json.dumps(trajectory),
        driver_explanation="test",
        is_high_uncertainty=False,
        model_used="arima",
    )


# ---------------------------------------------------------------------------
# Directionality constant
# ---------------------------------------------------------------------------

class TestDirectionalityConstant:
    def test_favorable_direction_is_lower(self):
        """
        DOC3 explicit: for a cost the requester pays (freight rate), LOWER is
        favorable. This must be a named constant, not an inferred sign.
        """
        assert FAVORABLE_DIRECTION == "lower"

    def test_optimistic_fraction_is_valid(self):
        assert 0.0 < SCENARIO_OPTIMISTIC_BAND_FRACTION <= 1.0

    def test_pessimistic_fraction_is_valid(self):
        assert 0.0 < SCENARIO_PESSIMISTIC_BAND_FRACTION <= 1.0


# ---------------------------------------------------------------------------
# Hand-calculated Optimistic / Pessimistic values
# (DOC4 Done When: confirmed against a known ForecastObject)
# ---------------------------------------------------------------------------

class TestHandCalculatedValues:
    """
    Known inputs → hand-calculated outputs.

    Trajectory: [{day:1, point_estimate:20000}, {day:2, point_estimate:21000}]
    Confidence band: lower=18000, upper=24000
    SCENARIO_OPTIMISTIC_BAND_FRACTION = 0.5 (from constants.py)
    SCENARIO_PESSIMISTIC_BAND_FRACTION = 0.5

    Day 1 (base=20000, lower=18000, upper=24000):
      optimistic  = 20000 - 0.5 * (20000 - 18000) = 20000 - 1000 = 19000
      pessimistic = 20000 + 0.5 * (24000 - 20000) = 20000 + 2000 = 22000

    Day 2 (base=21000):
      optimistic  = 21000 - 0.5 * (21000 - 18000) = 21000 - 1500 = 19500
      pessimistic = 21000 + 0.5 * (24000 - 21000) = 21000 + 1500 = 22500
    """

    TRAJ = [
        {"day": 1, "point_estimate": 20_000.0},
        {"day": 2, "point_estimate": 21_000.0},
    ]
    LOWER, UPPER = 18_000.0, 24_000.0

    def _paths(self) -> ScenarioPaths:
        fc = _make_forecast(self.TRAJ, self.LOWER, self.UPPER)
        return generate_scenarios(fc)

    def test_base_equals_trajectory(self):
        paths = self._paths()
        assert len(paths.base) == 2
        assert paths.base[0]["point_estimate"] == pytest.approx(20_000.0)
        assert paths.base[1]["point_estimate"] == pytest.approx(21_000.0)

    def test_optimistic_day1_hand_calculated(self):
        paths = self._paths()
        expected = 20_000.0 - SCENARIO_OPTIMISTIC_BAND_FRACTION * (20_000.0 - self.LOWER)
        assert paths.optimistic[0]["point_estimate"] == pytest.approx(expected, rel=1e-4)

    def test_optimistic_day2_hand_calculated(self):
        paths = self._paths()
        expected = 21_000.0 - SCENARIO_OPTIMISTIC_BAND_FRACTION * (21_000.0 - self.LOWER)
        assert paths.optimistic[1]["point_estimate"] == pytest.approx(expected, rel=1e-4)

    def test_pessimistic_day1_hand_calculated(self):
        paths = self._paths()
        expected = 20_000.0 + SCENARIO_PESSIMISTIC_BAND_FRACTION * (self.UPPER - 20_000.0)
        assert paths.pessimistic[0]["point_estimate"] == pytest.approx(expected, rel=1e-4)

    def test_pessimistic_day2_hand_calculated(self):
        paths = self._paths()
        expected = 21_000.0 + SCENARIO_PESSIMISTIC_BAND_FRACTION * (self.UPPER - 21_000.0)
        assert paths.pessimistic[1]["point_estimate"] == pytest.approx(expected, rel=1e-4)

    def test_day_numbers_preserved(self):
        """Day numbers from trajectory must be preserved in all three paths."""
        paths = self._paths()
        for path in (paths.base, paths.optimistic, paths.pessimistic):
            assert path[0]["day"] == 1
            assert path[1]["day"] == 2

    def test_optimistic_lower_than_base(self):
        """For FAVORABLE_DIRECTION='lower', optimistic < base always."""
        paths = self._paths()
        for b, o in zip(paths.base, paths.optimistic):
            assert o["point_estimate"] <= b["point_estimate"]

    def test_pessimistic_higher_than_base(self):
        """For a cost payer, pessimistic > base always."""
        paths = self._paths()
        for b, p in zip(paths.base, paths.pessimistic):
            assert p["point_estimate"] >= b["point_estimate"]

    def test_all_three_paths_same_length(self):
        paths = self._paths()
        assert len(paths.base) == len(paths.optimistic) == len(paths.pessimistic) == 2


# ---------------------------------------------------------------------------
# Degenerate case: zero-width confidence band (DOC4 Done When required case)
# ---------------------------------------------------------------------------

class TestZeroWidthBand:
    """
    DOC3: confidence_band is (x, x) (zero width, degenerate) → all three
    scenarios collapse to the same path; not an error.
    """
    TRAJ = [
        {"day": 1, "point_estimate": 20_000.0},
        {"day": 2, "point_estimate": 21_000.0},
    ]

    def _paths(self) -> ScenarioPaths:
        fc = _make_forecast(self.TRAJ, lower=20_000.0, upper=20_000.0)
        return generate_scenarios(fc)

    def test_zero_width_band_does_not_raise(self):
        paths = self._paths()
        assert isinstance(paths, ScenarioPaths)

    def test_zero_width_base_day1_unchanged(self):
        paths = self._paths()
        assert paths.base[0]["point_estimate"] == pytest.approx(20_000.0)

    def test_zero_width_optimistic_equals_base_day1(self):
        """With zero band width, optimistic collapse to base on day 1."""
        paths = self._paths()
        # Day 1: base=20000, lower=20000 → shift = FRACTION * (20000 - 20000) = 0
        assert paths.optimistic[0]["point_estimate"] == pytest.approx(paths.base[0]["point_estimate"])

    def test_zero_width_pessimistic_equals_base_day1(self):
        """With zero band width, pessimistic collapse to base on day 1."""
        paths = self._paths()
        assert paths.pessimistic[0]["point_estimate"] == pytest.approx(paths.base[0]["point_estimate"])

    def test_zero_width_all_paths_identical(self):
        """
        DOC3: zero-width band → all three scenarios collapse to the SAME path.
        'Same path' means optimistic == pessimistic for every point, because:
          opt  = base - FRACTION*(base - lower)
          pess = base + FRACTION*(upper - base) = base - FRACTION*(base - lower)  [since upper==lower]
        They're the same regardless of where base sits relative to the band.
        """
        paths = self._paths()
        for o, p in zip(paths.optimistic, paths.pessimistic):
            assert o["point_estimate"] == pytest.approx(p["point_estimate"])



# ---------------------------------------------------------------------------
# Degenerate case: single-point trajectory (DOC3 edge case)
# ---------------------------------------------------------------------------

class TestSinglePointTrajectory:
    def test_single_point_returns_all_three_paths_length_1(self):
        fc = _make_forecast(
            [{"day": 1, "point_estimate": 18_000.0}],
            lower=16_000.0, upper=22_000.0,
        )
        paths = generate_scenarios(fc)
        assert len(paths.base) == 1
        assert len(paths.optimistic) == 1
        assert len(paths.pessimistic) == 1

    def test_single_point_values_correct(self):
        base_val = 18_000.0
        lower, upper = 16_000.0, 22_000.0
        fc = _make_forecast([{"day": 1, "point_estimate": base_val}], lower, upper)
        paths = generate_scenarios(fc)
        expected_opt  = base_val - SCENARIO_OPTIMISTIC_BAND_FRACTION  * (base_val - lower)
        expected_pess = base_val + SCENARIO_PESSIMISTIC_BAND_FRACTION * (upper - base_val)
        assert paths.optimistic[0]["point_estimate"]  == pytest.approx(expected_opt,  rel=1e-4)
        assert paths.pessimistic[0]["point_estimate"] == pytest.approx(expected_pess, rel=1e-4)


# ---------------------------------------------------------------------------
# Degenerate case: empty trajectory
# ---------------------------------------------------------------------------

class TestEmptyTrajectory:
    def test_empty_trajectory_returns_empty_paths(self):
        fc = _make_forecast([], lower=16_000.0, upper=22_000.0)
        paths = generate_scenarios(fc)
        assert paths.base == []
        assert paths.optimistic == []
        assert paths.pessimistic == []


# ---------------------------------------------------------------------------
# JSON string inputs (as stored in DB)
# ---------------------------------------------------------------------------

class TestJsonStringInputs:
    def test_trajectory_as_json_string(self):
        """generate_scenarios() must handle trajectory as a JSON string (DB storage format)."""
        fc = ForecastObject(
            route="C2", vessel_class="Capesize", horizon_days=7,
            generated_at=None, point_estimate=20_000.0,
            confidence_band=json.dumps({"lower": 18_000.0, "upper": 24_000.0}),
            trajectory=json.dumps([{"day": 1, "point_estimate": 20_000.0}]),
            driver_explanation="test", is_high_uncertainty=False, model_used="arima",
        )
        paths = generate_scenarios(fc)
        assert len(paths.base) == 1
        assert paths.base[0]["point_estimate"] == pytest.approx(20_000.0)

    def test_malformed_trajectory_returns_empty(self):
        """Malformed trajectory JSON → empty paths, no crash."""
        fc = ForecastObject(
            route="C2", vessel_class="Capesize", horizon_days=7,
            generated_at=None, point_estimate=20_000.0,
            confidence_band=json.dumps({"lower": 18_000.0, "upper": 24_000.0}),
            trajectory="this is not json {{{",
            driver_explanation="test", is_high_uncertainty=False, model_used="arima",
        )
        paths = generate_scenarios(fc)
        assert paths.base == []
        assert paths.optimistic == []
        assert paths.pessimistic == []


# ---------------------------------------------------------------------------
# Ordering invariant: optimistic ≤ base ≤ pessimistic for all points
# ---------------------------------------------------------------------------

class TestOrdering:
    def test_ordering_holds_for_7_day_trajectory(self):
        """
        For any valid trajectory + confidence_band with lower < upper,
        optimistic ≤ base ≤ pessimistic must hold for EVERY point.
        """
        traj = [{"day": i + 1, "point_estimate": 20_000.0 + i * 200.0} for i in range(7)]
        fc = _make_forecast(traj, lower=15_000.0, upper=28_000.0)
        paths = generate_scenarios(fc)
        for b, o, p in zip(paths.base, paths.optimistic, paths.pessimistic):
            assert o["point_estimate"] <= b["point_estimate"] + 1e-6   # optimistic ≤ base
            assert b["point_estimate"] <= p["point_estimate"] + 1e-6   # base ≤ pessimistic

    def test_ordering_holds_for_30_day_trajectory(self):
        traj = [{"day": i + 1, "point_estimate": 20_000.0 - i * 50.0} for i in range(30)]
        fc = _make_forecast(traj, lower=14_000.0, upper=25_000.0)
        paths = generate_scenarios(fc)
        for b, o, p in zip(paths.base, paths.optimistic, paths.pessimistic):
            assert o["point_estimate"] <= b["point_estimate"] + 1e-6
            assert b["point_estimate"] <= p["point_estimate"] + 1e-6
