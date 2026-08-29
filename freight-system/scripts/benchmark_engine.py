import os
import sys
import logging
from datetime import datetime, timezone

os.environ.setdefault("DATABASE_URL", "sqlite:///freight_dev.db")
from backend.warehouse import repository
from backend.engine import forecasting, decision, constraint
from backend.warehouse.db import get_session

def evaluate_models():
    print("==================================================")
    print(" FORECASTING MODEL BENCHMARK (Production Engine)")
    print("==================================================")
    routes = repository.get_valid_routes()
    if not routes:
        print("No routes found in warehouse.")
        return
    
    route = 'Australia (Hay Point)→Paradip'
    vessel_class = 'Capesize'
    
    history = repository.get_rate_history(route, vessel_class, limit=300)
    if not history or len(history) < 30:
        print(f"Not enough history for {route} {vessel_class}")
        return
        
    print(f"Loaded {len(history)} historical data points for {route} ({vessel_class}).")
    
    # Retrieve the latest forecast object which contains the winning model
    fc = repository.get_latest_forecast(route, vessel_class, 14)
    if fc:
        print(f"\nWinning Model from Database: {fc.model_used}")
        print(f"  Point Estimate: ${fc.point_estimate:.2f}/MT")
        band = fc.confidence_band_dict()
        print(f"  Confidence Interval: [${band.get('lower', 0):.2f}, ${band.get('upper', 0):.2f}]")
        print(f"  Provenance: {fc.provenance}")
    else:
        print("\nNo forecast found in DB for this route.")

    # Re-evaluate manually
    try:
        from backend.engine.forecasting import _load_rate_history_with_dates, _select_best_model, _load_rate_history
        hist_list = _load_rate_history(route, vessel_class)
        if hist_list:
            df = _load_rate_history_with_dates(route, vessel_class)
            best_name, best_obj, metrics, fallback = _select_best_model(df, vessel_class)
            print("\nModel Pipeline Evaluation (MAE on 20% holdout):")
            for m_name, mae in metrics.items():
                print(f"  - {m_name.ljust(10)} : MAE = ${mae:.2f}/MT")
            print(f"\nRe-evaluated Best Model: {best_name} (Fallback used: {fallback})")
    except Exception as e:
        print(f"Error during re-evaluation: {e}")


def evaluate_milp_scenarios():
    print("\n==================================================")
    print(" MILP OPTIMIZER BENCHMARK (Production vs Research Patterns)")
    print("==================================================")
    
    scenarios = [
        {
            "name": "Single Voyage - Fixed Dates",
            "cargo": 120000,
            "origin": "Australia (Hay Point)",
            "dest": ["Gangavaram"],
            "flex": 0,
        },
        {
            "name": "Single Voyage - Flexible Dates",
            "cargo": 120000,
            "origin": "Australia (Hay Point)",
            "dest": ["Gangavaram"],
            "flex": 14,
        },
        {
            "name": "Multiple Voyages (Cargo Split) - Flexible Dates",
            "cargo": 280000,
            "origin": "Australia (Hay Point)",
            "dest": ["Gangavaram", "Paradip"],
            "flex": 21,
        },
        {
            "name": "Draft Constrained Port (Lightening Required)",
            "cargo": 150000,
            "origin": "Australia (Hay Point)",
            "dest": ["Haldia"], 
            "flex": 14,
        }
    ]
    
    for s in scenarios:
        print(f"\n[SCENARIO] {s['name']}")
        print(f"Cargo: {s['cargo']:,.0f} MT | Origin: {s['origin']} | Dest: {s['dest']} | Flex: {s['flex']} days")
        
        try:
            strat, alts = decision.solve(
                cargo_quantity=s['cargo'],
                origin_port=s['origin'],
                discharge_ports=s['dest'],
                timing_flexibility_days=s['flex']
            )
            
            print(f"  Solver       : {strat.solved_via}")
            print(f"  Total Cost   : ${strat.total_cost_worst_case:,.0f}")
            print(f"  Net Sail Val : ${strat.total_net_sail_value_usd:,.0f}")
            print(f"  Incr vs Kill : ${strat.incremental_vs_kill_usd:,.0f}")
            print(f"  Voyages ({strat.voyage_count}):")
            for v in strat.voyages:
                print(f"    - {v.vessel_class} to {v.port} @ Day {v.fix_day} ({v.mode}) | Cost: ${v.voyage_cost_usd:,.0f} | Lightening: {v.lightening_required}")
                if v.lightening_required:
                    print(f"      (Lightened at {v.lightening_port})")
        except Exception as e:
            print(f"  ERROR: {e}")

if __name__ == "__main__":
    evaluate_models()
    evaluate_milp_scenarios()
