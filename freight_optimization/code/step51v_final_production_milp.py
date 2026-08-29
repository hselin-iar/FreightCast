#!/usr/bin/env python3

"""
STEP 51V - FINAL PRODUCTION SAIL/KILL MILP

IMPORTANT ARCHITECTURE
----------------------

Step 51U is the COMPLETE production candidate universe.

Step 51V MUST NOT use the selected solution from Step 51P/51S/51T.

It:

1. Loads ALL Step 51U production candidates
2. Loads Step 23 contract economics
3. Loads current live VLSFO price from Step 50A
4. Rebuilds voyage cost
5. Calculates Bear/Base/Bull Sail economics
6. Calculates incremental Sail value versus Kill
7. Builds vessel temporal conflicts
8. Solves the production MILP
9. Produces SAIL and KILL decisions

Production eligibility coming from Step 51U:
    DWT >= cargo
    exact class match

MILP:
    one decision per contract
    maximum Sail
    no overlapping voyages per vessel
    portfolio downside protection

Objective:
    maximize total worst-case incremental value
"""

from pathlib import Path
import json
import os
import time

import numpy as np
import pandas as pd
import pulp


# =============================================================================
# PATHS
# =============================================================================

ROOT = Path(
    "/home/aryashekhar/freight-optimization"
)

PROCESSED = ROOT / "data" / "processed"
OUTPUTS = ROOT / "outputs"


UNIVERSE_FILE = (
    PROCESSED /
    "step51u_full_production_universe.csv"
)

CONTRACT_FILE = (
    PROCESSED /
    "step23_contract_sail_kill.csv"
)

BUNKER_FILE = (
    PROCESSED /
    "step50a_bunker_current.csv"
)

REVIEW_FILE = (
    PROCESSED /
    "step51u_review_universe.csv"
)


FINAL_FILE = (
    OUTPUTS /
    "step51v_final_solution.csv"
)

KILL_FILE = (
    OUTPUTS /
    "step51v_kill_summary.csv"
)

SCHEDULE_FILE = (
    OUTPUTS /
    "step51v_vessel_schedule.csv"
)

DECISIONS_FILE = (
    OUTPUTS /
    "step51v_contract_decisions.csv"
)

SUMMARY_FILE = (
    OUTPUTS /
    "step51v_summary.csv"
)

QUALITY_FILE = (
    OUTPUTS /
    "step51v_quality.csv"
)

REPORT_FILE = (
    OUTPUTS /
    "step51v_report.json"
)


# =============================================================================
# CONFIG
# =============================================================================

MAX_SAIL = int(
    os.environ.get(
        "MILP_MAX_SAIL",
        "12",
    )
)

RISK_RATIO = float(
    os.environ.get(
        "MILP_RISK_RATIO",
        "0.60",
    )
)

TIME_LIMIT = int(
    os.environ.get(
        "MILP_TIME_LIMIT",
        "120",
    )
)


# =============================================================================
# HELPERS
# =============================================================================

def now_utc():
    return pd.Timestamp.now(
        tz="UTC"
    ).isoformat()


def normalize_id(series):
    return (
        series
        .astype(str)
        .str.strip()
        .str.replace(
            r"\.0$",
            "",
            regex=True,
        )
    )


def numeric(series):
    return pd.to_numeric(
        series,
        errors="coerce",
    )


def to_utc(value):

    if value is None:
        return pd.NaT

    try:
        if pd.isna(value):
            return pd.NaT
    except Exception:
        pass

    try:
        ts = pd.Timestamp(value)
    except Exception:
        return pd.NaT

    if ts.tzinfo is None:
        return ts.tz_localize("UTC")

    return ts.tz_convert("UTC")


def require(
    df,
    columns,
    name,
):

    missing = [
        c
        for c in columns
        if c not in df.columns
    ]

    if missing:
        raise RuntimeError(
            f"{name} missing required columns:\n"
            + "\n".join(missing)
        )


# =============================================================================
# START
# =============================================================================

print()
print("=" * 80)
print("STEP 51V - FINAL PRODUCTION SAIL/KILL MILP")
print("=" * 80)
print()

print("MODE: LOCAL ONLY")
print("MyShipTracking API calls: 0")
print("MyShipTracking credits: 0")
print("OilPriceAPI calls: 0")
print("Maximum Sail:", MAX_SAIL)
print("Risk ratio:", RISK_RATIO)
print("Time limit:", TIME_LIMIT)
print()


# =============================================================================
# CHECK INPUTS
# =============================================================================

for path in [
    UNIVERSE_FILE,
    CONTRACT_FILE,
    BUNKER_FILE,
]:

    if not path.exists():
        raise FileNotFoundError(
            f"Missing input file:\n{path}"
        )


# =============================================================================
# 1/12 LOAD
# =============================================================================

print("=" * 80)
print("1/12 - LOADING COMPLETE PRODUCTION UNIVERSE")
print("=" * 80)
print()

universe = pd.read_csv(
    UNIVERSE_FILE
)

contracts = pd.read_csv(
    CONTRACT_FILE
)

bunker = pd.read_csv(
    BUNKER_FILE
)


print(
    "Step 51U rows:",
    len(universe)
)

print(
    "Step 23 contract rows:",
    len(contracts)
)

print(
    "Bunker rows:",
    len(bunker)
)


# =============================================================================
# INPUT REQUIREMENTS
# =============================================================================

require(
    universe,
    [
        "contract_id",
        "route_id",
        "origin",
        "destination",
        "cargo_type",
        "contract_volume_mt",
        "imo",
        "vessel_name",
        "vessel_dwt",
        "vessel_class",
        "contract_class",
        "departure_date",
        "estimated_eta",
    ],
    "Step 51U",
)


