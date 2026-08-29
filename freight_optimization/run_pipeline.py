#!/usr/bin/env python3

"""
MASTER FREIGHT OPTIMIZATION PIPELINE

Purpose
-------
Run the existing freight forecasting / bunker / feasibility /
production MILP pipeline from one command.

Usage
-----
    python3 run_pipeline.py

Optional:
    SKIP_FORECAST=1 python3 run_pipeline.py

The forecast stage is kept separate because the current production
optimization chain consumes the already-generated Step 18/19/23
economics and scenario artifacts. It is therefore not silently claimed
to be fully connected to the final MILP yet.

Current production chain:

    Forecast / validation artifacts
            ↓
    Step 50A - live bunker
            ↓
    Step 50B - bunker voyage economics
            ↓
    Step 50C - Bear/Base/Bull validation
            ↓
    Step 51A - departure-date feasibility
            ↓
    Step 51H - DWT/capacity propagation
            ↓
    Step 51U - complete production universe
            ↓
    Step 51V - final production MILP
            ↓
    final SAIL / KILL

IMPORTANT
---------
This master runner calls the EXISTING scripts.
It does not duplicate their business logic.

It uses subprocesses so that each existing script behaves exactly
as it does when executed manually.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path


# =============================================================================
# ROOT
# =============================================================================

ROOT = Path(
    "/home/aryashekhar/freight-optimization"
)

OUTPUTS = ROOT / "outputs"
PROCESSED = ROOT / "data" / "processed"


# =============================================================================
# CONFIG
# =============================================================================

SKIP_FORECAST = (
    os.environ.get(
        "SKIP_FORECAST",
        "0",
    )
    == "1"
)


# =============================================================================
# ANSI
# =============================================================================

RESET = "\033[0m"
BOLD = "\033[1m"
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"


def title(text: str) -> None:

    print()
    print("=" * 80)
    print(
        f"{BOLD}{text}{RESET}"
    )
    print("=" * 80)
    print()


def ok(text: str) -> None:

    print(
        f"{GREEN}✓{RESET} {text}"
    )


def warn(text: str) -> None:

    print(
        f"{YELLOW}!{RESET} {text}"
    )


def fail(text: str) -> None:

    print(
        f"{RED}✗{RESET} {text}"
    )


# =============================================================================
# PIPELINE STEP
# =============================================================================

def run_step(
    number: int,
    total: int,
    name: str,
    script: str,
    expected_files: list[str] | None = None,
    env_overrides: dict[str, str] | None = None,
) -> None:

    script_path = ROOT / script

    title(
        f"[{number}/{total}] {name}"
    )

    print(
        f"Script: {script}"
    )

    if not script_path.exists():

        fail(
            f"Script not found: {script_path}"
        )

        raise SystemExit(1)


    env = os.environ.copy()

    if env_overrides:
        env.update(
            env_overrides
        )


    start = time.perf_counter()


    try:

        result = subprocess.run(
            [
                sys.executable,
                str(script_path),
            ],
            cwd=ROOT,
            env=env,
            check=False,
        )

    except KeyboardInterrupt:

        print()

        fail(
            "Pipeline interrupted by user."
        )

        raise SystemExit(130)


    elapsed = (
        time.perf_counter()
        -
        start
    )


    if result.returncode != 0:

        fail(
            f"{name} FAILED "
            f"(exit code {result.returncode}, "
            f"{elapsed:.2f}s)"
        )

        print()
        print(
            "Pipeline stopped."
        )

        raise SystemExit(
            result.returncode
        )


    # -------------------------------------------------------------------------
    # Check expected outputs
    # -------------------------------------------------------------------------

    missing = []

    if expected_files:

        for filename in expected_files:

            path = Path(filename)

            if not path.is_absolute():

                path = ROOT / path

            if not path.exists():

                missing.append(
                    str(path)
                )


    if missing:

        warn(
            f"{name} exited successfully, "
            "but expected output files are missing:"
        )

        for path in missing:

            print(
                f"    {path}"
            )

        raise SystemExit(1)


    ok(
        f"{name} COMPLETE "
        f"({elapsed:.2f}s)"
    )


# =============================================================================
# FINAL RESULT
# =============================================================================

def show_final_result() -> None:

    import pandas as pd


    summary_file = (
        OUTPUTS /
        "step51v_summary.csv"
    )

    solution_file = (
        OUTPUTS /
        "step51v_final_solution.csv"
    )

    decisions_file = (
        OUTPUTS /
        "step51v_contract_decisions.csv"
    )


    if not summary_file.exists():

        fail(
            "Final Step 51V summary not found."
        )

        return


    summary = pd.read_csv(
        summary_file
    )

    if summary.empty:

        fail(
            "Step 51V summary is empty."
        )

        return


    s = summary.iloc[0]


    title(
        "FINAL PRODUCTION RESULT"
    )


    status = str(
        s.get(
            "status",
            "UNKNOWN",
        )
    )

    print(
        f"Status              : {status}"
    )

    print(
        f"Production candidates: "
        f"{int(s['input_step51u_rows'])}"
    )

    print(
        f"Contracts           : "
        f"{int(s['input_contracts'])}"
    )

    print(
        f"SAIL                : "
        f"{int(s['final_sail_contracts'])}"
    )

    print(
        f"KILL                : "
        f"{int(s['final_kill_contracts'])}"
    )

    print(
        f"Ships committed     : "
        f"{int(s['final_sail_vessels'])}"
    )

    print(
        f"Routes              : "
        f"{int(s['final_sail_routes'])}"
    )

    print(
        f"Departure dates     : "
        f"{int(s['final_departure_dates'])}"
    )

    print()

    print(
        f"Worst case          : "
        f"${float(s['worst_case_incremental_usd']) / 1_000_000:.2f}M"
    )

    print(
        f"Base case           : "
        f"${float(s['base_incremental_usd']) / 1_000_000:.2f}M"
    )

    print(
        f"Expected            : "
        f"${float(s['expected_incremental_usd']) / 1_000_000:.2f}M"
    )

    print(
        f"Bunker              : "
        f"${float(s['live_bunker_price_usd_per_mt']):,.2f}/MT"
    )

    print()

    print(
        f"Contract violations : "
        f"{int(s['contract_violations'])}"
    )

    print(
        f"Capacity violations : "
        f"{int(s['capacity_violations'])}"
    )

    print(
        f"Class violations    : "
        f"{int(s['class_violations'])}"
    )

    print(
        f"Temporal overlaps   : "
        f"{int(s['temporal_overlap_violations'])}"
    )


    # -------------------------------------------------------------------------
    # Print selected voyages
    # -------------------------------------------------------------------------

    if solution_file.exists():

        solution = pd.read_csv(
            solution_file
        )


        print()

        print(
            "-" * 80
        )

        print(
            "SAIL PLAN"
        )

        print(
            "-" * 80
        )


        for i, (_, row) in enumerate(
            solution.iterrows(),
            start=1,
        ):

            print(
                f"{i}. "
                f"{row['vessel_name']} "
                f"(IMO {row['imo']})"
            )

            print(
                f"   "
                f"{row['origin']} "
                f"-> "
                f"{row['destination']}"
            )

            print(
                f"   Departure: "
                f"{row['departure_date']}"
            )

            print(
                f"   ETA: "
                f"{row['estimated_eta']}"
            )

            print(
                f"   Worst: "
                f"${float(row['worst_incremental']) / 1_000:.1f}K"
            )

            print(
                f"   Expected: "
                f"${float(row['expected_incremental']) / 1_000:.1f}K"
            )

            print()


    # -------------------------------------------------------------------------
    # Output files
    # -------------------------------------------------------------------------

    print(
        "-" * 80
    )

    print(
        "OUTPUTS"
    )

    print(
        "-" * 80
    )

    print(
        f"Summary     : {summary_file}"
    )

    print(
        f"SAIL plan   : {solution_file}"
    )

    print(
        f"Decisions   : {decisions_file}"
    )


# =============================================================================
# START
# =============================================================================

def main() -> None:

    total_steps = 8

    start_all = time.perf_counter()


    title(
        "FREIGHT OPTIMIZATION MASTER PIPELINE"
    )


    print(
        f"Root: {ROOT}"
    )

    print(
        "Mode: existing scripts / local pipeline"
    )

    print(
        f"Forecast stage: "
        f"{'SKIPPED' if SKIP_FORECAST else 'ENABLED'}"
    )

    print()


    # =========================================================================
    # 1. EXISTING FORECAST VALIDATION
    # =========================================================================

    if not SKIP_FORECAST:

        run_step(
            1,
            total_steps,
            "EXISTING 5TC FORECAST / WALK-FORWARD",
            "walkforward_xgboost_5tc.py",
            expected_files=[
                "data/processed/5tc_walkforward_predictions.csv",
            ],
        )

    else:

        title(
            "[1/8] EXISTING 5TC FORECAST / WALK-FORWARD"
        )

        warn(
            "Skipped because SKIP_FORECAST=1"
        )


    # =========================================================================
    # 2. LIVE BUNKER
    # =========================================================================

    run_step(
        2,
        total_steps,
        "LIVE BUNKER INGESTION",
        "step50a_oilpriceapi_bunker_ingestion.py",
        expected_files=[
            "data/processed/step50a_bunker_current.csv",
            "outputs/step50a_bunker_summary.csv",
            "outputs/step50a_bunker_quality.csv",
        ],
    )


    # =========================================================================
    # 3. BUNKER VOYAGE ECONOMICS
    # =========================================================================

    run_step(
        3,
        total_steps,
        "LIVE BUNKER VOYAGE ECONOMICS",
        "step50b_live_bunker_voyage_economics.py",
        expected_files=[
            "data/processed/step50b_live_bunker_scenarios.csv",
        ],
    )


    # =========================================================================
    # 4. SCENARIO VALIDATION
    # =========================================================================

    run_step(
        4,
        total_steps,
        "BEAR / BASE / BULL VALIDATION",
        "step50c_validate_scenarios.py",
        expected_files=[
            "outputs/step50c_scenario_quality.csv",
        ],
    )


    # =========================================================================
    # 5. DEPARTURE DATE FEASIBILITY
    # =========================================================================

    run_step(
        5,
        total_steps,
        "DEPARTURE DATE FEASIBILITY",
        "step51a_departure_date_feasibility.py",
        expected_files=[
            "data/processed/step51a_optimizer_candidates.csv",
        ],
    )


    # =========================================================================
    # 6. DWT / CAPACITY PROPAGATION
    # =========================================================================

    run_step(
        6,
        total_steps,
        "DWT / CAPACITY PROPAGATION",
        "step51h_repair_capacity_fields.py",
        expected_files=[
            "data/processed/step51h_repaired_milp_input.csv",
            "outputs/step51h_capacity_summary.csv",
            "outputs/step51h_capacity_quality.csv",
        ],
    )


    # =========================================================================
    # 7. COMPLETE PRODUCTION UNIVERSE
    # =========================================================================

    run_step(
        7,
        total_steps,
        "FULL PRODUCTION CANDIDATE UNIVERSE",
        "step51u_build_full_production_universe.py",
        expected_files=[
            "data/processed/step51u_full_production_universe.csv",
            "data/processed/step51u_review_universe.csv",
            "outputs/step51u_summary.csv",
            "outputs/step51u_quality.csv",
        ],
    )


    # =========================================================================
    # 8. FINAL MILP
    # =========================================================================

    run_step(
        8,
        total_steps,
        "FINAL PRODUCTION SAIL / KILL MILP",
        "step51v_final_production_milp.py",
        expected_files=[
            "outputs/step51v_summary.csv",
            "outputs/step51v_quality.csv",
            "outputs/step51v_final_solution.csv",
            "outputs/step51v_contract_decisions.csv",
            "outputs/step51v_vessel_schedule.csv",
        ],
        env_overrides={
            "MILP_MAX_SAIL":
                os.environ.get(
                    "MILP_MAX_SAIL",
                    "12",
                ),

            "MILP_RISK_RATIO":
                os.environ.get(
                    "MILP_RISK_RATIO",
                    "0.60",
                ),

            "MILP_TIME_LIMIT":
                os.environ.get(
                    "MILP_TIME_LIMIT",
                    "120",
                ),
        },
    )


    # =========================================================================
    # FINAL RESULT
    # =========================================================================

    elapsed_all = (
        time.perf_counter()
        -
        start_all
    )


    show_final_result()


    title(
        "MASTER PIPELINE COMPLETE"
    )


    print(
        f"{GREEN}SUCCESS{RESET}"
    )

    print(
        f"Total runtime: "
        f"{elapsed_all:.2f}s"
    )

    print()

    print(
        "Run again with:"
    )

    print(
        "  python3 run_pipeline.py"
    )

    print()

    print(
        "Example with different MILP settings:"
    )

    print(
        "  MILP_MAX_SAIL=8 "
        "MILP_RISK_RATIO=0.40 "
        "MILP_TIME_LIMIT=120 "
        "python3 run_pipeline.py"
    )

    print()

    print(
        "Skip the existing forecast validation:"
    )

    print(
        "  SKIP_FORECAST=1 python3 run_pipeline.py"
    )

    print()


if __name__ == "__main__":
    main()
