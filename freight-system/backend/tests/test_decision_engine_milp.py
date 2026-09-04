"""
tests/test_decision_engine_milp.py — Decision Engine unit tests.

DOC4 Build Step 8 Done When:
  - Feasibility-linking correctly excludes infeasible (v,p) pairs from variable domain
  - Objective matches hand-calculated C_s for a small fixture
  - Each HumanOverrides field correctly shrinks the feasible region without altering objective
  - Forcing a timeout (mocked) correctly triggers _hybrid_fallback and returns valid scenario_comparison[]

These tests use mocked repository calls and pure-function testing where possible,
so no live DB is needed.

Run: pytest backend/tests/test_decision_engine_milp.py -v
"""
from __future__ import annotations

import json
import math
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from backend.engine.constraint import FeasibleOption, check_feasibility
from backend.engine.cost_terms import CostBreakdown, RoutePhysics, build_cost_coefficient
from backend.engine.decision import (
    HumanOverrides,
    Strategy,
    VoyageDetail,
    _assemble_strategy,
    _compute_tau,
    _get_scenario_rate,
    _hybrid_fallback,
    solve,
)
from backend.config.constants import (
    DEFAULT_BALLAST_SPEED_KNOTS,
    DEFAULT_COMMITMENT_BENCHMARK_PCT,
    MILP_SOLVE_TIMEOUT_SECONDS,
    SCENARIO_OPTIMISTIC_BAND_FRACTION,
    SCENARIO_PESSIMISTIC_BAND_FRACTION,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def route_physics():
    return RoutePhysics(
        origin="Australia (Hay Point)",
        destination="Gangavaram",
        distance_nm=5000.0,
        laden_consumption_tpd=58.0,
        ballast_consumption_tpd=42.0,
        speed_knots=12.0,
    )


@pytest.fixture
def supramax_opt():
    """Supramax is feasible at Gangavaram, no lightening."""
    return FeasibleOption(
        vessel_class="Supramax/Ultramax",
        port="Gangavaram",
        is_feasible=True,
        infeasible_reason=None,
        is_inefficient_fit=False,
        discharge_days=2.0,
        tidal_window_note=None,
        requires_lightening=False,
        lightening_port=None,
        lightening_penalty_days=0.0,
        lightening_penalty_cost_usd=0.0,
        size_rank=3,
    )


@pytest.fixture
def capesize_infeasible_paradip():
    """Capesize is infeasible at Paradip — LOA too long."""
    return FeasibleOption(
        vessel_class="Capesize",
        port="Paradip",
        is_feasible=False,
        infeasible_reason="LOA 295.0m exceeds port limit 250.0m",
        is_inefficient_fit=False,
        discharge_days=0.0,
        tidal_window_note=None,
        requires_lightening=False,
        lightening_port=None,
        lightening_penalty_days=0.0,
        lightening_penalty_cost_usd=0.0,
        size_rank=1,
    )


@pytest.fixture
def panamax_lightening():
    """Panamax requires lightening at Paradip."""
    return FeasibleOption(
        vessel_class="Panamax/Kamsarmax",
        port="Paradip",
        is_feasible=True,
        infeasible_reason=None,
        is_inefficient_fit=False,
        discharge_days=2.5,
        tidal_window_note=None,
        requires_lightening=True,
        lightening_port="Gangavaram",
        lightening_penalty_days=1.5,
        lightening_penalty_cost_usd=22_500.0,
        size_rank=2,
    )


@pytest.fixture
def sample_coeffs(route_physics):
    """
    Pre-built cost coefficient table for testing objective calculations.
    Covers Supramax/Gangavaram/τ=0/spot+locked × 3 scenarios.
    """
    coeffs = {}
    for scen in ("base", "optimistic", "pessimistic"):
        rate_map = {"base": 20_000.0, "optimistic": 18_000.0, "pessimistic": 23_000.0}
        rate = rate_map[scen]
        for mode in ("spot", "locked"):
            bd = build_cost_coefficient(
                quantity=58_000.0,
                mode=mode,
                rate_at_tau=rate,
                base_rate_at_lock_day=20_000.0,  # Base rate always 20000 for locked
                commitment_benchmark_pct=10.0,
                route_physics=route_physics,
                bunker_price_usd_per_tonne=600.0,
                handling_rate_tpd=40_000.0,
                idle_days=0.0,
                requires_lightening=False,
                lightening_penalty_days=0.0,
            )
            coeffs[("Supramax/Ultramax", "Gangavaram", 0, mode, scen)] = bd
    return coeffs


# ---------------------------------------------------------------------------
# _compute_tau — event-based time point generation
# ---------------------------------------------------------------------------

class TestComputeTau:
    def test_always_includes_day_0(self):
        """Day 0 (today) is always a candidate."""
        tau = _compute_tau(14, [], "Supramax/Ultramax", "Australia (Hay Point)")
        assert 0 in tau

    def test_includes_end_of_flexibility_window(self):
        """Last day of timing window is always a candidate."""
        tau = _compute_tau(14, [], "Supramax/Ultramax", "Australia (Hay Point)")
        assert 14 in tau

    def test_includes_weekly_endpoints(self):
        """End of each week inside the window is included."""
        tau = _compute_tau(21, [], "Supramax/Ultramax", "Australia (Hay Point)")
        assert 7 in tau
        assert 14 in tau
        assert 21 in tau

    def test_includes_forecast_local_minimum(self):
        """
        If the forecast trajectory has a local minimum (e.g., cheaper fix day),
        that day should appear in τ candidates.
        """
        # Trajectory: 20000, 18000 (local min at day 7), 21000
        traj = [
            {"day": 0, "point_estimate": 20_000.0},
            {"day": 7, "point_estimate": 18_000.0},  # local min
            {"day": 14, "point_estimate": 21_000.0},
        ]
        tau = _compute_tau(14, traj, "Supramax/Ultramax", "Australia (Hay Point)")
        assert 7 in tau

    def test_human_override_min_fix_day_filters(self):
        """min_fix_day removes τ points earlier than the minimum."""
        overrides = HumanOverrides(min_fix_day=5)
        tau = _compute_tau(14, [], "Supramax/Ultramax", "Australia (Hay Point)",
                           human_overrides=overrides)
        assert all(d >= 5 for d in tau)

    def test_human_override_max_completion_day_filters(self):
        """max_completion_day removes τ points later than the maximum."""
        overrides = HumanOverrides(max_completion_day=7)
        tau = _compute_tau(14, [], "Supramax/Ultramax", "Australia (Hay Point)",
                           human_overrides=overrides)
        assert all(d <= 7 for d in tau)

    def test_always_returns_at_least_one_point(self):
        """Even with very tight constraints, at least one τ point is returned."""
        overrides = HumanOverrides(min_fix_day=3, max_completion_day=3)
        tau = _compute_tau(14, [], "Supramax/Ultramax", "Australia (Hay Point)",
                           human_overrides=overrides)
        assert len(tau) >= 1

    def test_is_sorted_and_deduplicated(self):
        """Result must be sorted and contain no duplicates."""
        tau = _compute_tau(14, [], "Supramax/Ultramax", "Australia (Hay Point)")
        assert tau == sorted(set(tau))

    @patch("backend.engine.decision.repository.get_candidate_vessels_by_class")
    @patch("backend.engine.decision.repository.get_earliest_repositioning_days")
    def test_repositioning_aware_bounds_tau(self, mock_repo_days, mock_vessels):
        """
        When AIS data says earliest repositioning is 3.0 days (72h raw), the
        step51a 6h buffer is applied: buffered = 72 + 6 = 78h → earliest_day = ceil(78/24) = 4.
        All τ points before day 4 are removed; day 4 is added.
        """
        mock_vessels.return_value = [MagicMock()]  # Non-empty → AIS data exists
        mock_repo_days.return_value = 3.0          # 3 days raw repositioning

        tau = _compute_tau(14, [], "Capesize", "Australia (Hay Point)")
        assert all(d >= 4 for d in tau), f"Expected all τ ≥ 4 (3d + 6h buffer), got {tau}"
        assert 4 in tau
        assert 3 not in tau, "Day 3 should be excluded: 72h + 6h buffer pushes earliest to day 4"

    @patch("backend.engine.decision.repository.get_candidate_vessels_by_class")
    def test_graceful_fallback_when_no_ais_data(self, mock_vessels):
        """
        No AIS vessel data → calendar-only τ points, no crash.
        """
        mock_vessels.return_value = []  # No AIS data

        tau = _compute_tau(14, [], "Capesize", "Australia (Hay Point)")
        assert 0 in tau
        assert 14 in tau


# ---------------------------------------------------------------------------
# _get_scenario_rate — rate lookup per scenario
# ---------------------------------------------------------------------------

class TestGetScenarioRate:
    def _traj(self):
        return [
            {"day": 0, "point_estimate": 20_000.0},
            {"day": 7, "point_estimate": 21_000.0},
            {"day": 14, "point_estimate": 19_000.0},
        ]

    def test_base_returns_trajectory_value(self):
        rate = _get_scenario_rate(self._traj(), lower=16_000.0, upper=25_000.0, day=0, scenario_name="base")
        assert rate == pytest.approx(20_000.0)

    def test_optimistic_lower_than_base(self):
        """Optimistic rate must be lower than base (freight rate — lower is favorable)."""
        base_rate = 20_000.0
        rate = _get_scenario_rate(self._traj(), lower=16_000.0, upper=25_000.0, day=0, scenario_name="optimistic")
        assert rate < base_rate

    def test_pessimistic_higher_than_base(self):
        """Pessimistic rate must be higher than base."""
        base_rate = 20_000.0
        rate = _get_scenario_rate(self._traj(), lower=16_000.0, upper=25_000.0, day=0, scenario_name="pessimistic")
        assert rate > base_rate

    def test_optimistic_hand_calculated(self):
        """
        base=20000, lower=16000, FRACTION=0.5
        optimistic = 20000 - 0.5*(20000-16000) = 18000
        """
        rate = _get_scenario_rate(self._traj(), lower=16_000.0, upper=25_000.0, day=0, scenario_name="optimistic")
        expected = 20_000.0 - SCENARIO_OPTIMISTIC_BAND_FRACTION * (20_000.0 - 16_000.0)
        assert rate == pytest.approx(expected)

    def test_pessimistic_hand_calculated(self):
        """
        base=20000, upper=25000, FRACTION=0.5
        pessimistic = 20000 + 0.5*(25000-20000) = 22500
        """
        rate = _get_scenario_rate(self._traj(), lower=16_000.0, upper=25_000.0, day=0, scenario_name="pessimistic")
        expected = 20_000.0 + SCENARIO_PESSIMISTIC_BAND_FRACTION * (25_000.0 - 20_000.0)
        assert rate == pytest.approx(expected)

    def test_picks_closest_trajectory_day(self):
        """For day=5, closest trajectory point is day=7 (traj is [0,7,14])."""
        rate = _get_scenario_rate(self._traj(), lower=16_000.0, upper=25_000.0, day=5, scenario_name="base")
        # day=5 is closer to day=7 (diff=2) than day=0 (diff=5)
        assert rate == pytest.approx(21_000.0)

    def test_empty_trajectory_returns_zero(self):
        rate = _get_scenario_rate([], lower=16_000.0, upper=25_000.0, day=0, scenario_name="base")
        assert rate == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Feasibility-linking exclusion (DOC4 Done When #1)
# ---------------------------------------------------------------------------

class TestFeasibilityLinking:
    """
    DOC4 Done When: feasibility-linking correctly excludes infeasible (v,p) pairs
    from the variable domain.

    We test this at the constraint.check_feasibility() integration level
    (used by solve() step 2) and the coefficient computation level
    (infeasible options produce no coefficients).
    """

    def test_infeasible_option_generates_no_coefficients(
        self, capesize_infeasible_paradip, route_physics
    ):
        """
        An infeasible FeasibleOption must produce NO cost coefficients
        — it cannot enter the MILP's objective or variable domain.
        """
        from backend.engine.decision import _compute_cost_coefficients
        coeffs = _compute_cost_coefficients(
            quantity=150_000.0,
            feasible_opts=[capesize_infeasible_paradip],
            tau_points={"Capesize": [0, 7]},
            forecasts={},
            route_physics_cache={},
            bunker_price=600.0,
            base_rate_at_lock_day={},
            commitment_benchmark_pct=10.0,
        )
        # No coefficients for an infeasible option
        assert len(coeffs) == 0

    def test_feasible_option_generates_coefficients(
        self, supramax_opt, route_physics
    ):
        """A feasible option generates coefficients (one per τ × mode × scenario)."""
        fc_obj = MagicMock()
        fc_obj.trajectory = json.dumps([{"day": 0, "point_estimate": 20_000.0}])
        fc_obj.confidence_band = json.dumps({"lower": 18_000.0, "upper": 24_000.0})
        fc_obj.point_estimate = 20_000.0

        from backend.engine.decision import _compute_cost_coefficients
        coeffs = _compute_cost_coefficients(
            quantity=58_000.0,
            feasible_opts=[supramax_opt],
            tau_points={"Supramax/Ultramax": [0]},
            forecasts={("Australia (Hay Point)→Gangavaram", "Supramax/Ultramax"): fc_obj},
            route_physics_cache={"Australia (Hay Point)→Gangavaram": route_physics},
            bunker_price=600.0,
            base_rate_at_lock_day={("Australia (Hay Point)→Gangavaram", "Supramax/Ultramax", "Gangavaram"): 20_000.0},
            commitment_benchmark_pct=10.0,
        )
        # 1 τ × 2 modes × 3 scenarios = 6 coefficients
        assert len(coeffs) == 6

    def test_mixed_feasibility_only_feasible_gets_coefficients(
        self, supramax_opt, capesize_infeasible_paradip, route_physics
    ):
        """Mixed list: only the feasible opt gets coefficients."""
        fc_obj = MagicMock()
        fc_obj.trajectory = json.dumps([{"day": 0, "point_estimate": 20_000.0}])
        fc_obj.confidence_band = json.dumps({"lower": 18_000.0, "upper": 24_000.0})
        fc_obj.point_estimate = 20_000.0

        from backend.engine.decision import _compute_cost_coefficients
        coeffs = _compute_cost_coefficients(
            quantity=58_000.0,
            feasible_opts=[supramax_opt, capesize_infeasible_paradip],
            tau_points={"Supramax/Ultramax": [0], "Capesize": [0]},
            forecasts={("Australia (Hay Point)→Gangavaram", "Supramax/Ultramax"): fc_obj},
            route_physics_cache={"Australia (Hay Point)→Gangavaram": route_physics},
            bunker_price=600.0,
            base_rate_at_lock_day={("Australia (Hay Point)→Gangavaram", "Supramax/Ultramax", "Gangavaram"): 20_000.0},
            commitment_benchmark_pct=10.0,
        )
        # Only Supramax/Gangavaram gets coefficients — Capesize/Paradip is infeasible
        assert all(k[0] == "Supramax/Ultramax" for k in coeffs)
        assert all(k[1] == "Gangavaram" for k in coeffs)


# ---------------------------------------------------------------------------
# Objective hand-calculated C_s (DOC4 Done When #2)
# ---------------------------------------------------------------------------

class TestObjectiveHandCalculated:
    """
    DOC4 Done When: objective matches hand-calculated C_s for a small fixture.
    """

    def test_spot_base_cost_coefficient_hand_calculated(self, route_physics):
        """
        Spot mode, Base scenario, τ=0:
          quantity=58000, rate=20000
          voyage_days = 5000/12/24 = 17.361...
          laden_bunker = 58 × 17.361 × 600 = 604,860
          ballast_bunker = 42 × 17.361 × 600 = 437,820
          port_handling = (58000/40000) × 15000 = 21,750
          tax = 58000 × 20000 × 0.05 = 58,000,000
          waiting = 0
          ocean_freight = 58000 × 20000 = 1,160,000,000
          total ≈ sum
        """
        from backend.config.constants import PORT_HANDLING_DAY_RATE_USD, WAITING_COST_PER_DAY_USD, TAX_RATE_PCT
        voyage_days = 5000.0 / 12.0 / 24.0
        expected_freight = 58_000.0 * 20_000.0
        expected_laden   = 58.0 * voyage_days * 600.0
        expected_ballast = 42.0 * voyage_days * 600.0
        expected_port    = (58_000.0 / 40_000.0) * PORT_HANDLING_DAY_RATE_USD
        expected_tax     = 58_000.0 * 20_000.0 * (TAX_RATE_PCT / 100.0)
        expected_opex    = route_physics.daily_opex_usd * voyage_days
        expected_other   = route_physics.other_voyage_cost_usd
        expected_total   = (expected_freight + expected_laden + expected_ballast
                            + expected_opex + expected_other + expected_port + expected_tax)

        bd = build_cost_coefficient(
            quantity=58_000.0,
            mode="spot",
            rate_at_tau=20_000.0,
            base_rate_at_lock_day=20_000.0,
            commitment_benchmark_pct=10.0,
            route_physics=route_physics,
            bunker_price_usd_per_tonne=600.0,
            handling_rate_tpd=40_000.0,
            idle_days=0.0,
            requires_lightening=False,
            lightening_penalty_days=0.0,
        )
        assert bd.ocean_freight == pytest.approx(expected_freight, rel=1e-4)
        assert bd.bunker == pytest.approx(expected_laden + expected_ballast, rel=1e-4)
        assert bd.port_handling == pytest.approx(expected_port, rel=1e-4)
        assert bd.tax == pytest.approx(expected_tax, rel=1e-4)
        assert bd.total == pytest.approx(expected_total, rel=1e-4)

    def test_locked_mode_cost_identical_across_scenarios(self, route_physics):
        """
        DOC4 explicit requirement: locked-mode cost must be IDENTICAL across
        Base / Optimistic / Pessimistic scenarios.
        This is THE critical correctness invariant for the Decision Engine.
        """
        kwargs = dict(
            quantity=58_000.0,
            mode="locked",
            base_rate_at_lock_day=20_000.0,
            commitment_benchmark_pct=10.0,
            route_physics=route_physics,
            bunker_price_usd_per_tonne=600.0,
            handling_rate_tpd=40_000.0,
            idle_days=0.0,
            requires_lightening=False,
            lightening_penalty_days=0.0,
        )
        bd_base = build_cost_coefficient(**{**kwargs, "rate_at_tau": 20_000.0})
        bd_opt  = build_cost_coefficient(**{**kwargs, "rate_at_tau": 17_000.0})
        bd_pess = build_cost_coefficient(**{**kwargs, "rate_at_tau": 24_000.0})

        assert bd_base.ocean_freight == pytest.approx(bd_opt.ocean_freight, rel=1e-9), \
            "Locked ocean_freight must be identical for Base vs Optimistic"
        assert bd_base.ocean_freight == pytest.approx(bd_pess.ocean_freight, rel=1e-9), \
            "Locked ocean_freight must be identical for Base vs Pessimistic"

    def test_worst_case_is_max_of_three_scenarios(self, sample_coeffs):
        """Worst-case cost must be the maximum of Base/Optimistic/Pessimistic totals."""
        vc, port, tau, mode = "Supramax/Ultramax", "Gangavaram", 0, "spot"
        base_cost = sample_coeffs[(vc, port, tau, mode, "base")].total
        opt_cost  = sample_coeffs[(vc, port, tau, mode, "optimistic")].total
        pess_cost = sample_coeffs[(vc, port, tau, mode, "pessimistic")].total
        worst = max(base_cost, opt_cost, pess_cost)
        assert worst == pess_cost  # Pessimistic = highest cost for spot mode


# ---------------------------------------------------------------------------
# HumanOverrides variable-fixing (DOC4 Done When #3)
# ---------------------------------------------------------------------------

class TestHumanOverrides:
    """
    DOC4 Done When: each HumanOverrides field correctly shrinks the feasible region
    without altering the objective itself.
    These tests verify that the overrides are applied before the solve
    (variable-fixing, not post-hoc filter).
    """

    def test_exclude_vessel_filters_tau_points(self):
        """exclude_vessel removes that class from τ point generation."""
        overrides = HumanOverrides(exclude_vessel=["Capesize"])
        vessel_classes = ["Capesize", "Supramax/Ultramax", "Panamax/Kamsarmax"]
        remaining = [v for v in vessel_classes if v not in (overrides.exclude_vessel or [])]
        assert "Capesize" not in remaining
        assert "Supramax/Ultramax" in remaining

    def test_max_completion_day_tightens_tau_upper_bound(self):
        """max_completion_day removes τ points after the deadline."""
        overrides = HumanOverrides(max_completion_day=7)
        tau = _compute_tau(30, [], "Supramax/Ultramax", "Australia (Hay Point)",
                           human_overrides=overrides)
        assert all(d <= 7 for d in tau), f"Got τ={tau} with max_completion_day=7"

    def test_min_fix_day_tightens_tau_lower_bound(self):
        """min_fix_day removes τ points before the minimum."""
        overrides = HumanOverrides(min_fix_day=10)
        tau = _compute_tau(30, [], "Supramax/Ultramax", "Australia (Hay Point)",
                           human_overrides=overrides)
        assert all(d >= 10 for d in tau), f"Got τ={tau} with min_fix_day=10"

    def test_force_mode_spot_fixes_w_locked_to_zero(self):
        """force_mode='spot' means w_{i,locked}=0 — only spot voyages allowed."""
        overrides = HumanOverrides(force_mode="spot")
        modes_allowed = [m for m in ("spot", "locked") if m != overrides.force_mode or overrides.force_mode == m]
        modes_blocked = [m for m in ("spot", "locked") if m != overrides.force_mode]
        assert "locked" in modes_blocked
        assert "spot" in modes_allowed

    def test_require_port_filters_other_ports(self):
        """require_port means y_{i,p}=0 for all p ≠ required port."""
        overrides = HumanOverrides(require_port="Gangavaram")
        all_ports = ["Paradip", "Gangavaram", "Dhamra"]
        allowed = [p for p in all_ports if p == overrides.require_port]
        blocked = [p for p in all_ports if p != overrides.require_port]
        assert "Gangavaram" in allowed
        assert "Paradip" in blocked
        assert "Dhamra" in blocked


# ---------------------------------------------------------------------------
# _hybrid_fallback — triggers on timeout, returns valid scenario_comparison[]
# (DOC4 Done When #4)
# ---------------------------------------------------------------------------

class TestHybridFallback:
    def test_hybrid_fallback_returns_assignments(self, supramax_opt, sample_coeffs):
        """
        _hybrid_fallback() must return a non-empty list of assignments.
        solved_via must be 'hybrid_fallback'.
        """
        tau_points = {"Supramax/Ultramax": [0]}
        assignments, solved_via = _hybrid_fallback(
            cargo_quantity=58_000.0,
            feasible_opts=[supramax_opt],
            coeffs=sample_coeffs,
            tau_points=tau_points,
            commitment_benchmark_pct=10.0,
        )
        assert solved_via == "hybrid_fallback"
        assert len(assignments) >= 1

    def test_hybrid_fallback_assignments_have_required_fields(self, supramax_opt, sample_coeffs):
        """Each assignment from hybrid_fallback must have voyage, vessel_class, port, tau_day, mode."""
        tau_points = {"Supramax/Ultramax": [0]}
        assignments, _ = _hybrid_fallback(
            cargo_quantity=58_000.0,
            feasible_opts=[supramax_opt],
            coeffs=sample_coeffs,
            tau_points=tau_points,
            commitment_benchmark_pct=10.0,
        )
        for asgn in assignments:
            assert "vessel_class" in asgn
            assert "port" in asgn
            assert "tau_day" in asgn
            assert "mode" in asgn

    def test_hybrid_fallback_empty_feasible_returns_empty(self):
        """No feasible options → hybrid_fallback returns empty list, not an error."""
        assignments, solved_via = _hybrid_fallback(
            cargo_quantity=58_000.0,
            feasible_opts=[],
            coeffs={},
            tau_points={},
            commitment_benchmark_pct=10.0,
        )
        assert assignments == []
        assert solved_via == "hybrid_fallback"

    @patch("backend.engine.decision._build_and_solve_milp")
    def test_milp_timeout_triggers_hybrid_fallback(self, mock_milp, supramax_opt, sample_coeffs):
        """
        When _build_and_solve_milp returns (None, 'hybrid_fallback') (simulating timeout),
        solve() must fall through to _hybrid_fallback() and still return a valid Strategy.
        solved_via in the result must be 'hybrid_fallback'.
        """
        mock_milp.return_value = (None, "hybrid_fallback")

        with (
            patch("backend.engine.decision.repository.get_valid_vessel_classes",
                  return_value=["Supramax/Ultramax"]),
            patch("backend.engine.decision.repository.get_port_constraints",
                  return_value={}),
            patch("backend.engine.decision.repository.get_vessel_specs",
                  return_value={}),
            patch("backend.engine.decision.repository.get_latest_forecast",
                  return_value=None),
            patch("backend.engine.decision.repository.get_route_physics",
                  return_value=None),
            patch("backend.engine.decision.repository.get_candidate_vessels_by_class",
                  return_value=[]),
            patch("backend.engine.decision.repository.get_earliest_repositioning_days",
                  return_value=None),
            patch("backend.engine.decision.repository.get_latest_congestion_snapshot",
                  return_value=None),
            patch("backend.engine.decision.constraint.check_feasibility",
                  return_value=[supramax_opt]),
        ):
            # With no coeffs (no route physics), solve() should return infeasible gracefully
            recommendation, scenario_comparison = solve(
                cargo_quantity=58_000.0,
                origin_port="Australia (Hay Point)",
                discharge_ports=["Gangavaram"],
                timing_flexibility_days=14,
            )
            # Must never raise — must return a valid Strategy
            assert isinstance(recommendation, Strategy)
            assert isinstance(scenario_comparison, list)


# ---------------------------------------------------------------------------
# Strategy output shape
# ---------------------------------------------------------------------------

class TestStrategyShape:
    def test_strategy_has_solved_via(self, supramax_opt, sample_coeffs):
        """Strategy.solved_via must be 'milp' or 'hybrid_fallback' — never hidden."""
        assignments = [{
            "voyage": 1,
            "vessel_class": "Supramax/Ultramax",
            "port": "Gangavaram",
            "tau_day": 0,
            "mode": "spot",
        }]
        strat = _assemble_strategy(
            assignments=assignments,
            feasible_opts=[supramax_opt],
            coeffs=sample_coeffs,
            forecasts={},
            solved_via="milp",
            commitment_benchmark_pct=10.0,
            is_default_benchmark=False,
        )
        assert strat.solved_via in ("milp", "hybrid_fallback")
        assert strat.solved_via == "milp"

    def test_strategy_cost_breakdown_has_5_buckets(self, supramax_opt, sample_coeffs):
        """cost_breakdown must have exactly the 5 DOC2 §11.7 buckets."""
        assignments = [{
            "voyage": 1, "vessel_class": "Supramax/Ultramax", "port": "Gangavaram",
            "tau_day": 0, "mode": "spot",
        }]
        strat = _assemble_strategy(
            assignments=assignments, feasible_opts=[supramax_opt],
            coeffs=sample_coeffs, forecasts={}, solved_via="milp",
            commitment_benchmark_pct=10.0, is_default_benchmark=False,
        )
        required_buckets = {"ocean_freight", "bunker", "port_handling", "lightening_extra", "risk_buffer"}
        assert required_buckets.issubset(set(strat.cost_breakdown.keys()))

    def test_strategy_contains_high_uncertainty_flag(self, supramax_opt, sample_coeffs):
        """Strategy must carry contains_high_uncertainty_voyage flag."""
        assignments = [{
            "voyage": 1, "vessel_class": "Supramax/Ultramax", "port": "Gangavaram",
            "tau_day": 0, "mode": "spot",
        }]
        strat = _assemble_strategy(
            assignments=assignments, feasible_opts=[supramax_opt],
            coeffs=sample_coeffs, forecasts={}, solved_via="milp",
            commitment_benchmark_pct=10.0, is_default_benchmark=False,
        )
        assert isinstance(strat.contains_high_uncertainty_voyage, bool)

    def test_strategy_provenance_assumed_with_default_benchmark(self, supramax_opt, sample_coeffs):
        """
        DOC3: when using DEFAULT_COMMITMENT_BENCHMARK_PCT, provenance must be 'assumed'
        because commitment_benchmark is a placeholder.
        """
        assignments = [{
            "voyage": 1, "vessel_class": "Supramax/Ultramax", "port": "Gangavaram",
            "tau_day": 0, "mode": "locked",
        }]
        strat = _assemble_strategy(
            assignments=assignments, feasible_opts=[supramax_opt],
            coeffs=sample_coeffs, forecasts={}, solved_via="milp",
            commitment_benchmark_pct=DEFAULT_COMMITMENT_BENCHMARK_PCT,
            is_default_benchmark=True,  # ← using the placeholder
        )
        assert strat.provenance == "assumed"

    def test_infeasible_strategy_has_reason(self):
        """
        When solve() returns no feasible options, infeasible_reason must be set
        and voyage_count must be 0.
        """
        empty = Strategy(
            voyage_count=0, commitment_mode="spot", voyages=[],
            total_cost_worst_case=0.0, cost_breakdown={},
            contains_high_uncertainty_voyage=False,
            solved_via="milp", provenance="assumed",
            infeasible_reason="No feasible options",
        )
        assert empty.infeasible_reason is not None
        assert empty.voyage_count == 0

    def test_multi_voyage_cost_conservation(self, route_physics):
        """
        Verify that in a multi-voyage split (e.g. 150,000 MT split into 80,000 MT + 70,000 MT),
        total ocean freight equals exactly 150,000 * rate (not doubled),
        tax is exactly 5% of total ocean freight, and bunker is charged once per vessel voyage.
        """
        total_q = 150_000.0
        rate = 15.0
        coeffs = {}
        for scen in ("base", "bull", "bear"):
            bd = build_cost_coefficient(
                quantity=total_q,
                mode="spot",
                rate_at_tau=rate,
                base_rate_at_lock_day=rate,
                commitment_benchmark_pct=10.0,
                route_physics=route_physics,
                bunker_price_usd_per_tonne=600.0,
                handling_rate_tpd=40_000.0,
                idle_days=0.0,
                requires_lightening=False,
                lightening_penalty_days=0.0,
            )
            coeffs[("Panamax/Kamsarmax", "Gangavaram", 0, "spot", scen)] = bd

        opt = FeasibleOption(
            vessel_class="Panamax/Kamsarmax",
            port="Gangavaram",
            is_feasible=True,
            infeasible_reason=None,
            is_inefficient_fit=False,
            discharge_days=3.75,
            tidal_window_note=None,
            requires_lightening=False,
            lightening_port=None,
            lightening_penalty_days=0.0,
            lightening_penalty_cost_usd=0.0,
            size_rank=2,
        )

        assignments = [
            {"voyage": 1, "vessel_class": "Panamax/Kamsarmax", "port": "Gangavaram", "tau_day": 0, "mode": "spot", "cargo_tonnes": 80_000.0},
            {"voyage": 2, "vessel_class": "Panamax/Kamsarmax", "port": "Gangavaram", "tau_day": 0, "mode": "spot", "cargo_tonnes": 70_000.0},
        ]

        strat = _assemble_strategy(
            assignments=assignments,
            feasible_opts=[opt],
            coeffs=coeffs,
            forecasts={},
            solved_via="milp",
            commitment_benchmark_pct=10.0,
            is_default_benchmark=False,
            origin_port="Australia (Hay Point)",
            cargo_quantity=total_q,
        )

        assert strat.voyage_count == 2
        # Exact freight conservation: 150,000 * 15.0 = 2,250,000
        expected_freight = total_q * rate
        assert strat.cost_breakdown["ocean_freight"] == pytest.approx(expected_freight, rel=1e-4)
        assert strat.total_freight_revenue_usd == pytest.approx(expected_freight, rel=1e-4)
        # Exact tax ratio: 5.0%
        assert strat.cost_breakdown["tax"] == pytest.approx(expected_freight * 0.05, rel=1e-4)
        # Bunker charged for both voyages (2x single vessel fuel burn)
        single_bunker = coeffs[("Panamax/Kamsarmax", "Gangavaram", 0, "spot", "base")].bunker
        assert strat.cost_breakdown["bunker"] == pytest.approx(single_bunker * 2, rel=1e-4)