require(
    contracts,
    [
        "contract_id",
        "route_id",
        "scenario",
        "scenario_route_freight_rate",
        "contract_volume_mt",
        "kill_penalty_usd",
        "kill_alternative_value_usd",
    ],
    "Step 23",
)


require(
    bunker,
    [
        "price_usd_per_metric_ton",
    ],
    "Step 50A",
)


# =============================================================================
# 2/12 NORMALIZATION
# =============================================================================

print()
print("=" * 80)
print("2/12 - NORMALIZING")
print("=" * 80)
print()


# Universe

universe[
    "contract_id"
] = normalize_id(
    universe[
        "contract_id"
    ]
)

universe[
    "route_id"
] = normalize_id(
    universe[
        "route_id"
    ]
)

universe[
    "imo"
] = normalize_id(
    universe[
        "imo"
    ]
)

universe[
    "contract_volume_mt"
] = numeric(
    universe[
        "contract_volume_mt"
    ]
)

universe[
    "vessel_dwt"
] = numeric(
    universe[
        "vessel_dwt"
    ]
)

universe[
    "departure_dt"
] = universe[
    "departure_date"
].apply(
    to_utc
)

universe[
    "eta_dt"
] = universe[
    "estimated_eta"
].apply(
    to_utc
)


# Contracts

contracts[
    "contract_id"
] = normalize_id(
    contracts[
        "contract_id"
    ]
)

contracts[
    "route_id"
] = normalize_id(
    contracts[
        "route_id"
    ]
)

contracts[
    "scenario"
] = (
    contracts[
        "scenario"
    ]
    .astype(str)
    .str.strip()
    .str.lower()
)

contracts[
    "contract_volume_mt"
] = numeric(
    contracts[
        "contract_volume_mt"
    ]
)

contracts[
    "scenario_route_freight_rate"
] = numeric(
    contracts[
        "scenario_route_freight_rate"
    ]
)


for col in [
    "kill_penalty_usd",
    "kill_alternative_value_usd",
    "fuel_consumption_mt",
    "bunker_mt_per_day",
    "daily_opex_usd",
    "opex_cost_usd",
    "other_voyage_cost_usd",
    "total_voyage_days",
]:

    if col in contracts.columns:

        contracts[
            col
        ] = numeric(
            contracts[
                col
            ]
        )


# =============================================================================
# 3/12 BUILD CONTRACT ECONOMIC MASTER
# =============================================================================

print()
print("=" * 80)
print("3/12 - BUILDING CONTRACT ECONOMIC MASTER")
print("=" * 80)
print()


contract_meta = (
    contracts[
        [
            "contract_id",
            "route_id",
            "origin",
            "destination",
            "cargo_type",
            "contract_volume_mt",
            "vessel_class",
        ]
    ]
    .drop_duplicates(
        "contract_id",
        keep="first",
    )
    .copy()
)


rates = (
    contracts[
        [
            "contract_id",
            "scenario",
            "scenario_route_freight_rate",
        ]
    ]
    .drop_duplicates(
        [
            "contract_id",
            "scenario",
        ]
    )
    .pivot(
        index="contract_id",
        columns="scenario",
        values="scenario_route_freight_rate",
    )
    .reset_index()
)


rates = rates.rename(
    columns={
        "bear":
            "bear_rate",

        "base":
            "base_rate",

        "bull":
            "bull_rate",
    }
)


kill = (
    contracts[
        [
            "contract_id",
            "kill_penalty_usd",
            "kill_alternative_value_usd",
        ]
    ]
    .drop_duplicates(
        "contract_id",
        keep="first",
    )
)


kill[
    "kill_value"
] = (
    kill[
        "kill_alternative_value_usd"
    ]
    -
    kill[
        "kill_penalty_usd"
    ]
)


contract_meta = (
    contract_meta
    .merge(
        rates,
        on="contract_id",
        how="left",
    )
    .merge(
        kill[
            [
                "contract_id",
                "kill_value",
            ]
        ],
        on="contract_id",
        how="left",
    )
)


print(
    "Unique contracts:",
    len(contract_meta)
)

print(
    "Contracts with Bear:",
    int(
        contract_meta[
            "bear_rate"
        ].notna().sum()
    )
)

print(
    "Contracts with Base:",
    int(
        contract_meta[
            "base_rate"
        ].notna().sum()
    )
)

print(
    "Contracts with Bull:",
    int(
        contract_meta[
            "bull_rate"
        ].notna().sum()
    )
)


# =============================================================================
# 4/12 BUILD ROUTE ECONOMIC MASTER
# =============================================================================

print()
print("=" * 80)
print("4/12 - BUILDING ROUTE ECONOMIC MASTER")
print("=" * 80)
print()


route_economics = (
    contracts[
        [
            "route_id",
            "scenario",
            "fuel_consumption_mt",
            "bunker_mt_per_day",
            "daily_opex_usd",
            "opex_cost_usd",
            "other_voyage_cost_usd",
            "total_voyage_days",
        ]
    ]
    .drop_duplicates(
        [
            "route_id",
            "scenario",
        ]
    )
    .copy()
)


for col in [
    "fuel_consumption_mt",
    "bunker_mt_per_day",
    "daily_opex_usd",
    "opex_cost_usd",
    "other_voyage_cost_usd",
    "total_voyage_days",
]:

    route_economics[
        col
    ] = numeric(
        route_economics[
            col
        ]
    )


# -------------------------------------------------------------------------
# Use BASE route scenario as the cost master.
# -------------------------------------------------------------------------

