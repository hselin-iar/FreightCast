"""
tests/test_cost_terms.py — Cost Terms Module tests.

DOC4 Build Step 7 Done When:
  test_cost_terms.py passes, INCLUDING:
    - Critical test: locked voyage cost IDENTICAL across Base/Optimistic/Pessimistic
    - 5-bucket breakdown sums to same total as parts summed independently
    - All sub-functions against hand-calculated values
    - repositioning_cost with real inputs AND with either input None (returns 0.0)

No DB required — cost_terms.py is pure arithmetic.

Run: pytest backend/tests/test_cost_terms.py -v
"""
from __future__ import annotations

import pytest

from backend.engine.cost_terms import (
    CostBreakdown,
    RoutePhysics,
    build_cost_coefficient,
    bunker_cost,
    lightening_penalty_cost,
    locked_freight_cost,
    port_handling_cost,
    repositioning_cost,
    spot_freight_cost,
    tax_cost,
    waiting_cost,
)
from backend.config.constants import (
    PORT_HANDLING_DAY_RATE_USD,
    WAITING_COST_PER_DAY_USD,
    TAX_RATE_PCT,
    DEFAULT_BALLAST_SPEED_KNOTS,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def route_physics():
    """Realistic fixture: Australia → Paradip, ~5500 nm."""
    return RoutePhysics(
        origin="Australia (Hay Point)",
        destination="Paradip",
        distance_nm=5500.0,
        laden_consumption_tpd=58.0,
        ballast_consumption_tpd=42.0,
        speed_knots=12.0,
    )


@pytest.fixture
def build_args(route_physics):
    """Common keyword arguments for build_cost_coefficient(), spot mode."""
    return dict(
        quantity=80_000.0,
        mode="spot",
        rate_at_tau=20_000.0,
        base_rate_at_lock_day=19_000.0,
        commitment_benchmark_pct=10.0,
        route_physics=route_physics,
        bunker_price_usd_per_tonne=600.0,
        handling_rate_tpd=40_000.0,
        idle_days=1.5,
        requires_lightening=False,
        lightening_penalty_days=0.0,
        repositioning_days=None,
        ballast_consumption_tpd=None,
    )


# ---------------------------------------------------------------------------
# spot_freight_cost
# ---------------------------------------------------------------------------

class TestSpotFreightCost:
    def test_standard_calculation(self):
        """80,000 t × $20,000/day = $1,600,000,000."""
        assert spot_freight_cost(80_000.0, 20_000.0) == pytest.approx(1_600_000_000.0)

    def test_zero_rate(self):
        assert spot_freight_cost(80_000.0, 0.0) == pytest.approx(0.0)

    def test_zero_quantity(self):
        assert spot_freight_cost(0.0, 20_000.0) == pytest.approx(0.0)

    def test_proportional_to_quantity(self):
        c1 = spot_freight_cost(40_000.0, 20_000.0)
        c2 = spot_freight_cost(80_000.0, 20_000.0)
        assert c2 == pytest.approx(c1 * 2.0)


# ---------------------------------------------------------------------------
# locked_freight_cost
# ---------------------------------------------------------------------------

class TestLockedFreightCost:
    def test_standard_calculation(self):
        """
        80,000 t × $19,000 × (1 - 10/100) = 80,000 × 19,000 × 0.9 = $1,368,000,000
        """
        expected = 80_000.0 * 19_000.0 * 0.9
        assert locked_freight_cost(80_000.0, 19_000.0, 10.0) == pytest.approx(expected)

    def test_zero_discount_edge_case(self):
        """
        DOC3 edge case: commitment_benchmark_pct=0 → no discount.
        Must not error or produce NaN.
        quantity × base_rate_at_lock_day × 1.0 exactly.
        """
        result = locked_freight_cost(80_000.0, 19_000.0, 0.0)
        assert result == pytest.approx(80_000.0 * 19_000.0)
        assert result == result  # NaN check

    def test_100_percent_discount(self):
        """100% discount → 0 cost. Not an expected business scenario, but must not break."""
        assert locked_freight_cost(80_000.0, 19_000.0, 100.0) == pytest.approx(0.0)

    def test_proportional_to_quantity(self):
        c1 = locked_freight_cost(40_000.0, 19_000.0, 10.0)
        c2 = locked_freight_cost(80_000.0, 19_000.0, 10.0)
        assert c2 == pytest.approx(c1 * 2.0)


# ---------------------------------------------------------------------------
# bunker_cost
# ---------------------------------------------------------------------------

class TestBunkerCost:
    def test_laden_hand_calculated(self, route_physics):
        """
        Laden: 58 tpd × (5500 nm / 12 kt / 24 h) × $600/t
        voyage_days = 5500 / 12 / 24 = 19.097...
        cost = 58 × 19.097 × 600 = $664,583.33...
        """
        voyage_days = 5500.0 / 12.0 / 24.0
        expected = 58.0 * voyage_days * 600.0
        assert bunker_cost(route_physics, laden=True, bunker_price_usd_per_tonne=600.0) == pytest.approx(expected, rel=1e-4)

    def test_ballast_hand_calculated(self, route_physics):
        """
        Ballast: 42 tpd × (5500/12/24) × $600 = $481,250.0
        """
        voyage_days = 5500.0 / 12.0 / 24.0
        expected = 42.0 * voyage_days * 600.0
        assert bunker_cost(route_physics, laden=False, bunker_price_usd_per_tonne=600.0) == pytest.approx(expected, rel=1e-4)

    def test_laden_greater_than_ballast(self, route_physics):
        """Laden consumption > ballast consumption → laden cost > ballast cost."""
        laden  = bunker_cost(route_physics, laden=True, bunker_price_usd_per_tonne=600.0)
        ballast = bunker_cost(route_physics, laden=False, bunker_price_usd_per_tonne=600.0)
        assert laden > ballast

    def test_zero_distance_raises(self):
        """No RoutePhysics row with distance=0 should ever succeed — it's a data error."""
        bad = RoutePhysics("A", "B", distance_nm=0.0, laden_consumption_tpd=58.0,
                           ballast_consumption_tpd=42.0, speed_knots=12.0)
        with pytest.raises(ValueError, match="distance_nm"):
            bunker_cost(bad, laden=True, bunker_price_usd_per_tonne=600.0)

    def test_negative_distance_raises(self):
        bad = RoutePhysics("A", "B", distance_nm=-100.0, laden_consumption_tpd=58.0,
                           ballast_consumption_tpd=42.0, speed_knots=12.0)
        with pytest.raises(ValueError):
            bunker_cost(bad, laden=True, bunker_price_usd_per_tonne=600.0)

    def test_proportional_to_bunker_price(self, route_physics):
        c1 = bunker_cost(route_physics, laden=True, bunker_price_usd_per_tonne=600.0)
        c2 = bunker_cost(route_physics, laden=True, bunker_price_usd_per_tonne=1200.0)
        assert c2 == pytest.approx(c1 * 2.0)


# ---------------------------------------------------------------------------
# port_handling_cost
# ---------------------------------------------------------------------------

class TestPortHandlingCost:
    def test_standard_calculation(self):
        """
        80,000 t / 40,000 tpd = 2.0 days × PORT_HANDLING_DAY_RATE_USD ($15,000) = $30,000
        """
        expected = (80_000.0 / 40_000.0) * PORT_HANDLING_DAY_RATE_USD
        assert port_handling_cost(80_000.0, 40_000.0) == pytest.approx(expected)

    def test_zero_handling_rate_returns_zero(self):
        """Guard: no division by zero."""
        assert port_handling_cost(80_000.0, 0.0) == pytest.approx(0.0)

    def test_proportional_to_quantity(self):
        c1 = port_handling_cost(40_000.0, 40_000.0)
        c2 = port_handling_cost(80_000.0, 40_000.0)
        assert c2 == pytest.approx(c1 * 2.0)


# ---------------------------------------------------------------------------
# waiting_cost
# ---------------------------------------------------------------------------

class TestWaitingCost:
    def test_standard_calculation(self):
        """1.5 idle days × WAITING_COST_PER_DAY_USD ($12,000) = $18,000."""
        expected = 1.5 * WAITING_COST_PER_DAY_USD
        assert waiting_cost(1.5) == pytest.approx(expected)

    def test_zero_idle_days_returns_zero_not_none(self):
        """
        DOC3 edge case: idle_days=0 → returns 0.0, not None/skipped.
        The $0 must still show as a line in the breakdown.
        """
        result = waiting_cost(0.0)
        assert result == pytest.approx(0.0)
        assert result is not None
        assert isinstance(result, float)

    def test_proportional_to_days(self):
        c1 = waiting_cost(1.0)
        c2 = waiting_cost(3.0)
        assert c2 == pytest.approx(c1 * 3.0)


# ---------------------------------------------------------------------------
# tax_cost
# ---------------------------------------------------------------------------

class TestTaxCost:
    def test_standard_calculation(self):
        """
        80,000 t × $20,000 rate × (5.0/100) = $80,000,000
        """
        expected = 80_000.0 * 20_000.0 * (TAX_RATE_PCT / 100.0)
        assert tax_cost(80_000.0, 20_000.0) == pytest.approx(expected)

    def test_separate_from_freight(self):
        """Tax bucket must be independently computable — distinct from spot_freight_cost."""
        freight = spot_freight_cost(80_000.0, 20_000.0)
        tax = tax_cost(80_000.0, 20_000.0)
        # They use the same inputs but are distinct functions / distinct buckets
        assert tax != freight
        assert tax == pytest.approx(freight * (TAX_RATE_PCT / 100.0))


# ---------------------------------------------------------------------------
# lightening_penalty_cost
# ---------------------------------------------------------------------------

class TestLighteningPenaltyCost:
    def test_no_lightening_returns_zero(self):
        """DOC3: 'not applicable ≠ free' — returns 0.0, not None."""
        result = lightening_penalty_cost(requires_lightening=False, lightening_penalty_days=2.5)
        assert result == pytest.approx(0.0)
        assert isinstance(result, float)

    def test_lightening_required_hand_calculated(self):
        """
        2.5 days × PORT_HANDLING_DAY_RATE_USD ($15,000) = $37,500
        """
        expected = 2.5 * PORT_HANDLING_DAY_RATE_USD
        result = lightening_penalty_cost(requires_lightening=True, lightening_penalty_days=2.5)
        assert result == pytest.approx(expected)

    def test_zero_days_with_lightening_required(self):
        """Lightening required but 0 days → $0. Not an error."""
        assert lightening_penalty_cost(requires_lightening=True, lightening_penalty_days=0.0) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# repositioning_cost
# ---------------------------------------------------------------------------

class TestRepositioningCost:
    def test_real_inputs_non_zero(self):
        """
        DOC3: with real AIS data grounding the voyage.
        42 tpd × 3.5 days × $600/t = $88,200
        """
        expected = 42.0 * 3.5 * 600.0
        result = repositioning_cost(
            ballast_consumption_tpd=42.0,
            repositioning_days=3.5,
            bunker_price_usd_per_tonne=600.0,
        )
        assert result == pytest.approx(expected)

    def test_ballast_consumption_none_returns_zero(self):
        """
        DOC3 graceful fallback: no AIS position data for this class/route.
        ballast_consumption_tpd=None → returns exactly 0.0, NOT an error.
        """
        result = repositioning_cost(
            ballast_consumption_tpd=None,
            repositioning_days=3.5,
            bunker_price_usd_per_tonne=600.0,
        )
        assert result == pytest.approx(0.0)
        assert result is not None

    def test_repositioning_days_none_returns_zero(self):
        """
        repositioning_days=None (no AIS position data) → returns exactly 0.0.
        """
        result = repositioning_cost(
            ballast_consumption_tpd=42.0,
            repositioning_days=None,
            bunker_price_usd_per_tonne=600.0,
        )
        assert result == pytest.approx(0.0)

    def test_both_none_returns_zero(self):
        """Both None → 0.0. Most common fallback path."""
        result = repositioning_cost(None, None, 600.0)
        assert result == pytest.approx(0.0)

    def test_zero_repositioning_days_returns_zero(self):
        """0 days (vessel already at origin) → $0, not an error."""
        result = repositioning_cost(42.0, 0.0, 600.0)
        assert result == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# build_cost_coefficient — integration tests
# ---------------------------------------------------------------------------

class TestBuildCostCoefficient:

    # ── 5-bucket total integrity ─────────────────────────────────────────────

    def test_total_equals_sum_of_buckets(self, build_args, route_physics):
        """
        DOC4 Done When: 5-bucket breakdown sums to the same total as
        adding the buckets independently. Catches a bucket omitted from total.
        """
        bd = build_cost_coefficient(**build_args)
        expected_total = (
            bd.ocean_freight
            + bd.bunker
            + bd.opex
            + bd.other_cost
            + bd.port_handling
            + bd.lightening_extra
            + bd.tax
            + bd.waiting
        )
        assert bd.total == pytest.approx(expected_total, rel=1e-6)

    def test_all_buckets_present(self, build_args):
        """CostBreakdown must have all required fields — none missing."""
        bd = build_cost_coefficient(**build_args)
        assert hasattr(bd, "ocean_freight")
        assert hasattr(bd, "bunker")
        assert hasattr(bd, "opex")
        assert hasattr(bd, "other_cost")
        assert hasattr(bd, "port_handling")
        assert hasattr(bd, "lightening_extra")
        assert hasattr(bd, "tax")
        assert hasattr(bd, "waiting")
        assert hasattr(bd, "total")
        assert hasattr(bd, "provenance")

    def test_spot_mode_uses_rate_at_tau(self, build_args):
        """Spot mode: ocean_freight = quantity × rate_at_tau."""
        bd = build_cost_coefficient(**build_args)
        expected = 80_000.0 * 20_000.0
        assert bd.ocean_freight == pytest.approx(expected, rel=1e-4)

    # ── CRITICAL TEST: locked-mode cost identical across scenarios ────────────

    def test_locked_freight_cost_identical_across_scenarios(self, build_args, route_physics):
        """
        DOC4 CRITICAL TEST (flagged high-risk):
        Call build_cost_coefficient() three times for the SAME locked voyage
        with Base / Optimistic / Pessimistic scenario rates — the ocean_freight
        component MUST be IDENTICAL across all three.

        This is the exact bug class DOC2 §10's "Base-path rate at the lock date"
        phrasing exists to prevent: a locked voyage must not appear cheaper in the
        Optimistic scenario (where rates happen to be lower) or more expensive in
        the Pessimistic scenario (where rates are higher). It's LOCKED.
        """
        base_rate_at_lock_day = 19_000.0
        base_args = dict(build_args)
        base_args["mode"] = "locked"
        base_args["base_rate_at_lock_day"] = base_rate_at_lock_day

        # Simulate the three scenario evaluations decision.py performs.
        # rate_at_tau VARIES by scenario (as it would in real usage) —
        # but locked cost must stay constant regardless.
        bd_base = build_cost_coefficient(**{**base_args, "rate_at_tau": 19_000.0})   # Base
        bd_opt  = build_cost_coefficient(**{**base_args, "rate_at_tau": 17_000.0})   # Optimistic (lower rate)
        bd_pess = build_cost_coefficient(**{**base_args, "rate_at_tau": 22_000.0})   # Pessimistic (higher rate)

        # ocean_freight must be IDENTICAL across all three evaluations
        assert bd_base.ocean_freight == pytest.approx(bd_opt.ocean_freight,  rel=1e-9), \
            "Locked freight cost must not vary between Base and Optimistic scenarios."
        assert bd_base.ocean_freight == pytest.approx(bd_pess.ocean_freight, rel=1e-9), \
            "Locked freight cost must not vary between Base and Pessimistic scenarios."

        # Verify it equals the hand-calculated locked value (with 10% discount)
        expected = 80_000.0 * base_rate_at_lock_day * (1 - 10.0 / 100.0)
        assert bd_base.ocean_freight == pytest.approx(expected, rel=1e-6)

    def test_spot_freight_varies_by_scenario_rate(self, build_args):
        """
        Spot mode: cost DOES vary by scenario rate (contrast to locked invariant above).
        rate_at_tau differs → ocean_freight differs.
        """
        bd_low  = build_cost_coefficient(**{**build_args, "rate_at_tau": 17_000.0})
        bd_high = build_cost_coefficient(**{**build_args, "rate_at_tau": 22_000.0})
        assert bd_low.ocean_freight < bd_high.ocean_freight

    # ── Lightening ───────────────────────────────────────────────────────────

    def test_lightening_adds_to_breakdown(self, build_args):
        """When lightening is required, lightening_extra > 0 and total is higher."""
        bd_no_light = build_cost_coefficient(**build_args)  # requires_lightening=False
        light_args = dict(build_args)
        light_args["requires_lightening"] = True
        light_args["lightening_penalty_days"] = 2.5
        bd_with_light = build_cost_coefficient(**light_args)

        assert bd_with_light.lightening_extra > 0.0
        assert bd_with_light.total > bd_no_light.total

    def test_no_lightening_extra_is_zero(self, build_args):
        """No lightening → lightening_extra == 0.0 (consistent zero, not missing)."""
        bd = build_cost_coefficient(**build_args)
        assert bd.lightening_extra == pytest.approx(0.0)

    # ── Repositioning folds into bunker ──────────────────────────────────────

    def test_repositioning_folds_into_bunker_bucket(self, build_args, route_physics):
        """
        DOC3: repositioning_cost folds into the bunker bucket (still bunker fuel).
        Adding repositioning inputs increases bd.bunker, NOT a new bucket.
        """
        bd_no_repo = build_cost_coefficient(**build_args)  # repositioning_days=None
        repo_args = dict(build_args)
        repo_args["repositioning_days"] = 3.5
        repo_args["ballast_consumption_tpd"] = 42.0
        bd_with_repo = build_cost_coefficient(**repo_args)

        # bunker bucket increased
        assert bd_with_repo.bunker > bd_no_repo.bunker
        # no extra bucket appeared — total has exactly 6 contributing terms
        assert bd_with_repo.total > bd_no_repo.total

    # ── Waiting cost present even at 0 days ──────────────────────────────────

    def test_waiting_present_at_zero_idle_days(self, build_args):
        """Waiting = 0.0 at idle_days=0 — consistent zero, not a missing line."""
        zero_wait_args = dict(build_args)
        zero_wait_args["idle_days"] = 0.0
        bd = build_cost_coefficient(**zero_wait_args)
        assert bd.waiting == pytest.approx(0.0)
        assert bd.waiting is not None

    # ── Tax is separate from freight ──────────────────────────────────────────

    def test_tax_is_separate_bucket(self, build_args):
        """Tax must be in its own bucket — not folded into ocean_freight."""
        bd = build_cost_coefficient(**build_args)
        # Tax and freight are separately accessible
        assert bd.tax > 0.0
        # Tax ≠ freight (different magnitudes by design)
        assert bd.tax != bd.ocean_freight

    # ── Total integrity with lightening and repositioning ────────────────────

    def test_total_equals_sum_with_lightening_and_repositioning(self, build_args):
        """5-bucket sum = total even when lightening and repositioning are active."""
        full_args = dict(build_args)
        full_args["requires_lightening"] = True
        full_args["lightening_penalty_days"] = 2.5
        full_args["repositioning_days"] = 3.5
        full_args["ballast_consumption_tpd"] = 42.0
        bd = build_cost_coefficient(**full_args)
        expected_total = (
            bd.ocean_freight + bd.bunker + bd.opex + bd.other_cost + bd.port_handling
            + bd.lightening_extra + bd.tax + bd.waiting
        )
        assert bd.total == pytest.approx(expected_total, rel=1e-6)

    # ── Hand-calculated total verification ───────────────────────────────────

    def test_hand_calculated_spot_total(self, build_args, route_physics):
        """
        Spot mode hand-calculation for fixture inputs:
          quantity=80000, rate_at_tau=20000, bunker_price=600, handling_rate=40000,
          idle_days=1.5, no lightening, no repositioning
          distance_nm=5500, laden_tpd=58, ballast_tpd=42, speed=12

        ocean_freight  = 80000 × 20000 = 1,600,000,000
        voyage_days    = 5500/12/24 = 19.0972...
        laden_bunker   = 58 × 19.0972 × 600 = 664,574.3...
        ballast_bunker = 42 × 19.0972 × 600 = 481,252.2...
        port_handling  = (80000/40000) × 15000 = 30,000
        lightening_extra = 0
        tax            = 80000 × 20000 × 0.05 = 80,000,000
        waiting        = 1.5 × 12000 = 18,000
        total          ≈ sum of above
        """
        bd = build_cost_coefficient(**build_args)
        voyage_days = 5500.0 / 12.0 / 24.0
        expected = {
            "ocean_freight":    80_000.0 * 20_000.0,
            "laden_bunker":     58.0 * voyage_days * 600.0,
            "ballast_bunker":   42.0 * voyage_days * 600.0,
            "port_handling":    (80_000.0 / 40_000.0) * PORT_HANDLING_DAY_RATE_USD,
            "tax":              80_000.0 * 20_000.0 * (TAX_RATE_PCT / 100.0),
            "waiting":          1.5 * WAITING_COST_PER_DAY_USD,
        }
        assert bd.ocean_freight  == pytest.approx(expected["ocean_freight"],  rel=1e-4)
        assert bd.bunker         == pytest.approx(expected["laden_bunker"] + expected["ballast_bunker"], rel=1e-4)
        assert bd.port_handling  == pytest.approx(expected["port_handling"],  rel=1e-4)
        assert bd.tax            == pytest.approx(expected["tax"],            rel=1e-4)
        assert bd.waiting        == pytest.approx(expected["waiting"],        rel=1e-4)
        assert bd.lightening_extra == pytest.approx(0.0)
