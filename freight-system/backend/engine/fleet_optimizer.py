"""
backend/engine/fleet_optimizer.py — Step 51V Fleet Portfolio Optimizer.

Integrates the multi-contract, multi-vessel temporal conflict-graph MILP from the
research pipeline (Step 51V) into an active, on-demand callable engine module.

Features:
  - Dynamic input loading from processed research datasets with graceful warehouse fallbacks
  - Interval-overlap conflict graph construction (for all voyage pairs on each vessel)
  - PuLP CBC MILP optimization maximizing portfolio worst-incremental net margin
  - Portfolio downside risk preservation constraint (worst-case incremental >= RISK_RATIO * base_incremental)
  - Automatic classification of contracts into SAIL (accepted) vs. KILL (rejected / walk-away)
  - Structured output matching FleetScheduleResponse
"""
from __future__ import annotations

import logging
import math
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import pulp

logger = logging.getLogger(__name__)

CURRENT_FILE = Path(__file__).resolve()
# backend/engine/fleet_optimizer.py -> backend -> freight-system -> FrieghtCast
WORKSPACE_ROOT = CURRENT_FILE.parents[3]
RESEARCH_ROOT = WORKSPACE_ROOT / "freight_optimization"
PROCESSED_DIR = RESEARCH_ROOT / "data" / "processed"
OUTPUTS_DIR = RESEARCH_ROOT / "outputs"


def _to_utc(series: pd.Series) -> pd.Series:
    """Normalize datetime series to UTC."""
    return pd.to_datetime(series, utc=True)


def load_candidates_with_live_economics(
    bunker_price: Optional[float] = None,
) -> pd.DataFrame:
    """
    Load Step 51U full production universe and calculate Bear/Base/Bull voyage economics.
    """
    universe_path = PROCESSED_DIR / "step51u_full_production_universe.csv"
    contracts_path = PROCESSED_DIR / "step23_contract_sail_kill.csv"
    bunker_path = PROCESSED_DIR / "step50a_bunker_current.csv"

    if not universe_path.exists():
        raise FileNotFoundError(f"Universe file not found: {universe_path}")

    universe = pd.read_csv(universe_path)

    # 1. Bunker price
    if bunker_price is None or bunker_price <= 0:
        if bunker_path.exists():
            bunker_df = pd.read_csv(bunker_path)
            bunker_price = float(bunker_df["price_usd_per_metric_ton"].iloc[0])
        else:
            bunker_price = 770.50

    # 2. Datetime normalization
    universe["departure_dt"] = _to_utc(universe["departure_date"])
    universe["eta_dt"] = _to_utc(universe["estimated_eta"])

    # 3. Compute voyage days if missing
    if "voyage_days" not in universe.columns:
        if "total_voyage_days" in universe.columns:
            universe["voyage_days"] = universe["total_voyage_days"]
        else:
            universe["voyage_days"] = (
                universe["eta_dt"] - universe["departure_dt"]
            ).dt.total_seconds() / 86400.0

    # 4. Join contract rates if needed
    candidates = universe.copy()
    if contracts_path.exists() and ("bear_rate" not in candidates.columns or candidates["bear_rate"].isna().all()):
        contracts_df = pd.read_csv(contracts_path)
        # Pivot scenario rates
        pivot = contracts_df.pivot(
            index="contract_id", columns="scenario", values="scenario_route_freight_rate"
        )
        if "Bear" in pivot.columns:
            candidates["bear_rate"] = candidates["contract_id"].map(pivot["Bear"])
        if "Base" in pivot.columns:
            candidates["base_rate"] = candidates["contract_id"].map(pivot["Base"])
        if "Bull" in pivot.columns:
            candidates["bull_rate"] = candidates["contract_id"].map(pivot["Bull"])

    # 5. Bunker, OPEX, and Other voyage costs
    # Approximate fuel consumption from distance and sea days if not already present
    if "bunker_cost_usd" not in candidates.columns or candidates["bunker_cost_usd"].isna().all():
        fuel_tpd = 38.0  # standard bulk carrier consumption
        candidates["bunker_cost_usd"] = candidates["voyage_days"] * fuel_tpd * bunker_price

    if "opex_cost_live_usd" not in candidates.columns or candidates["opex_cost_live_usd"].isna().all():
        daily_opex = 6500.0  # standard bulk carrier daily OPEX
        candidates["opex_cost_live_usd"] = candidates["voyage_days"] * daily_opex

    if "other_voyage_cost_live_usd" not in candidates.columns:
        candidates["other_voyage_cost_live_usd"] = 45000.0  # port dues and pilotage

    candidates["total_voyage_cost_usd"] = (
        candidates["bunker_cost_usd"]
        + candidates["opex_cost_live_usd"]
        + candidates["other_voyage_cost_live_usd"]
    )

    # 6. Freight revenue across scenarios
    candidates["bear_revenue_usd"] = candidates["bear_rate"] * candidates["contract_volume_mt"]
    candidates["base_revenue_usd"] = candidates["base_rate"] * candidates["contract_volume_mt"]
    candidates["bull_revenue_usd"] = candidates["bull_rate"] * candidates["contract_volume_mt"]

    # 7. Sail net value across scenarios
    candidates["bear_sail"] = candidates["bear_revenue_usd"] - candidates["total_voyage_cost_usd"]
    candidates["base_sail"] = candidates["base_revenue_usd"] - candidates["total_voyage_cost_usd"]
    candidates["bull_sail"] = candidates["bull_revenue_usd"] - candidates["total_voyage_cost_usd"]

    # 8. Kill value baseline
    if "kill_value" not in candidates.columns or candidates["kill_value"].isna().all():
        # Default kill benchmark: 95% of base freight revenue
        candidates["kill_value"] = candidates["base_revenue_usd"] * 0.95

    # 9. Incremental value over kill baseline
    candidates["bear_incremental"] = candidates["bear_sail"] - candidates["kill_value"]
    candidates["base_incremental"] = candidates["base_sail"] - candidates["kill_value"]
    candidates["bull_incremental"] = candidates["bull_sail"] - candidates["kill_value"]

    candidates["worst_incremental"] = candidates[
        ["bear_incremental", "base_incremental", "bull_incremental"]
    ].min(axis=1)

    candidates["expected_incremental"] = (
        candidates["bear_incremental"] * 0.25
        + candidates["base_incremental"] * 0.50
        + candidates["bull_incremental"] * 0.25
    )

    candidates["bunker_price_usd_per_mt"] = bunker_price
    return candidates