route_base = (
    route_economics[
        route_economics[
            "scenario"
        ]
        ==
        "base"
    ]
    .copy()
    .drop_duplicates(
        "route_id",
        keep="first",
    )
)


route_base = route_base.rename(
    columns={
        "fuel_consumption_mt":
            "route_fuel_consumption_mt",

        "bunker_mt_per_day":
            "route_bunker_mt_per_day",

        "daily_opex_usd":
            "route_daily_opex_usd",

        "opex_cost_usd":
            "route_opex_cost_usd",

        "other_voyage_cost_usd":
            "route_other_cost_usd",

        "total_voyage_days":
            "route_default_voyage_days",
    }
)


route_cost_columns = [
    "route_id",
    "route_fuel_consumption_mt",
    "route_bunker_mt_per_day",
    "route_daily_opex_usd",
    "route_opex_cost_usd",
    "route_other_cost_usd",
    "route_default_voyage_days",
]


route_cost_columns = [
    c
    for c in route_cost_columns
    if c in route_base.columns
]


print(
    "Base route economics:",
    len(route_base)
)


# =============================================================================
# 5/12 JOIN ECONOMICS TO ALL 51U CANDIDATES
# =============================================================================

print()
print("=" * 80)
print("5/12 - JOINING ECONOMICS TO ALL CANDIDATES")
print("=" * 80)
print()


candidates = universe.merge(
    contract_meta,
    on="contract_id",
    how="left",
    suffixes=(
        "",
        "_contract",
    )
)


# -------------------------------------------------------------------------
# Protect the original Step 51U route ID.
# -------------------------------------------------------------------------

if "route_id_contract" in candidates.columns:

    # Prefer the universe route_id but verify agreement.

    route_mismatch = (
        candidates[
            "route_id"
        ].astype(str)
        !=
        candidates[
            "route_id_contract"
        ].astype(str)
    )

    mismatch_count = int(
        route_mismatch.sum()
    )

    if mismatch_count:

        print(
            "WARNING: route mismatches:",
            mismatch_count
        )

    candidates[
        "route_id_check"
    ] = candidates[
        "route_id"
    ]

else:

    candidates[
        "route_id_check"
    ] = candidates[
        "route_id"
    ]


candidates = candidates.merge(
    route_base[
        route_cost_columns
    ],
    on="route_id",
    how="left",
)


print(
    "Candidates after economics join:",
    len(candidates)
)


# =============================================================================
# 6/12 LIVE BUNKER + VOYAGE ECONOMICS
# =============================================================================

print()
print("=" * 80)
print("6/12 - CALCULATING LIVE VOYAGE ECONOMICS")
print("=" * 80)
print()


bunker_price = float(
    bunker[
        "price_usd_per_metric_ton"
    ].iloc[0]
)


print(
    "Live VLSFO:",
    bunker_price,
    "USD/MT"
)


# -------------------------------------------------------------------------
# Voyage days
#
# Priority:
#   Step 51U candidate-specific total_voyage_days
#   route base default
# -------------------------------------------------------------------------

if "total_voyage_days" not in candidates.columns:

    candidates[
        "total_voyage_days"
    ] = np.nan


candidates[
    "total_voyage_days"
] = numeric(
    candidates[
        "total_voyage_days"
    ]
)


candidates[
    "voyage_days"
] = candidates[
    "total_voyage_days"
].combine_first(
    candidates[
        "route_default_voyage_days"
    ]
)


# -------------------------------------------------------------------------
# Bunker cost
#
# Priority:
#   explicit route fuel consumption × live price
#   otherwise bunker/day × voyage days × live price
# -------------------------------------------------------------------------

candidates[
    "bunker_cost_usd"
] = (
    candidates[
        "route_fuel_consumption_mt"
    ]
    *
    bunker_price
)


bunker_fallback = (
    candidates[
        "bunker_cost_usd"
    ].isna()
    &
    candidates[
        "route_bunker_mt_per_day"
    ].notna()
    &
    candidates[
        "voyage_days"
    ].notna()
)


candidates.loc[
    bunker_fallback,
    "bunker_cost_usd",
] = (
    candidates.loc[
        bunker_fallback,
        "route_bunker_mt_per_day",
    ]
    *
    candidates.loc[
        bunker_fallback,
        "voyage_days",
    ]
    *
    bunker_price
)


# -------------------------------------------------------------------------
# OPEX
# -------------------------------------------------------------------------

candidates[
    "opex_cost_live_usd"
] = (
    candidates[
        "route_daily_opex_usd"
    ]
    *
    candidates[
        "voyage_days"
    ]
)


opex_fallback = (
    candidates[
        "opex_cost_live_usd"
    ].isna()
    &
    candidates[
        "route_opex_cost_usd"
    ].notna()
)


candidates.loc[
    opex_fallback,
    "opex_cost_live_usd",
] = candidates.loc[
    opex_fallback,
    "route_opex_cost_usd",
]


# -------------------------------------------------------------------------
# Other voyage cost
# -------------------------------------------------------------------------

candidates[
    "other_voyage_cost_live_usd"
] = candidates[
    "route_other_cost_usd"
]


# -------------------------------------------------------------------------
# Total cost
# -------------------------------------------------------------------------

candidates[
    "total_voyage_cost_usd"
] = (
    candidates[
        "bunker_cost_usd"
    ]
    +
    candidates[
        "opex_cost_live_usd"
    ]
    +
    candidates[
        "other_voyage_cost_live_usd"
    ]
)


# -------------------------------------------------------------------------
# Revenue
# -------------------------------------------------------------------------

