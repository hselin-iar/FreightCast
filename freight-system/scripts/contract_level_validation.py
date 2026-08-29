#!/usr/bin/env python3
"""
contract_level_validation.py — Contract-by-contract comparative validation.
Compares the 6 selected contracts from step51v_final_solution.csv with production engine.
"""

import sys
from pathlib import Path
import pandas as pd

PROD_ROOT = Path(__file__).resolve().parent.parent
RESEARCH_ROOT = PROD_ROOT.parent / "freight_optimization"
sys.path.insert(0, str(PROD_ROOT))

from backend.warehouse import repository
from backend.engine import cost_terms

def compare_contracts():
    research_sol_path = RESEARCH_ROOT / "outputs" / "step51v_final_solution.csv"
    if not research_sol_path.exists():
        print("Research final solution CSV not found.")
        return

    df = pd.read_csv(research_sol_path)
    print("=" * 100)
    print(f"{'CONTRACT':<14} | {'ORIGIN -> DEST':<40} | {'CLASS':<10} | {'RESEARCH COST':<15} | {'PROD COST':<15} | {'DELTA %':<8}")
    print("=" * 100)

    for _, row in df.iterrows():
        cid = row["contract_id"]
        origin = row["origin"]
        dest = row["destination"]
        vol = float(row["contract_volume_mt"])
        bunker_p = float(row["bunker_price_usd_per_mt"])
        res_total = float(row["total_voyage_cost_usd"])
        res_bunker = float(row["bunker_cost_usd"])
        res_opex = float(row["opex_cost_live_usd"])
        
        # Clean route names to match DB
        orig_clean = "Australia (Hay Point)" if "Australia" in origin or "Queensland" in origin else ("Indonesia (East Kalimantan)" if "Indonesia" in origin else "South Africa (Richards Bay)")
        dest_clean = "Paradip" if "Paradip" in dest else ("Gangavaram" if "Visakhapatnam" in dest or "East Coast India" in dest else "Dhamra")
        
        rp = repository.get_route_physics(orig_clean, dest_clean)
        if not rp:
            continue
            
        rate = float(row["base_rate"])
        prod_cb = cost_terms.build_cost_coefficient(
            quantity=vol,
            mode="spot",
            rate_at_tau=rate,
            base_rate_at_lock_day=rate,
            commitment_benchmark_pct=0.0,
            route_physics=rp,
            bunker_price_usd_per_tonne=bunker_p,
            handling_rate_tpd=40000.0,
            idle_days=0.0,
            requires_lightening=False,
            lightening_penalty_days=0.0,
        )
        
        # Operational voyage costs (Bunker + OPEX + Port + Other)
        prod_voyage_cost = prod_cb.bunker + prod_cb.opex + prod_cb.port_handling + prod_cb.other_cost
        delta_pct = ((prod_voyage_cost - res_total) / res_total) * 100.0
        
        route_str = f"{orig_clean.split(' ')[0]} -> {dest_clean}"
        print(f"{cid:<14} | {route_str:<40} | {row['vessel_class']:<10} | ${res_total:>13,.2f} | ${prod_voyage_cost:>13,.2f} | {delta_pct:>+7.2f}%")

    print("=" * 100)

if __name__ == "__main__":
    compare_contracts()
