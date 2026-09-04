"""
backend/tests/test_steaming_speed.py

Tests for discrete steaming speeds and cubic fuel consumption power law in engine/cost_terms.py.
"""
import pytest
from backend.engine.cost_terms import (
    bunker_cost,
    opex_cost,
    build_cost_coefficient,
    RoutePhysics,
    STEAMING_SPEEDS,
)


@pytest.fixture
def sample_route_physics():
    return RoutePhysics(
        origin="Australia (Hay Point)",
        destination="Paradip",
        distance_nm=4850.0,
        laden_consumption_tpd=55.0,
        ballast_consumption_tpd=40.0,
        speed_knots=12.5,
        daily_opex_usd=8500.0,
        other_voyage_cost_usd=12000.0,
    )


def test_cubic_bunker_consumption(sample_route_physics):
    bunker_price = 600.0

    eco_cost = bunker_cost(sample_route_physics, laden=True, bunker_price_usd_per_tonne=bunker_price, speed_mode="eco")
    design_cost = bunker_cost(sample_route_physics, laden=True, bunker_price_usd_per_tonne=bunker_price, speed_mode="design")
    express_cost = bunker_cost(sample_route_physics, laden=True, bunker_price_usd_per_tonne=bunker_price, speed_mode="express")

    # Eco speed (11.5 kn) burns less total fuel than Design (12.5 kn)
    # Ratio: (11.5/12.5)^3 * (12.5/11.5) = (11.5/12.5)^2 = 0.8464 (saves ~15.4% fuel over the trip)
    assert eco_cost < design_cost
    assert express_cost > design_cost
    savings_pct = (design_cost - eco_cost) / design_cost
    assert 0.14 < savings_pct < 0.17


def test_build_cost_coefficient_speed_attributes(sample_route_physics):
    bd = build_cost_coefficient(
        quantity=150000.0,
        mode="spot",
        rate_at_tau=15.0,
        base_rate_at_lock_day=15.0,
        commitment_benchmark_pct=70.0,
        route_physics=sample_route_physics,
        bunker_price_usd_per_tonne=600.0,
        handling_rate_tpd=40000.0,
        idle_days=0.0,
        requires_lightening=False,
        lightening_penalty_days=0.0,
        speed_mode="eco",
    )
    assert bd.steaming_speed_knots == 11.5
    assert bd.steaming_mode == "eco"
    assert bd.speed_bunker_savings_usd > 0.0