candidates[
    "bear_revenue_usd"
] = (
    candidates[
        "bear_rate"
    ]
    *
    candidates[
        "contract_volume_mt"
    ]
)

candidates[
    "base_revenue_usd"
] = (
    candidates[
        "base_rate"
    ]
    *
    candidates[
        "contract_volume_mt"
    ]
)

candidates[
    "bull_revenue_usd"
] = (
    candidates[
        "bull_rate"
    ]
    *
    candidates[
        "contract_volume_mt"
    ]
)


# -------------------------------------------------------------------------
# SAIL
# -------------------------------------------------------------------------

candidates[
    "bear_sail"
] = (
    candidates[
        "bear_revenue_usd"
    ]
    -
    candidates[
        "total_voyage_cost_usd"
    ]
)


candidates[
    "base_sail"
] = (
    candidates[
        "base_revenue_usd"
    ]
    -
    candidates[
        "total_voyage_cost_usd"
    ]
)


candidates[
    "bull_sail"
] = (
    candidates[
        "bull_revenue_usd"
    ]
    -
    candidates[
        "total_voyage_cost_usd"
    ]
)


# -------------------------------------------------------------------------
# Incremental vs KILL
# -------------------------------------------------------------------------

candidates[
    "bear_incremental"
] = (
    candidates[
        "bear_sail"
    ]
    -
    candidates[
        "kill_value"
    ]
)


candidates[
    "base_incremental"
] = (
    candidates[
        "base_sail"
    ]
    -
    candidates[
        "kill_value"
    ]
)


candidates[
    "bull_incremental"
] = (
    candidates[
        "bull_sail"
    ]
    -
    candidates[
        "kill_value"
    ]
)


candidates[
    "worst_incremental"
] = candidates[
    [
        "bear_incremental",
        "base_incremental",
        "bull_incremental",
    ]
].min(
    axis=1
)


candidates[
    "expected_incremental"
] = candidates[
    [
        "bear_incremental",
        "base_incremental",
        "bull_incremental",
    ]
].mean(
    axis=1
)


# -------------------------------------------------------------------------
# Economics completeness
# -------------------------------------------------------------------------

required_economic_columns = [
    "bear_incremental",
    "base_incremental",
    "bull_incremental",
    "worst_incremental",
    "expected_incremental",
]


for col in required_economic_columns:

    missing = int(
        candidates[
            col
        ].isna().sum()
    )

    print(
        f"{col}: missing {missing}"
    )

    if missing:

        raise RuntimeError(
            f"Missing economic values in {col}. "
            "Check Step 23 route economics."
        )


# =============================================================================
# 7/12 VALIDATE CANDIDATE UNIVERSE
# =============================================================================

print()
print("=" * 80)
print("7/12 - VALIDATING COMPLETE PRODUCTION UNIVERSE")
print("=" * 80)
print()


capacity_violations = int(
    (
        candidates[
            "vessel_dwt"
        ]
        <
        candidates[
            "contract_volume_mt"
        ]
    ).sum()
)


class_violations = int(
    (
        candidates[
            "vessel_class"
        ]
        .astype(str)
        .str.strip()
        .str.upper()
        !=
        candidates[
            "contract_class"
        ]
        .astype(str)
        .str.strip()
        .str.upper()
    ).sum()
)


invalid_dates = int(
    (
        candidates[
            "departure_dt"
        ].isna()
        |
        candidates[
            "eta_dt"
        ].isna()
    ).sum()
)


invalid_intervals = int(
    (
        candidates[
            "eta_dt"
        ]
        <=
        candidates[
            "departure_dt"
        ]
    ).sum()
)


print(
    "Capacity violations:",
    capacity_violations
)

print(
    "Class violations:",
    class_violations
)

print(
    "Invalid date rows:",
    invalid_dates
)

print(
    "Invalid time intervals:",
    invalid_intervals
)


if capacity_violations:

    raise RuntimeError(
        "Capacity validation failed."
    )


if class_violations:

    raise RuntimeError(
        "Class validation failed."
    )


if invalid_dates:

    raise RuntimeError(
        "Date validation failed."
    )


if invalid_intervals:

    raise RuntimeError(
        "ETA <= departure found."
    )


# -------------------------------------------------------------------------
# Remove duplicate decision rows.
# -------------------------------------------------------------------------

before_dedup = len(
    candidates
)


candidates = (
    candidates
    .drop_duplicates(
        [
            "contract_id",
            "imo",
            "departure_dt",
            "eta_dt",
        ],
        keep="first",
    )
    .reset_index(
        drop=True
    )
)


duplicates_removed = (
    before_dedup
    -
    len(candidates)
)


print(
    "Duplicate decisions removed:",
    duplicates_removed
)

print(
    "Final production decision rows:",
    len(candidates)
)


# =============================================================================
# 8/12 TEMPORAL CONFLICTS
# =============================================================================

print()
print("=" * 80)
print("8/12 - BUILDING VESSEL TEMPORAL CONFLICT GRAPH")
print("=" * 80)
print()


conflicts = []


for imo, group in (
    candidates
    .groupby(
        "imo"
    )
):

    idxs = list(
        group.index
    )


    for i in range(
        len(idxs)
    ):

        a = idxs[i]


        for j in range(
            i + 1,
            len(idxs)
        ):

            b = idxs[j]


            if (
                candidates.loc[
                    a,
                    "contract_id",
                ]
                ==
                candidates.loc[
                    b,
                    "contract_id",
                ]
            ):

                continue


            a_start = to_utc(
                candidates.loc[
                    a,
                    "departure_dt",
                ]
            )

            a_end = to_utc(
                candidates.loc[
                    a,
                    "eta_dt",
                ]
            )

            b_start = to_utc(
                candidates.loc[
                    b,
                    "departure_dt",
                ]
            )

            b_end = to_utc(
                candidates.loc[
                    b,
                    "eta_dt",
                ]
            )


            if (
                a_start < b_end
                and
                b_start < a_end
            ):

                conflicts.append(
                    (
                        a,
                        b,
                    )
                )


