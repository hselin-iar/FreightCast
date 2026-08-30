import asyncio
from backend.engine import decision, constraint
import logging

logging.basicConfig(level=logging.DEBUG)

def test():
    feasible_opts = [
        constraint.FeasibleOption(vessel_class="Capesize", port="Dhamra", discharge_days=4, tide_penalty=0),
        constraint.FeasibleOption(vessel_class="Panamax", port="Dhamra", discharge_days=2, tide_penalty=0)
    ]
    forecasts = {
        "Dhamra_Capesize": {"base": 20.0, "optimistic": 18.0, "pessimistic": 25.0, "confidence": 0.8},
        "Dhamra_Panamax": {"base": 22.0, "optimistic": 20.0, "pessimistic": 28.0, "confidence": 0.8}
    }
    route_physics = {
        ("Capesize", "Dhamra"): {"voyage_days_round_trip": 20.0},
        ("Panamax", "Dhamra"): {"voyage_days_round_trip": 22.0}
    }
    repo_cache = {
        ("Capesize", "Dhamra"): 0,
        ("Panamax", "Dhamra"): 0
    }

    try:
        recommendation, scenario_comparison = decision.solve(
            cargo_quantity=120000,
            feasible_opts=feasible_opts,
            origin_port="Hay Point",
            bunker_price=600.0,
            base_rate_at_lock=15.0,
            forecasts=forecasts,
            route_physics_cache=route_physics,
            repo_cache=repo_cache,
            commitment_benchmark_pct=10.0,
            is_default_benchmark=True,
            constraints=None
        )
        print("Recommendation sig:", "|".join(sorted(f"{v.vessel_class}-{v.port}-{v.mode}-{v.fix_day}" for v in recommendation.voyages)))
        for s in scenario_comparison:
            print("Alt sig:", "|".join(sorted(f"{v.vessel_class}-{v.port}-{v.mode}-{v.fix_day}" for v in s.voyages)))
    except Exception as e:
        import traceback
        traceback.print_exc()

test()