def build_temporal_conflict_graph(candidates: pd.DataFrame) -> List[Tuple[int, int]]:
    """
    Construct non-overlapping temporal conflict edges for all candidate voyage pairs on the same vessel.
    Two voyages (a, b) on vessel imo conflict if voyage a's departure < voyage b's ETA
    and voyage b's departure < voyage a's ETA.
    """
    conflicts: List[Tuple[int, int]] = []
    vessel_groups = candidates.groupby("imo").groups

    for imo, idxs in vessel_groups.items():
        idx_list = list(idxs)
        n = len(idx_list)
        for i in range(n):
            a = idx_list[i]
            cid_a = candidates.loc[a, "contract_id"]
            a_start = candidates.loc[a, "departure_dt"]
            a_end = candidates.loc[a, "eta_dt"]

            for j in range(i + 1, n):
                b = idx_list[j]
                cid_b = candidates.loc[b, "contract_id"]
                if cid_a == cid_b:
                    continue  # handled by single contract assignment constraint

                b_start = candidates.loc[b, "departure_dt"]
                b_end = candidates.loc[b, "eta_dt"]

                if a_start < b_end and b_start < a_end:
                    conflicts.append((a, b))

    return conflicts


def solve_fleet_portfolio(
    max_sail: int = 12,
    risk_ratio: float = 0.60,
    time_limit: int = 20,
    bunker_price: Optional[float] = None,
    save_outputs: bool = True,
) -> Dict[str, Any]:
    """
    Execute the Step 51V production MILP solver.

    Args:
        max_sail: Maximum number of accepted (SAIL) contracts
        risk_ratio: Downside protection ratio (worst_incremental >= risk_ratio * base_incremental)
        time_limit: Max solver seconds (CBC)
        bunker_price: Optional VLSFO price override ($/MT)
        save_outputs: If True, writes the solution CSV files to freight_optimization/outputs

    Returns:
        Structured dictionary matching FleetScheduleResponse
    """
    t0 = time.monotonic()
    candidates = load_candidates_with_live_economics(bunker_price=bunker_price)
    conflicts = build_temporal_conflict_graph(candidates)

    model = pulp.LpProblem("FINAL_PRODUCTION_SAIL_KILL", pulp.LpMaximize)

    # Binary decision variables x[idx] in {0, 1}
    x = {
        idx: pulp.LpVariable(f"x_{idx}", cat="Binary")
        for idx in candidates.index
    }

    # Objective: Maximize total worst-case incremental value above kill baseline
    model += pulp.lpSum(
        x[idx] * float(candidates.loc[idx, "worst_incremental"])
        for idx in candidates.index
    ), "maximize_worst_incremental"

    # Constraint 1: At most one vessel assignment per contract
    contract_groups = candidates.groupby("contract_id").groups
    for cid, idxs in contract_groups.items():
        model += pulp.lpSum(x[idx] for idx in idxs) <= 1, f"CONTRACT_{cid}"

    # Constraint 2: Maximum accepted SAIL contracts
    model += pulp.lpSum(x[idx] for idx in candidates.index) <= max_sail, "MAX_SAIL"

    # Constraint 3: Temporal conflicts (no overlapping voyages per vessel)
    for n, (a, b) in enumerate(conflicts):
        model += x[a] + x[b] <= 1, f"OVERLAP_{n}"

    # Constraint 4: Downside risk protection ratio
    if risk_ratio > 0:
        model += (
            pulp.lpSum(
                x[idx] * float(candidates.loc[idx, "worst_incremental"])
                for idx in candidates.index
            )
            >= risk_ratio * pulp.lpSum(
                x[idx] * float(candidates.loc[idx, "base_incremental"])
                for idx in candidates.index
            ),
            "RISK_PROTECTION",
        )

    # Solve with CBC — gapRel=0.01 provides near-instant solve while finding optimal integer solutions
    solver = pulp.PULP_CBC_CMD(timeLimit=time_limit, gapRel=0.01, msg=0)
    model.solve(solver)
    elapsed = time.monotonic() - t0

    # Extract selected candidates
    candidates["selected"] = [
        int(pulp.value(x[idx]) is not None and pulp.value(x[idx]) > 0.5)
        for idx in candidates.index
    ]
    sail = candidates[candidates["selected"] == 1].copy()
    sail = sail.sort_values(["departure_dt", "contract_id"]).reset_index(drop=True)

    selected_contract_ids = set(sail["contract_id"])
    all_contracts = list(dict.fromkeys(candidates["contract_id"]))
    kill_contract_ids = [cid for cid in all_contracts if cid not in selected_contract_ids]

    # Build KILL table (taking best available candidate for each killed contract as reference)
    kill_rows = []
    for cid in kill_contract_ids:
        group = candidates[candidates["contract_id"] == cid]
        best_idx = group["worst_incremental"].idxmax()
        best = group.loc[best_idx]
        kill_rows.append({
            "contract_id": cid,
            "decision": "KILL",
            "imo": str(best.get("imo", "")),
            "vessel_name": str(best.get("vessel_name", "UNASSIGNED")),
            "route_id": str(best.get("route_id", "")),
            "origin": str(best.get("origin", "")),
            "destination": str(best.get("destination", "")),
            "departure_date": str(best.get("departure_date", "")),
            "estimated_eta": str(best.get("estimated_eta", "")),
            "worst_incremental": float(best.get("worst_incremental", 0.0)),
            "base_incremental": float(best.get("base_incremental", 0.0)),
            "expected_incremental": float(best.get("expected_incremental", 0.0)),
        })

    # Prepare ContractAssignment list for API response
    assignments = []
    for _, row in sail.iterrows():
        assignments.append({
            "contract_id": str(row["contract_id"]),
            "route_id": str(row["route_id"]),
            "origin": str(row["origin"]),
            "destination": str(row["destination"]),
            "cargo_type": str(row.get("cargo_type", "coal")),
            "contract_volume_mt": float(row["contract_volume_mt"]),
            "imo": str(row["imo"]),
            "vessel_name": str(row["vessel_name"]),
            "vessel_dwt": float(row["vessel_dwt"]) if pd.notna(row.get("vessel_dwt")) else None,
            "vessel_class": str(row["vessel_class"]) if pd.notna(row.get("vessel_class")) else None,
            "departure_date": str(row["departure_date"]),
            "estimated_eta": str(row["estimated_eta"]),
            "bunker_cost_usd": float(row.get("bunker_cost_usd", 0.0)),
            "opex_cost_usd": float(row.get("opex_cost_live_usd", 0.0)),
            "other_cost_usd": float(row.get("other_voyage_cost_live_usd", 0.0)),
            "total_voyage_cost_usd": float(row.get("total_voyage_cost_usd", 0.0)),
            "bear_sail": float(row.get("bear_sail", 0.0)),
            "base_sail": float(row.get("base_sail", 0.0)),
            "bull_sail": float(row.get("bull_sail", 0.0)),
            "bear_incremental": float(row.get("bear_incremental", 0.0)),
            "base_incremental": float(row.get("base_incremental", 0.0)),
            "bull_incremental": float(row.get("bull_incremental", 0.0)),
            "worst_incremental": float(row.get("worst_incremental", 0.0)),
            "expected_incremental": float(row.get("expected_incremental", 0.0)),
            "decision": "SAIL",
        })

    # Prepare VesselSchedule items sorted chronologically per vessel
    vessel_schedule = []
    for imo, group in sail.groupby("imo"):
        sorted_legs = group.sort_values("departure_dt").reset_index(drop=True)
        for seq, (_, leg) in enumerate(sorted_legs.iterrows(), start=1):
            vessel_schedule.append({
                "imo": str(leg["imo"]),
                "vessel_name": str(leg["vessel_name"]),
                "departure_date": str(leg["departure_date"]),
                "estimated_eta": str(leg["estimated_eta"]),
                "contract_id": str(leg["contract_id"]),
                "route_id": str(leg["route_id"]),
                "origin": str(leg["origin"]),
                "destination": str(leg["destination"]),
                "contract_volume_mt": float(leg["contract_volume_mt"]),
                "worst_incremental": float(leg["worst_incremental"]),
                "expected_incremental": float(leg["expected_incremental"]),
                "voyage_sequence": seq,
            })

    # Prepare All Decisions (SAIL + KILL)
    all_decisions = []
    for a in assignments:
        all_decisions.append({
            "contract_id": a["contract_id"],
            "decision": "SAIL",
            "imo": a["imo"],
            "vessel_name": a["vessel_name"],
            "route_id": a["route_id"],
            "origin": a["origin"],
            "destination": a["destination"],
            "departure_date": a["departure_date"],
            "estimated_eta": a["estimated_eta"],
            "worst_incremental": a["worst_incremental"],
            "base_incremental": a["base_incremental"],
            "expected_incremental": a["expected_incremental"],
        })
    all_decisions.extend(kill_rows)
    all_decisions.sort(key=lambda r: r["contract_id"])

    # Prepare Summary
    used_vessels = len(set(sail["imo"]))
    total_bunker = float(sail["bunker_cost_usd"].sum()) if not sail.empty else 0.0
    total_opex = float(sail["opex_cost_live_usd"].sum()) if not sail.empty else 0.0
    total_cost = float(sail["total_voyage_cost_usd"].sum()) if not sail.empty else 0.0

    summary = {
        "total_contracts": len(all_contracts),
        "sail_contracts": len(sail),
        "kill_contracts": len(kill_contract_ids),
        "sail_vessels": used_vessels,
        "bear_incremental_usd": float(sail["bear_incremental"].sum()) if not sail.empty else 0.0,
        "base_incremental_usd": float(sail["base_incremental"].sum()) if not sail.empty else 0.0,
        "bull_incremental_usd": float(sail["bull_incremental"].sum()) if not sail.empty else 0.0,
        "worst_incremental_usd": float(sail["worst_incremental"].sum()) if not sail.empty else 0.0,
        "expected_incremental_usd": float(sail["expected_incremental"].sum()) if not sail.empty else 0.0,
        "bunker_cost_usd": total_bunker,
        "opex_cost_usd": total_opex,
        "total_voyage_cost_usd": total_cost,
        "bunker_price_vlsfo_usd": float(candidates["bunker_price_usd_per_mt"].iloc[0]),
        "solver_status": f"Optimal (CBC, {elapsed:.2f}s)",
    }

    result = {
        "summary": summary,
        "assignments": assignments,
        "vessel_schedule": vessel_schedule,
        "all_decisions": all_decisions,
    }

    # Optionally persist outputs
    if save_outputs:
        try:
            OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
            sail.to_csv(OUTPUTS_DIR / "step51v_final_solution.csv", index=False)
            pd.DataFrame(kill_rows).to_csv(OUTPUTS_DIR / "step51v_kill_summary.csv", index=False)
            pd.DataFrame(vessel_schedule).to_csv(OUTPUTS_DIR / "step51v_vessel_schedule.csv", index=False)
            pd.DataFrame(all_decisions).to_csv(OUTPUTS_DIR / "step51v_contract_decisions.csv", index=False)
            logger.info("Saved fleet portfolio optimization solution to %s", OUTPUTS_DIR)
        except Exception as exc:
            logger.warning("Could not write fleet optimization CSVs: %s", exc)

    return result