print(
    "Temporal conflict edges:",
    len(conflicts)
)


# =============================================================================
# 9/12 MILP
# =============================================================================

print()
print("=" * 80)
print("9/12 - BUILDING MILP")
print("=" * 80)
print()


model = pulp.LpProblem(
    "FINAL_PRODUCTION_SAIL_KILL",
    pulp.LpMaximize,
)


x = {
    idx:
        pulp.LpVariable(
            f"x_{idx}",
            lowBound=0,
            upBound=1,
            cat="Binary",
        )

    for idx in candidates.index
}


# -------------------------------------------------------------------------
# Objective
# -------------------------------------------------------------------------

model += pulp.lpSum(
    x[idx]
    *
    float(
        candidates.loc[
            idx,
            "worst_incremental",
        ]
    )
    for idx in candidates.index
)


# -------------------------------------------------------------------------
# One Sail assignment per contract
# -------------------------------------------------------------------------

contract_groups = (
    candidates
    .groupby(
        "contract_id"
    )
    .groups
)


for contract_id, idxs in (
    contract_groups.items()
):

    model += (
        pulp.lpSum(
            x[idx]
            for idx in idxs
        )
        <= 1,

        f"CONTRACT_{contract_id}",
    )


# -------------------------------------------------------------------------
# Maximum Sail
# -------------------------------------------------------------------------

model += (
    pulp.lpSum(
        x[idx]
        for idx in candidates.index
    )
    <= MAX_SAIL,

    "MAX_SAIL",
)


# -------------------------------------------------------------------------
# Vessel temporal conflicts
# -------------------------------------------------------------------------

for n, (
    a,
    b,
) in enumerate(
    conflicts
):

    model += (
        x[a]
        +
        x[b]
        <= 1,

        f"OVERLAP_{n}",
    )


# -------------------------------------------------------------------------
# Risk
# -------------------------------------------------------------------------

if RISK_RATIO > 0:

    model += (
        pulp.lpSum(
            x[idx]
            *
            float(
                candidates.loc[
                    idx,
                    "worst_incremental",
                ]
            )
            for idx in candidates.index
        )
        >=
        RISK_RATIO
        *
        pulp.lpSum(
            x[idx]
            *
            float(
                candidates.loc[
                    idx,
                    "base_incremental",
                ]
            )
            for idx in candidates.index
        ),

        "RISK_PROTECTION",
    )


print(
    "MILP variables:",
    len(x)
)

print(
    "Contracts:",
    len(contract_groups)
)

print(
    "Vessels:",
    candidates[
        "imo"
    ].nunique()
)

print(
    "Routes:",
    candidates[
        "route_id"
    ].nunique()
)

print(
    "Temporal conflicts:",
    len(conflicts)
)


# =============================================================================
# 10/12 SOLVE
# =============================================================================

print()
print("=" * 80)
print("10/12 - SOLVING CBC")
print("=" * 80)
print()


start = time.perf_counter()


solver = pulp.PULP_CBC_CMD(
    msg=False,
    timeLimit=TIME_LIMIT,
)


model.solve(
    solver
)


solve_seconds = (
    time.perf_counter()
    -
    start
)


status = pulp.LpStatus[
    model.status
]


print(
    "CBC status:",
    status
)

print(
    "Solve seconds:",
    round(
        solve_seconds,
        4,
    )
)


if model.status != pulp.LpStatusOptimal:

    raise RuntimeError(
        "MILP did not solve to Optimal. "
        f"Status={status}"
    )


# =============================================================================
# 11/12 EXTRACT + VALIDATE
# =============================================================================

print()
print("=" * 80)
print("11/12 - EXTRACTING FINAL SAIL / KILL")
print("=" * 80)
print()


candidates[
    "selected"
] = [
    int(
        pulp.value(
            x[idx]
        )
        >
        0.5
    )
    for idx in candidates.index
]


sail = candidates[
    candidates[
        "selected"
    ]
    ==
    1
].copy()


sail = (
    sail
    .sort_values(
        [
            "departure_dt",
            "contract_id",
        ]
    )
    .reset_index(
        drop=True
    )
)


selected_contracts = set(
    sail[
        "contract_id"
    ]
)


all_contracts = (
    candidates[
        "contract_id"
    ]
    .drop_duplicates()
    .tolist()
)


kill_contract_ids = [
    cid
    for cid in all_contracts
    if cid not in selected_contracts
]


# -------------------------------------------------------------------------
# KILL table
# -------------------------------------------------------------------------

kill_rows = []


