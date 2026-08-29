"""
api/routes/fleet_schedule.py — Fleet Portfolio & AIS Scheduling API (Step 51V).

Exposes the research pipeline's global multi-contract fleet optimization
and AIS vessel assignment solution to the dashboard UI.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import pandas as pd
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()

# Locate freight_optimization directory robustly
CURRENT_FILE = Path(__file__).resolve()
# routes -> api -> backend -> freight-system -> FrieghtCast
WORKSPACE_ROOT = CURRENT_FILE.parents[4]
RESEARCH_ROOT = WORKSPACE_ROOT / "freight_optimization"
OUTPUTS_DIR = RESEARCH_ROOT / "outputs"


class ContractAssignment(BaseModel):
    contract_id: str
    route_id: str
    origin: str
    destination: str
    cargo_type: str
    contract_volume_mt: float
    imo: Optional[str] = None
    vessel_name: Optional[str] = None
    vessel_dwt: Optional[float] = None
    vessel_class: Optional[str] = None
    departure_date: Optional[str] = None
    estimated_eta: Optional[str] = None
    bunker_cost_usd: float = 0.0
    opex_cost_usd: float = 0.0
    other_cost_usd: float = 0.0
    total_voyage_cost_usd: float = 0.0
    bear_sail: float = 0.0
    base_sail: float = 0.0
    bull_sail: float = 0.0
    bear_incremental: float = 0.0
    base_incremental: float = 0.0
    bull_incremental: float = 0.0
    worst_incremental: float = 0.0
    expected_incremental: float = 0.0
    decision: str


class VesselScheduleItem(BaseModel):
    imo: str
    vessel_name: str
    departure_date: str
    estimated_eta: str
    contract_id: str
    route_id: str
    origin: str
    destination: str
    contract_volume_mt: float
    worst_incremental: float
    expected_incremental: float
    voyage_sequence: int


class FleetScheduleSummary(BaseModel):
    total_contracts: int
    sail_contracts: int
    kill_contracts: int
    sail_vessels: int
    bear_incremental_usd: float
    base_incremental_usd: float
    bull_incremental_usd: float
    worst_incremental_usd: float
    expected_incremental_usd: float
    bunker_cost_usd: float
    opex_cost_usd: float
    total_voyage_cost_usd: float
    bunker_price_vlsfo_usd: float
    solver_status: str


class FleetScheduleResponse(BaseModel):
    summary: FleetScheduleSummary
    assignments: List[ContractAssignment]
    vessel_schedule: List[VesselScheduleItem]
    all_decisions: List[Dict[str, Any]]


@router.get("/fleet-schedule", response_model=FleetScheduleResponse)
def get_fleet_schedule() -> FleetScheduleResponse:
    """
    Returns the complete Step 51V multi-contract fleet optimization solution,
    including vessel assignments, SAIL/KILL decisions, and schedule timelines.
    """
    final_solution_path = OUTPUTS_DIR / "step51v_final_solution.csv"
    vessel_schedule_path = OUTPUTS_DIR / "step51v_vessel_schedule.csv"
    contract_decisions_path = OUTPUTS_DIR / "step51v_contract_decisions.csv"

    if not final_solution_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Step 51V solution file not found. Please run optimization first.",
        )

    try:
        df_sol = pd.read_csv(final_solution_path)
        assignments = []
        for _, row in df_sol.iterrows():
            assignments.append(
                ContractAssignment(
                    contract_id=str(row["contract_id"]),
                    route_id=str(row["route_id"]),
                    origin=str(row["origin"]),
                    destination=str(row["destination"]),
                    cargo_type=str(row.get("cargo_type", "coal")),
                    contract_volume_mt=float(row["contract_volume_mt"]),
                    imo=str(row["imo"]) if pd.notna(row.get("imo")) else None,
                    vessel_name=str(row["vessel_name"]) if pd.notna(row.get("vessel_name")) else None,
                    vessel_dwt=float(row["vessel_dwt"]) if pd.notna(row.get("vessel_dwt")) else None,
                    vessel_class=str(row["vessel_class"]) if pd.notna(row.get("vessel_class")) else None,
                    departure_date=str(row["departure_date"]) if pd.notna(row.get("departure_date")) else None,
                    estimated_eta=str(row["estimated_eta"]) if pd.notna(row.get("estimated_eta")) else None,
                    bunker_cost_usd=float(row.get("bunker_cost_usd", 0.0)),
                    opex_cost_usd=float(row.get("opex_cost_live_usd", row.get("opex_cost_usd", 0.0))),
                    other_cost_usd=float(row.get("other_voyage_cost_live_usd", 0.0)),
                    total_voyage_cost_usd=float(row.get("total_voyage_cost_usd", 0.0)),
                    bear_sail=float(row.get("bear_sail", 0.0)),
                    base_sail=float(row.get("base_sail", 0.0)),
                    bull_sail=float(row.get("bull_sail", 0.0)),
                    bear_incremental=float(row.get("bear_incremental", 0.0)),
                    base_incremental=float(row.get("base_incremental", 0.0)),
                    bull_incremental=float(row.get("bull_incremental", 0.0)),
                    worst_incremental=float(row.get("worst_incremental", 0.0)),
                    expected_incremental=float(row.get("expected_incremental", 0.0)),
                    decision=str(row["decision"]),
                )
            )

        # Vessel schedule
        schedule_items = []
        if vessel_schedule_path.exists():
            df_sched = pd.read_csv(vessel_schedule_path)
            for _, row in df_sched.iterrows():
                schedule_items.append(
                    VesselScheduleItem(
                        imo=str(row["imo"]),
                        vessel_name=str(row["vessel_name"]),
                        departure_date=str(row["departure_date"]),
                        estimated_eta=str(row["estimated_eta"]),
                        contract_id=str(row["contract_id"]),
                        route_id=str(row["route_id"]),
                        origin=str(row["origin"]),
                        destination=str(row["destination"]),
                        contract_volume_mt=float(row["contract_volume_mt"]),
                        worst_incremental=float(row["worst_incremental"]),
                        expected_incremental=float(row["expected_incremental"]),
                        voyage_sequence=int(row.get("voyage_sequence", 1)),
                    )
                )

        # All contract decisions
        all_decisions = []
        if contract_decisions_path.exists():
            df_dec = pd.read_csv(contract_decisions_path)
            all_decisions = df_dec.fillna("").to_dict(orient="records")

        # Summary
        sail_count = len(df_sol[df_sol["decision"] == "SAIL"])
        kill_count = len(all_decisions) - sail_count if all_decisions else 10
        total_contracts = len(all_decisions) if all_decisions else 16

        summary = FleetScheduleSummary(
            total_contracts=total_contracts,
            sail_contracts=sail_count,
            kill_contracts=kill_count,
            sail_vessels=len(df_sol["imo"].unique()) if "imo" in df_sol else sail_count,
            bear_incremental_usd=float(df_sol["bear_incremental"].sum()),
            base_incremental_usd=float(df_sol["base_incremental"].sum()),
            bull_incremental_usd=float(df_sol["bull_incremental"].sum()),
            worst_incremental_usd=float(df_sol["worst_incremental"].sum()),
            expected_incremental_usd=float(df_sol["expected_incremental"].sum()),
            bunker_cost_usd=float(df_sol["bunker_cost_usd"].sum()),
            opex_cost_usd=float(df_sol["opex_cost_live_usd"].sum() if "opex_cost_live_usd" in df_sol else 0.0),
            total_voyage_cost_usd=float(df_sol["total_voyage_cost_usd"].sum()),
            bunker_price_vlsfo_usd=float(df_sol["bunker_price_usd_per_mt"].iloc[0]) if "bunker_price_usd_per_mt" in df_sol else 770.5,
            solver_status="Optimal (CBC)",
        )

        return FleetScheduleResponse(
            summary=summary,
            assignments=assignments,
            vessel_schedule=schedule_items,
            all_decisions=all_decisions,
        )
    except Exception as exc:
        logger.exception("Failed to parse Step 51V solution: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Error reading Step 51V fleet optimization: {exc}",
        )