for contract_id in kill_contract_ids:

    group = candidates[
        candidates[
            "contract_id"
        ]
        ==
        contract_id
    ]


    best_idx = group[
        "worst_incremental"
    ].idxmax()


    best = group.loc[
        best_idx
    ]


    kill_rows.append(
        {
            "contract_id":
                contract_id,

            "decision":
                "KILL",

            "route_id":
                best[
                    "route_id"
                ],

            "origin":
                best[
                    "origin"
                ],

            "destination":
                best[
                    "destination"
                ],

            "cargo_type":
                best[
                    "cargo_type"
                ],

            "contract_volume_mt":
                best[
                    "contract_volume_mt"
                ],

            "best_available_vessel":
                best[
                    "vessel_name"
                ],

            "best_available_imo":
                best[
                    "imo"
                ],

            "best_available_departure":
                best[
                    "departure_date"
                ],

            "best_available_eta":
                best[
                    "estimated_eta"
                ],

            "best_worst_incremental":
                best[
                    "worst_incremental"
                ],

            "best_base_incremental":
                best[
                    "base_incremental"
                ],

            "best_expected_incremental":
                best[
                    "expected_incremental"
                ],

            "reason":
                "NOT_SELECTED_BY_PRODUCTION_MILP",
        }
    )


kill = pd.DataFrame(
    kill_rows
)


# -------------------------------------------------------------------------
# Validation
# -------------------------------------------------------------------------

contract_violations = int(
    (
        sail[
            "contract_id"
        ]
        .value_counts()
        >
        1
    ).sum()
)


capacity_violations_final = int(
    (
        sail[
            "vessel_dwt"
        ]
        <
        sail[
            "contract_volume_mt"
        ]
    ).sum()
)


class_violations_final = int(
    (
        sail[
            "vessel_class"
        ]
        .astype(str)
        .str.strip()
        .str.upper()
        !=
        sail[
            "contract_class"
        ]
        .astype(str)
        .str.strip()
        .str.upper()
    ).sum()
)


overlap_violations = 0


for imo, group in (
    sail
    .groupby(
        "imo"
    )
):

    idxs = list(
        group.index
    )


    for i in range(
        len(idxs)
    ):

        for j in range(
            i + 1,
            len(idxs)
        ):

            a = idxs[i]
            b = idxs[j]


            a_start = to_utc(
                sail.loc[
                    a,
                    "departure_dt",
                ]
            )

            a_end = to_utc(
                sail.loc[
                    a,
                    "eta_dt",
                ]
            )

            b_start = to_utc(
                sail.loc[
                    b,
                    "departure_dt",
                ]
            )

            b_end = to_utc(
                sail.loc[
                    b,
                    "eta_dt",
                ]
            )


            if (
                a_start < b_end
                and
                b_start < a_end
            ):

                overlap_violations += 1


max_sail_violation = int(
    len(sail)
    >
    MAX_SAIL
)


print(
    "SAIL contracts:",
    len(sail)
)

print(
    "KILL contracts:",
    len(kill)
)

print(
    "Contract violations:",
    contract_violations
)

print(
    "Capacity violations:",
    capacity_violations_final
)

print(
    "Class violations:",
    class_violations_final
)

print(
    "Temporal overlap violations:",
    overlap_violations
)

print(
    "Max Sail violation:",
    max_sail_violation
)


if any(
    [
        contract_violations,
        capacity_violations_final,
        class_violations_final,
        overlap_violations,
        max_sail_violation,
    ]
):

    raise RuntimeError(
        "Final production solution failed validation."
    )


# =============================================================================
# ECONOMIC TOTALS
# =============================================================================

bear_total = float(
    sail[
        "bear_incremental"
    ].sum()
)

base_total = float(
    sail[
        "base_incremental"
    ].sum()
)

bull_total = float(
    sail[
        "bull_incremental"
    ].sum()
)

worst_total = float(
    sail[
        "worst_incremental"
    ].sum()
)

expected_total = float(
    sail[
        "expected_incremental"
    ].sum()
)

bunker_total = float(
    sail[
        "bunker_cost_usd"
    ].sum()
)

opex_total = float(
    sail[
        "opex_cost_live_usd"
    ].sum()
)

voyage_cost_total = float(
    sail[
        "total_voyage_cost_usd"
    ].sum()
)


# =============================================================================
# FINAL SOLUTION TABLE
# =============================================================================

sail[
    "decision"
] = "SAIL"


sail[
    "bunker_price_usd_per_mt"
] = bunker_price


final_columns = [
    "contract_id",
    "route_id",
    "origin",
    "destination",
    "cargo_type",
    "contract_volume_mt",
    "imo",
    "vessel_name",
    "vessel_dwt",
    "vessel_class",
    "contract_class",
    "departure_date",
    "estimated_eta",
    "bear_rate",
    "base_rate",
    "bull_rate",
    "bunker_price_usd_per_mt",
    "bunker_cost_usd",
    "opex_cost_live_usd",
    "other_voyage_cost_live_usd",
    "total_voyage_cost_usd",
    "bear_sail",
    "base_sail",
    "bull_sail",
    "bear_incremental",
    "base_incremental",
    "bull_incremental",
    "worst_incremental",
    "expected_incremental",
    "decision",
]


final_columns = [
    c
    for c in final_columns
    if c in sail.columns
]


sail[
    final_columns
].to_csv(
    FINAL_FILE,
    index=False,
)


# =============================================================================
# KILL TABLE
# =============================================================================

kill.to_csv(
    KILL_FILE,
    index=False,
)


# =============================================================================
# VESSEL SCHEDULE
# =============================================================================

if sail.empty:

    vessel_schedule = pd.DataFrame()

else:

    vessel_schedule = (
        sail[
            [
                "imo",
                "vessel_name",
                "departure_date",
                "estimated_eta",
                "contract_id",
                "route_id",
                "origin",
                "destination",
                "contract_volume_mt",
                "worst_incremental",
                "expected_incremental",
            ]
        ]
        .sort_values(
            [
                "imo",
                "departure_date",
            ]
        )
        .reset_index(
            drop=True
        )
    )


    vessel_schedule[
        "voyage_sequence"
    ] = (
        vessel_schedule
        .groupby(
            "imo"
        )
        .cumcount()
        +
        1
    )


vessel_schedule.to_csv(
    SCHEDULE_FILE,
    index=False,
)


# =============================================================================
# CONTRACT DECISION TABLE
# =============================================================================

decision_rows = []


for cid in all_contracts:

    selected_rows = sail[
        sail[
            "contract_id"
        ]
        ==
        cid
    ]


    if not selected_rows.empty:

        r = selected_rows.iloc[0]

        decision_rows.append(
            {
                "contract_id":
                    cid,

                "decision":
                    "SAIL",

                "imo":
                    r[
                        "imo"
                    ],

                "vessel_name":
                    r[
                        "vessel_name"
                    ],

                "route_id":
                    r[
                        "route_id"
                    ],

                "origin":
                    r[
                        "origin"
                    ],

                "destination":
                    r[
                        "destination"
                    ],

                "departure_date":
                    r[
                        "departure_date"
                    ],

                "estimated_eta":
                    r[
                        "estimated_eta"
                    ],

                "worst_incremental":
                    r[
                        "worst_incremental"
                    ],

                "base_incremental":
                    r[
                        "base_incremental"
                    ],

                "expected_incremental":
                    r[
                        "expected_incremental"
                    ],
            }
        )


    else:

        group = candidates[
            candidates[
                "contract_id"
            ]
            ==
            cid
        ]


        best = group.loc[
            group[
                "worst_incremental"
            ].idxmax()
        ]


        decision_rows.append(
            {
                "contract_id":
                    cid,

                "decision":
                    "KILL",

                "imo":
                    best[
                        "imo"
                    ],

                "vessel_name":
                    best[
                        "vessel_name"
                    ],

                "route_id":
                    best[
                        "route_id"
                    ],

                "origin":
                    best[
                        "origin"
                    ],

                "destination":
                    best[
                        "destination"
                    ],

                "departure_date":
                    best[
                        "departure_date"
                    ],

                "estimated_eta":
                    best[
                        "estimated_eta"
                    ],

                "worst_incremental":
                    best[
                        "worst_incremental"
                    ],

                "base_incremental":
                    best[
                        "base_incremental"
                    ],

                "expected_incremental":
                    best[
                        "expected_incremental"
                    ],
            }
        )


decision_table = pd.DataFrame(
    decision_rows
)


decision_table.to_csv(
    DECISIONS_FILE,
    index=False,
)


# =============================================================================
# 12/12 SUMMARY
# =============================================================================

print()
print("=" * 80)
print("12/12 - SAVING SUMMARY")
print("=" * 80)
print()


summary = pd.DataFrame(
    [
        {
            "generated_utc":
                now_utc(),

            "status":
                status,

            "input_step51u_rows":
                len(universe),

            "economic_candidate_rows":
                len(candidates),

            "input_contracts":
                len(contract_groups),

            "input_vessels":
                candidates[
                    "imo"
                ].nunique(),

            "input_routes":
                candidates[
                    "route_id"
                ].nunique(),

            "final_sail_contracts":
                len(sail),

            "final_kill_contracts":
                len(kill),

            "final_sail_vessels":
                sail[
                    "imo"
                ].nunique(),

            "final_sail_routes":
                sail[
                    "route_id"
                ].nunique(),

            "final_departure_dates":
                sail[
                    "departure_date"
                ].nunique(),

            "temporal_conflict_edges":
                len(conflicts),

            "bear_incremental_usd":
                bear_total,

            "base_incremental_usd":
                base_total,

            "bull_incremental_usd":
                bull_total,

            "worst_case_incremental_usd":
                worst_total,

            "expected_incremental_usd":
                expected_total,

            "bunker_cost_total_usd":
                bunker_total,

            "opex_cost_total_usd":
                opex_total,

            "voyage_cost_total_usd":
                voyage_cost_total,

            "live_bunker_price_usd_per_mt":
                bunker_price,

            "max_sail":
                MAX_SAIL,

            "risk_ratio":
                RISK_RATIO,

            "solve_seconds":
                solve_seconds,

            "contract_violations":
                contract_violations,

            "capacity_violations":
                capacity_violations_final,

            "class_violations":
                class_violations_final,

            "temporal_overlap_violations":
                overlap_violations,

            "myshiptracking_api_calls":
                0,

            "myshiptracking_credits":
                0,

            "oilpriceapi_calls":
                0,

            "status_detail":
                "FINAL_PRODUCTION_MILP_COMPLETE",
        }
    ]
)


summary.to_csv(
    SUMMARY_FILE,
    index=False,
)


# =============================================================================
# QUALITY
# =============================================================================

quality_rows = [
    (
        "step51u_input_rows",
        len(universe),
    ),

    (
        "economic_candidate_rows",
        len(candidates),
    ),

    (
        "input_contracts",
        len(contract_groups),
    ),

    (
        "input_vessels",
        candidates[
            "imo"
        ].nunique(),
    ),

    (
        "input_routes",
        candidates[
            "route_id"
        ].nunique(),
    ),

    (
        "temporal_conflict_edges",
        len(conflicts),
    ),

    (
        "final_sail_contracts",
        len(sail),
    ),

    (
        "final_kill_contracts",
        len(kill),
    ),

    (
        "final_sail_vessels",
        sail[
            "imo"
        ].nunique(),
    ),

    (
        "final_sail_routes",
        sail[
            "route_id"
        ].nunique(),
    ),

    (
        "positive_worst_case_candidates",
        int(
            (
                candidates[
                    "worst_incremental"
                ]
                >
                0
            ).sum()
        ),
    ),

    (
        "contract_violations",
        contract_violations,
    ),

    (
        "capacity_violations",
        capacity_violations_final,
    ),

    (
        "class_violations",
        class_violations_final,
    ),

    (
        "temporal_overlap_violations",
        overlap_violations,
    ),

    (
        "max_sail_violation",
        max_sail_violation,
    ),

    (
        "myshiptracking_api_calls",
        0,
    ),

    (
        "myshiptracking_credits_consumed",
        0,
    ),

    (
        "oilpriceapi_calls",
        0,
    ),
]


quality = pd.DataFrame(
    quality_rows,
    columns=[
        "metric",
        "value",
    ],
)


quality.to_csv(
    QUALITY_FILE,
    index=False,
)


# =============================================================================
# REPORT
# =============================================================================

report = {
    "generated_utc":
        now_utc(),

    "status":
        status,

    "architecture":
        {
            "candidate_source":
                "step51u_full_production_universe",

            "preselected_solution_used":
                False,

            "step51p_used_for_decision_generation":
                False,

            "step51s_used_for_decision_generation":
                False,

            "dwt_is_hard_constraint":
                True,

            "exact_class_is_hard_constraint":
                True,

            "live_bunker_used":
                True,
        },

    "configuration":
        {
            "maximum_sail":
                MAX_SAIL,

            "risk_ratio":
                RISK_RATIO,

            "time_limit_seconds":
                TIME_LIMIT,
        },

    "input":
        {
            "step51u_rows":
                len(universe),

            "economic_rows":
                len(candidates),

            "contracts":
                len(contract_groups),

            "vessels":
                candidates[
                    "imo"
                ].nunique(),

            "routes":
                candidates[
                    "route_id"
                ].nunique(),
        },

    "result":
        {
            "sail_contracts":
                len(sail),

            "kill_contracts":
                len(kill),

            "sail_vessels":
                sail[
                    "imo"
                ].nunique(),

            "sail_routes":
                sail[
                    "route_id"
                ].nunique(),

            "bear_incremental_usd":
                bear_total,

            "base_incremental_usd":
                base_total,

            "bull_incremental_usd":
                bull_total,

            "worst_case_incremental_usd":
                worst_total,

            "expected_incremental_usd":
                expected_total,

            "bunker_cost_total_usd":
                bunker_total,

            "opex_cost_total_usd":
                opex_total,

            "voyage_cost_total_usd":
                voyage_cost_total,
        },

    "validation":
        {
            "contract_violations":
                contract_violations,

            "capacity_violations":
                capacity_violations_final,

            "class_violations":
                class_violations_final,

            "temporal_overlap_violations":
                overlap_violations,

            "max_sail_violation":
                max_sail_violation,
        },

    "bunker":
        {
            "price_usd_per_metric_ton":
                bunker_price,
        },

    "api":
        {
            "myshiptracking_calls":
                0,

            "myshiptracking_credits":
                0,

            "oilpriceapi_calls":
                0,
        },

    "outputs":
        {
            "final_solution":
                str(FINAL_FILE),

            "kill_summary":
                str(KILL_FILE),

            "vessel_schedule":
                str(SCHEDULE_FILE),

            "contract_decisions":
                str(DECISIONS_FILE),

            "summary":
                str(SUMMARY_FILE),

            "quality":
                str(QUALITY_FILE),
        },
}


with REPORT_FILE.open(
    "w",
    encoding="utf-8",
) as f:

    json.dump(
        report,
        f,
        indent=2,
        default=str,
    )


# =============================================================================
# FINAL
# =============================================================================

print()
print("=" * 80)
print("STEP 51V COMPLETE")
print("=" * 80)
print()

print(
    "CBC status:",
    status
)

print(
    "51U candidate rows:",
    len(universe)
)

print(
    "Economic candidate rows:",
    len(candidates)
)

print(
    "Contracts:",
    len(contract_groups)
)

print(
    "SAIL contracts:",
    len(sail)
)

print(
    "KILL contracts:",
    len(kill)
)

print(
    "SAIL vessels:",
    sail[
        "imo"
    ].nunique()
)

print(
    "SAIL routes:",
    sail[
        "route_id"
    ].nunique()
)

print(
    "Departure dates:",
    sail[
        "departure_date"
    ].nunique()
)

print()
print(
    "Bear incremental:",
    bear_total
)

print(
    "Base incremental:",
    base_total
)

print(
    "Bull incremental:",
    bull_total
)

print(
    "Worst-case incremental:",
    worst_total
)

print(
    "Expected incremental:",
    expected_total
)

print()
print(
    "Bunker cost:",
    bunker_total
)

print(
    "OPEX cost:",
    opex_total
)

print(
    "Total voyage cost:",
    voyage_cost_total
)

print()
print(
    "Live VLSFO:",
    bunker_price,
    "USD/MT"
)

print()
print(
    "Contract violations:",
    contract_violations
)

print(
    "Capacity violations:",
    capacity_violations_final
)

print(
    "Class violations:",
    class_violations_final
)

print(
    "Temporal overlap violations:",
    overlap_violations
)

print(
    "Max Sail violation:",
    max_sail_violation
)

print()
print(
    "MyShipTracking API calls: 0"
)

print(
    "MyShipTracking credits: 0"
)

print(
    "OilPriceAPI calls: 0"
)

print()
print("SAVED:")
print(
    FINAL_FILE
)

print(
    KILL_FILE
)

print(
    SCHEDULE_FILE
)

print(
    DECISIONS_FILE
)

print(
    SUMMARY_FILE
)

print(
    QUALITY_FILE
)

print(
    REPORT_FILE
)
