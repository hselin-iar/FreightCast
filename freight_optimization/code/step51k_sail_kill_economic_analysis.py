#!/usr/bin/env python3

"""
STEP 51K - SAIL / KILL ECONOMIC EXPLANATION

LOCAL ONLY
----------
MyShipTracking API calls: 0
MyShipTracking credits: 0
OilPriceAPI calls: 0

PURPOSE
-------
Explain why every contract is SAIL or KILL using the current:
    - contract economics
    - AIS vessel candidates
    - date feasibility
    - live VLSFO bunker price

This is diagnostic only.
It does NOT modify Step 51I.
It does NOT call any API.

IMPORTANT
---------
All vessel/date fields are made explicit before merges so pandas cannot
silently create vessel_name_x / vessel_name_y or similar schema problems.
"""

from pathlib import Path
import json

import numpy as np
import pandas as pd


# =============================================================================
# PATHS
# =============================================================================

ROOT = Path(
    "/home/aryashekhar/freight-optimization"
)

PROCESSED = ROOT / "data" / "processed"
OUTPUTS = ROOT / "outputs"

CONTRACT_FILE = (
    PROCESSED / "step23_contract_sail_kill.csv"
)

VESSEL_FILE = (
    PROCESSED / "step49g_vessel_candidates.csv"
)

DATE_FILE = (
    PROCESSED / "step51a_optimizer_candidates.csv"
)

BUNKER_FILE = (
    PROCESSED / "step50a_bunker_current.csv"
)

SOLUTION_FILE = (
    PROCESSED / "step51i_contract_fleet_solution.csv"
)

ANALYSIS_FILE = (
    OUTPUTS / "step51k_contract_economic_analysis.csv"
)

PRIORITY_FILE = (
    OUTPUTS / "step51k_priority_rank.csv"
)

SUMMARY_FILE = (
    OUTPUTS / "step51k_summary.csv"
)

REPORT_FILE = (
    OUTPUTS / "step51k_report.json"
)


# =============================================================================
# HELPERS
# =============================================================================

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


def normalize_class(value):

    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass

    s = (
        str(value)
        .strip()
        .upper()
        .replace("-", "")
        .replace("_", "")
        .replace(" ", "")
    )

    if "PANAMAX" in s:
        return "PANAMAX"

    if "SUPRAMAX" in s:
        return "SUPRAMAX"

    if "ULTRAMAX" in s:
        return "ULTRAMAX"

    if "CAPESIZE" in s:
        return "CAPE"

    if "CAPE" in s:
        return "CAPE"

    if "VLOC" in s:
        return "CAPE"

    if "HANDY" in s:
        return "HANDYSIZE"

    return s


def numeric(series):
    return pd.to_numeric(
        series,
        errors="coerce",
    )


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
            f"{name} missing columns:\n"
            +
            "\n".join(missing)
        )


def now_utc():
    return pd.Timestamp.now(
        tz="UTC"
    ).isoformat()


# =============================================================================
# START
# =============================================================================

print()
print("=" * 80)
print("STEP 51K - SAIL / KILL ECONOMIC EXPLANATION")
print("=" * 80)
print()

print("MODE: LOCAL ONLY")
print("MyShipTracking API calls: 0")
print("MyShipTracking credits: 0")
print("OilPriceAPI calls: 0")
print()


# =============================================================================
# FILE CHECK
# =============================================================================

for path in [
    CONTRACT_FILE,
    VESSEL_FILE,
    DATE_FILE,
    BUNKER_FILE,
    SOLUTION_FILE,
]:

    if not path.exists():

        raise FileNotFoundError(
            str(path)
        )


# =============================================================================
# 1. LOAD
# =============================================================================

print("=" * 80)
print("1/8 - LOADING DATA")
print("=" * 80)
print()

contracts = pd.read_csv(
    CONTRACT_FILE
)

vessels = pd.read_csv(
    VESSEL_FILE
)

dates = pd.read_csv(
    DATE_FILE
)

solution = pd.read_csv(
    SOLUTION_FILE
)

bunker = pd.read_csv(
    BUNKER_FILE
)

print(
    "Contract rows:",
    len(contracts)
)

print(
    "Vessel rows:",
    len(vessels)
)

print(
    "Date rows:",
    len(dates)
)

print(
    "Solution rows:",
    len(solution)
)


# =============================================================================
# 2. NORMALIZE / VALIDATE
# =============================================================================

print()
print("=" * 80)
print("2/8 - NORMALIZING")
print("=" * 80)
print()


require(
    contracts,
    [
        "contract_id",
        "route_id",
        "origin",
        "destination",
        "vessel_class",
        "cargo_type",
        "scenario",
        "scenario_route_freight_rate",
        "contract_volume_mt",
        "kill_penalty_usd",
        "kill_alternative_value_usd",
    ],
    "Contracts",
)

require(
    vessels,
    [
        "imo",
        "vessel_name",
        "dwt",
    ],
    "Vessels",
)

require(
    dates,
    [
        "imo",
        "route_id",
        "departure_date",
        "estimated_eta",
    ],
    "Date candidates",
)

require(
    solution,
    [
        "contract_id",
        "decision",
    ],
    "Solution",
)

require(
    bunker,
    [
        "price_usd_per_metric_ton",
    ],
    "Bunker",
)


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
    "vessel_class_norm"
] = (
    contracts[
        "vessel_class"
    ]
    .apply(
        normalize_class
    )
)

for col in [
    "scenario_route_freight_rate",
    "contract_volume_mt",
    "kill_penalty_usd",
    "kill_alternative_value_usd",
]:

    contracts[col] = numeric(
        contracts[col]
    )


vessels[
    "imo"
] = normalize_id(
    vessels[
        "imo"
    ]
)

vessels[
    "dwt"
] = numeric(
    vessels[
        "dwt"
    ]
)

if "dwt_class" in vessels.columns:

    vessels[
        "vessel_class_norm"
    ] = (
        vessels[
            "dwt_class"
        ]
        .apply(
            normalize_class
        )
    )

else:

    vessels[
        "vessel_class_norm"
    ] = ""


# Important:
# Keep vessel identity in ONE place only.

vessel_master = (
    vessels[
        [
            "imo",
            "vessel_name",
            "dwt",
            "vessel_class_norm",
        ]
    ]
    .drop_duplicates(
        "imo",
        keep="first",
    )
    .copy()
)


dates[
    "imo"
] = normalize_id(
    dates[
        "imo"
    ]
)

dates[
    "route_id"
] = normalize_id(
    dates[
        "route_id"
    ]
)

dates[
    "departure_date"
] = pd.to_datetime(
    dates[
        "departure_date"
    ],
    errors="coerce",
)

dates[
    "estimated_eta"
] = pd.to_datetime(
    dates[
        "estimated_eta"
    ],
    utc=True,
    errors="coerce",
)


for col in [
    "reposition_distance_nm",
    "reposition_hours",
    "route_distance_nm",
    "route_speed_knots",
    "sea_hours",
    "port_days",
    "total_voyage_hours",
    "total_voyage_days",
]:

    if col in dates.columns:

        dates[col] = numeric(
            dates[col]
        )


solution[
    "contract_id"
] = normalize_id(
    solution[
        "contract_id"
    ]
)

solution[
    "decision"
] = (
    solution[
        "decision"
    ]
    .astype(str)
    .str.upper()
    .str.strip()
)


bunker_price = float(
    bunker[
        "price_usd_per_metric_ton"
    ].iloc[0]
)

print(
    "Current VLSFO:",
    bunker_price,
    "USD/MT"
)


# =============================================================================
# 3. CONTRACT BASE
# =============================================================================

print()
print("=" * 80)
print("3/8 - BUILDING CONTRACT ECONOMIC BASE")
print("=" * 80)
print()


contract_meta = (
    contracts
    [
        [
            "contract_id",
            "route_id",
            "origin",
            "destination",
            "vessel_class",
            "vessel_class_norm",
            "cargo_type",
            "contract_volume_mt",
        ]
    ]
    .drop_duplicates(
        "contract_id",
        keep="first",
    )
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
    "kill_value_usd"
] = (
    numeric(
        kill[
            "kill_alternative_value_usd"
        ]
    )
    -
    numeric(
        kill[
            "kill_penalty_usd"
        ]
    )
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
                "kill_value_usd",
            ]
        ],
        on="contract_id",
        how="left",
    )
)


# =============================================================================
# ROUTE ECONOMICS
# =============================================================================

route_econ = (
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
        ],
        keep="last",
    )
)


for col in [
    "fuel_consumption_mt",
    "bunker_mt_per_day",
    "daily_opex_usd",
    "opex_cost_usd",
    "other_voyage_cost_usd",
    "total_voyage_days",
]:

    route_econ[col] = numeric(
        route_econ[col]
    )


route_econ_base = (
    route_econ[
        route_econ[
            "scenario"
        ]
        ==
        "base"
    ]
    .copy()
    .rename(
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
                "route_total_voyage_days",
        }
    )
    .drop_duplicates(
        "route_id",
        keep="first",
    )
)


# =============================================================================
# 4. BUILD CLEAN VESSEL/DATE POOL
# =============================================================================

print()
print("=" * 80)
print("4/8 - BUILDING CLEAN VESSEL / DATE POOL")
print("=" * 80)
print()


# DO NOT carry vessel_name from dates.
#
# Step 51A may contain its own vessel columns.
# We intentionally select only physical/date fields here and then merge
# the authoritative vessel master.

date_fields = [
    "imo",
    "route_id",
    "departure_date",
    "estimated_eta",
]

for col in [
    "reposition_distance_nm",
    "reposition_hours",
    "route_distance_nm",
    "route_speed_knots",
    "sea_hours",
    "port_days",
    "total_voyage_hours",
    "total_voyage_days",
]:

    if col in dates.columns:

        date_fields.append(
            col
        )


date_pool = (
    dates[
        date_fields
    ]
    .drop_duplicates(
        [
            "imo",
            "route_id",
            "departure_date",
        ],
        keep="first",
    )
)


# Authoritative vessel merge.

date_pool = date_pool.merge(
    vessel_master[
        [
            "imo",
            "vessel_name",
            "dwt",
            "vessel_class_norm",
        ]
    ],
    on="imo",
    how="inner",
)


# Explicit sanity check.

require(
    date_pool,
    [
        "imo",
        "vessel_name",
        "dwt",
        "vessel_class_norm",
        "route_id",
        "departure_date",
        "estimated_eta",
    ],
    "Clean vessel/date pool",
)


print(
    "Vessel/date pool:",
    len(date_pool)
)

print(
    "Unique vessels:",
    date_pool[
        "imo"
    ].nunique()
)

print(
    "Unique routes:",
    date_pool[
        "route_id"
    ].nunique()
)


# =============================================================================
# 5. ECONOMIC ANALYSIS
# =============================================================================

print()
print("=" * 80)
print("5/8 - ANALYZING EACH CONTRACT")
print("=" * 80)
print()


selected_contract_ids = set(
    solution.loc[
        solution[
            "decision"
        ]
        ==
        "SAIL",
        "contract_id",
    ]
)


rows = []


for _, contract in contract_meta.iterrows():

    cid = contract[
        "contract_id"
    ]

    route_id = contract[
        "route_id"
    ]

    volume = float(
        contract[
            "contract_volume_mt"
        ]
    )

    required_class = contract[
        "vessel_class_norm"
    ]

    kill_value = float(
        contract[
            "kill_value_usd"
        ]
    )


    route_pool = (
        date_pool[
            date_pool[
                "route_id"
            ]
            ==
            route_id
        ]
        .copy()
    )


    candidate_rows = len(
        route_pool
    )

    candidate_vessels = (
        route_pool[
            "imo"
        ]
        .nunique()
    )


    # -------------------------------------------------------------------------
    # NO ROUTE/DATA CANDIDATE
    # -------------------------------------------------------------------------

    if route_pool.empty:

        rows.append(
            {
                "contract_id":
                    cid,

                "route_id":
                    route_id,

                "origin":
                    contract[
                        "origin"
                    ],

                "destination":
                    contract[
                        "destination"
                    ],

                "vessel_class":
                    contract[
                        "vessel_class"
                    ],

                "cargo_type":
                    contract[
                        "cargo_type"
                    ],

                "contract_volume_mt":
                    volume,

                "candidate_rows":
                    0,

                "candidate_vessels":
                    0,

                "capacity_pass_rows":
                    0,

                "capacity_class_pass_rows":
                    0,

                "best_vessel":
                    "",

                "best_vessel_imo":
                    "",

                "best_departure_date":
                    "",

                "best_eta":
                    "",

                "best_dwt":
                    np.nan,

                "bear_sail_value_usd":
                    np.nan,

                "base_sail_value_usd":
                    np.nan,

                "bull_sail_value_usd":
                    np.nan,

                "kill_value_usd":
                    kill_value,

                "bear_incremental_value_usd":
                    np.nan,

                "base_incremental_value_usd":
                    np.nan,

                "bull_incremental_value_usd":
                    np.nan,

                "best_expected_incremental_usd":
                    np.nan,

                "best_worst_case_incremental_usd":
                    np.nan,

                "optimizer_decision":
                    (
                        "SAIL"
                        if cid
                        in selected_contract_ids
                        else
                        "KILL"
                    ),

                "reason":
                    "NO_CURRENT_ROUTE_DATE_CANDIDATE",
            }
        )

        continue


    # -------------------------------------------------------------------------
    # CAPACITY
    # -------------------------------------------------------------------------

    route_pool[
        "capacity_pass"
    ] = (
        route_pool[
            "dwt"
        ]
        >=
        volume
    )


    capacity_pool = route_pool[
        route_pool[
            "capacity_pass"
        ]
    ].copy()


    capacity_pass_rows = len(
        capacity_pool
    )


    if capacity_pool.empty:

        rows.append(
            {
                "contract_id":
                    cid,

                "route_id":
                    route_id,

                "origin":
                    contract[
                        "origin"
                    ],

                "destination":
                    contract[
                        "destination"
                    ],

                "vessel_class":
                    contract[
                        "vessel_class"
                    ],

                "cargo_type":
                    contract[
                        "cargo_type"
                    ],

                "contract_volume_mt":
                    volume,

                "candidate_rows":
                    candidate_rows,

                "candidate_vessels":
                    candidate_vessels,

                "capacity_pass_rows":
                    0,

                "capacity_class_pass_rows":
                    0,

                "best_vessel":
                    "",

                "best_vessel_imo":
                    "",

                "best_departure_date":
                    "",

                "best_eta":
                    "",

                "best_dwt":
                    np.nan,

                "bear_sail_value_usd":
                    np.nan,

                "base_sail_value_usd":
                    np.nan,

                "bull_sail_value_usd":
                    np.nan,

                "kill_value_usd":
                    kill_value,

                "bear_incremental_value_usd":
                    np.nan,

                "base_incremental_value_usd":
                    np.nan,

                "bull_incremental_value_usd":
                    np.nan,

                "best_expected_incremental_usd":
                    np.nan,

                "best_worst_case_incremental_usd":
                    np.nan,

                "optimizer_decision":
                    (
                        "SAIL"
                        if cid
                        in selected_contract_ids
                        else
                        "KILL"
                    ),

                "reason":
                    "CAPACITY_FILTER",
            }
        )

        continue


    # -------------------------------------------------------------------------
    # CLASS
    # -------------------------------------------------------------------------

    capacity_pool[
        "class_pass"
    ] = capacity_pool.apply(
        lambda row:
            (
                required_class == ""
                or
                row[
                    "vessel_class_norm"
                ] == ""
                or
                row[
                    "vessel_class_norm"
                ]
                ==
                required_class
            ),
        axis=1,
    )


    feasible = capacity_pool[
        capacity_pool[
            "class_pass"
        ]
    ].copy()


    if feasible.empty:

        rows.append(
            {
                "contract_id":
                    cid,

                "route_id":
                    route_id,

                "origin":
                    contract[
                        "origin"
                    ],

                "destination":
                    contract[
                        "destination"
                    ],

                "vessel_class":
                    contract[
                        "vessel_class"
                    ],

                "cargo_type":
                    contract[
                        "cargo_type"
                    ],

                "contract_volume_mt":
                    volume,

                "candidate_rows":
                    candidate_rows,

                "candidate_vessels":
                    candidate_vessels,

                "capacity_pass_rows":
                    capacity_pass_rows,

                "capacity_class_pass_rows":
                    0,

                "best_vessel":
                    "",

                "best_vessel_imo":
                    "",

                "best_departure_date":
                    "",

                "best_eta":
                    "",

                "best_dwt":
                    np.nan,

                "bear_sail_value_usd":
                    np.nan,

                "base_sail_value_usd":
                    np.nan,

                "bull_sail_value_usd":
                    np.nan,

                "kill_value_usd":
                    kill_value,

                "bear_incremental_value_usd":
                    np.nan,

                "base_incremental_value_usd":
                    np.nan,

                "bull_incremental_value_usd":
                    np.nan,

                "best_expected_incremental_usd":
                    np.nan,

                "best_worst_case_incremental_usd":
                    np.nan,

                "optimizer_decision":
                    (
                        "SAIL"
                        if cid
                        in selected_contract_ids
                        else
                        "KILL"
                    ),

                "reason":
                    "CLASS_FILTER",
            }
        )

        continue


    # -------------------------------------------------------------------------
    # ROUTE ECONOMICS
    # -------------------------------------------------------------------------

    feasible = feasible.merge(
        route_econ_base[
            [
                "route_id",
                "route_fuel_consumption_mt",
                "route_bunker_mt_per_day",
                "route_daily_opex_usd",
                "route_opex_cost_usd",
                "route_other_cost_usd",
                "route_total_voyage_days",
            ]
        ],
        on="route_id",
        how="left",
    )


    # -------------------------------------------------------------------------
    # VOYAGE DAYS
    # -------------------------------------------------------------------------

    feasible[
        "voyage_days"
    ] = feasible[
        "route_total_voyage_days"
    ]


    if "total_voyage_days" in feasible.columns:

        feasible[
            "voyage_days"
        ] = feasible[
            "total_voyage_days"
        ].combine_first(
            feasible[
                "route_total_voyage_days"
            ]
        )


    # -------------------------------------------------------------------------
    # BUNKER
    # -------------------------------------------------------------------------

    feasible[
        "bunker_cost_usd"
    ] = (
        feasible[
            "route_fuel_consumption_mt"
        ]
        *
        bunker_price
    )


    fallback_bunker = (
        feasible[
            "bunker_cost_usd"
        ].isna()
        &
        feasible[
            "route_bunker_mt_per_day"
        ].notna()
        &
        feasible[
            "voyage_days"
        ].notna()
    )


    feasible.loc[
        fallback_bunker,
        "bunker_cost_usd",
    ] = (
        feasible.loc[
            fallback_bunker,
            "route_bunker_mt_per_day",
        ]
        *
        feasible.loc[
            fallback_bunker,
            "voyage_days",
        ]
        *
        bunker_price
    )


    # -------------------------------------------------------------------------
    # OPEX
    # -------------------------------------------------------------------------

    feasible[
        "opex_live_usd"
    ] = (
        feasible[
            "route_daily_opex_usd"
        ]
        *
        feasible[
            "voyage_days"
        ]
    )


    fallback_opex = (
        feasible[
            "opex_live_usd"
        ].isna()
        &
        feasible[
            "route_opex_cost_usd"
        ].notna()
    )


    feasible.loc[
        fallback_opex,
        "opex_live_usd",
    ] = feasible.loc[
        fallback_opex,
        "route_opex_cost_usd",
    ]


    feasible[
        "total_cost_usd"
    ] = (
        feasible[
            "bunker_cost_usd"
        ]
        +
        feasible[
            "opex_live_usd"
        ]
        +
        feasible[
            "route_other_cost_usd"
        ]
    )


    # -------------------------------------------------------------------------
    # SAIL VALUES
    # -------------------------------------------------------------------------

    feasible[
        "bear_sail_value_usd"
    ] = (
        float(
            contract[
                "bear_rate"
            ]
        )
        *
        volume
        -
        feasible[
            "total_cost_usd"
        ]
    )


    feasible[
        "base_sail_value_usd"
    ] = (
        float(
            contract[
                "base_rate"
            ]
        )
        *
        volume
        -
        feasible[
            "total_cost_usd"
        ]
    )


    feasible[
        "bull_sail_value_usd"
    ] = (
        float(
            contract[
                "bull_rate"
            ]
        )
        *
        volume
        -
        feasible[
            "total_cost_usd"
        ]
    )


    # -------------------------------------------------------------------------
    # INCREMENTAL VS KILL
    # -------------------------------------------------------------------------

    feasible[
        "bear_incremental"
    ] = (
        feasible[
            "bear_sail_value_usd"
        ]
        -
        kill_value
    )


    feasible[
        "base_incremental"
    ] = (
        feasible[
            "base_sail_value_usd"
        ]
        -
        kill_value
    )


    feasible[
        "bull_incremental"
    ] = (
        feasible[
            "bull_sail_value_usd"
        ]
        -
        kill_value
    )


    feasible[
        "expected_incremental"
    ] = feasible[
        [
            "bear_incremental",
            "base_incremental",
            "bull_incremental",
        ]
    ].mean(
        axis=1
    )


    feasible[
        "worst_incremental"
    ] = feasible[
        [
            "bear_incremental",
            "base_incremental",
            "bull_incremental",
        ]
    ].min(
        axis=1
    )


    # -------------------------------------------------------------------------
    # BEST AVAILABLE CANDIDATE
    # -------------------------------------------------------------------------

    feasible = (
        feasible
        .sort_values(
            [
                "worst_incremental",
                "expected_incremental",
            ],
            ascending=[
                False,
                False,
            ],
        )
        .reset_index(
            drop=True
        )
    )


    best = feasible.iloc[0]


    # -------------------------------------------------------------------------
    # EXPLAIN KILL
    # -------------------------------------------------------------------------

    if cid in selected_contract_ids:

        decision = "SAIL"
        reason = "SAIL"

    elif float(
        best[
            "worst_incremental"
        ]
    ) > 0:

        decision = "KILL"

        reason = (
            "KILL_AVAILABLE_BUT_PORTFOLIO_OUTCOMPETED"
        )

    elif float(
        best[
            "expected_incremental"
        ]
    ) > 0:

        decision = "KILL"

        reason = (
            "KILL_AVAILABLE_BUT_SCENARIO_RISK"
        )

    else:

        decision = "KILL"

        reason = (
            "KILL_AVAILABLE_ECONOMICALLY_WEAK"
        )


    # -------------------------------------------------------------------------
    # SAVE ROW
    # -------------------------------------------------------------------------

    rows.append(
        {
            "contract_id":
                cid,

            "route_id":
                route_id,

            "origin":
                contract[
                    "origin"
                ],

            "destination":
                contract[
                    "destination"
                ],

            "vessel_class":
                contract[
                    "vessel_class"
                ],

            "cargo_type":
                contract[
                    "cargo_type"
                ],

            "contract_volume_mt":
                volume,

            "candidate_rows":
                candidate_rows,

            "candidate_vessels":
                candidate_vessels,

            "capacity_pass_rows":
                capacity_pass_rows,

            "capacity_class_pass_rows":
                len(feasible),

            "best_vessel":
                best[
                    "vessel_name"
                ],

            "best_vessel_imo":
                best[
                    "imo"
                ],

            "best_departure_date":
                best[
                    "departure_date"
                ],

            "best_eta":
                best[
                    "estimated_eta"
                ],

            "best_dwt":
                best[
                    "dwt"
                ],

            "bear_sail_value_usd":
                best[
                    "bear_sail_value_usd"
                ],

            "base_sail_value_usd":
                best[
                    "base_sail_value_usd"
                ],

            "bull_sail_value_usd":
                best[
                    "bull_sail_value_usd"
                ],

            "kill_value_usd":
                kill_value,

            "bear_incremental_value_usd":
                best[
                    "bear_incremental"
                ],

            "base_incremental_value_usd":
                best[
                    "base_incremental"
                ],

            "bull_incremental_value_usd":
                best[
                    "bull_incremental"
                ],

            "best_expected_incremental_usd":
                best[
                    "expected_incremental"
                ],

            "best_worst_case_incremental_usd":
                best[
                    "worst_incremental"
                ],

            "optimizer_decision":
                decision,

            "reason":
                reason,
        }
    )


analysis = pd.DataFrame(
    rows
)


# =============================================================================
# 6. PRIORITY
# =============================================================================

print()
print("=" * 80)
print("6/8 - RANKING KILL OPPORTUNITIES")
print("=" * 80)
print()


priority = analysis[
    analysis[
        "optimizer_decision"
    ]
    ==
    "KILL"
].copy()


priority[
    "economic_priority"
] = priority[
    "best_worst_case_incremental_usd"
]


priority = (
    priority
    .sort_values(
        [
            "economic_priority",
            "best_expected_incremental_usd",
        ],
        ascending=[
            False,
            False,
        ],
    )
    .reset_index(
        drop=True
    )
)


priority[
    "priority_rank"
] = (
    priority.index
    +
    1
)


display_cols = [
    "priority_rank",
    "contract_id",
    "reason",
    "candidate_vessels",
    "capacity_class_pass_rows",
    "best_vessel",
    "best_vessel_imo",
    "best_departure_date",
    "best_dwt",
    "kill_value_usd",
    "best_worst_case_incremental_usd",
    "best_expected_incremental_usd",
]


display_cols = [
    c
    for c in display_cols
    if c in priority.columns
]


print(
    priority[
        display_cols
    ]
    .to_string(
        index=False
    )
)


# =============================================================================
# 7. COUNTS
# =============================================================================

print()
print("=" * 80)
print("7/8 - SUMMARY")
print("=" * 80)
print()


sail_count = int(
    (
        analysis[
            "optimizer_decision"
        ]
        ==
        "SAIL"
    ).sum()
)


kill_count = int(
    (
        analysis[
            "optimizer_decision"
        ]
        ==
        "KILL"
    ).sum()
)


no_candidate_count = int(
    (
        analysis[
            "reason"
        ]
        ==
        "NO_CURRENT_ROUTE_DATE_CANDIDATE"
    ).sum()
)


portfolio_outcompeted_count = int(
    (
        analysis[
            "reason"
        ]
        ==
        "KILL_AVAILABLE_BUT_PORTFOLIO_OUTCOMPETED"
    ).sum()
)


scenario_risk_count = int(
    (
        analysis[
            "reason"
        ]
        ==
        "KILL_AVAILABLE_BUT_SCENARIO_RISK"
    ).sum()
)


economically_weak_count = int(
    (
        analysis[
            "reason"
        ]
        ==
        "KILL_AVAILABLE_ECONOMICALLY_WEAK"
    ).sum()
)


capacity_count = int(
    (
        analysis[
            "reason"
        ]
        ==
        "CAPACITY_FILTER"
    ).sum()
)


class_count = int(
    (
        analysis[
            "reason"
        ]
        ==
        "CLASS_FILTER"
    ).sum()
)


positive_worst_count = int(
    (
        analysis[
            "best_worst_case_incremental_usd"
        ]
        > 0
    )
    .fillna(False)
    .sum()
)


positive_expected_count = int(
    (
        analysis[
            "best_expected_incremental_usd"
        ]
        > 0
    )
    .fillna(False)
    .sum()
)


# =============================================================================
# SAVE
# =============================================================================

print()
print("=" * 80)
print("8/8 - SAVING OUTPUTS")
print("=" * 80)
print()


analysis.to_csv(
    ANALYSIS_FILE,
    index=False,
)


priority.to_csv(
    PRIORITY_FILE,
    index=False,
)


summary = pd.DataFrame(
    [
        {
            "generated_utc":
                now_utc(),

            "contracts":
                len(analysis),

            "sail":
                sail_count,

            "kill":
                kill_count,

            "no_current_candidate":
                no_candidate_count,

            "portfolio_outcompeted":
                portfolio_outcompeted_count,

            "scenario_risk":
                scenario_risk_count,

            "economically_weak":
                economically_weak_count,

            "capacity_filter":
                capacity_count,

            "class_filter":
                class_count,

            "positive_worst_case_contracts":
                positive_worst_count,

            "positive_expected_contracts":
                positive_expected_count,

            "bunker_price_usd_per_mt":
                bunker_price,

            "api_calls_myshiptracking":
                0,

            "myshiptracking_credits":
                0,

            "oilpriceapi_calls":
                0,

            "status":
                "SAIL_KILL_ECONOMIC_ANALYSIS_COMPLETE",
        }
    ]
)


summary.to_csv(
    SUMMARY_FILE,
    index=False,
)


report = {
    "generated_utc":
        now_utc(),

    "status":
        "SAIL_KILL_ECONOMIC_ANALYSIS_COMPLETE",

    "counts": {
        "contracts":
            len(analysis),

        "sail":
            sail_count,

        "kill":
            kill_count,

        "no_current_candidate":
            no_candidate_count,

        "portfolio_outcompeted":
            portfolio_outcompeted_count,

        "scenario_risk":
            scenario_risk_count,

        "economically_weak":
            economically_weak_count,

        "capacity_filter":
            capacity_count,

        "class_filter":
            class_count,

        "positive_worst_case_contracts":
            positive_worst_count,

        "positive_expected_contracts":
            positive_expected_count,
    },

    "bunker": {
        "price_usd_per_mt":
            bunker_price,
    },

    "interpretation": [
        (
            "NO_CURRENT_ROUTE_DATE_CANDIDATE indicates AIS/data coverage "
            "limitations, not an economic KILL."
        ),

        (
            "KILL_AVAILABLE_BUT_PORTFOLIO_OUTCOMPETED means the contract "
            "has a positive worst-case Sail-vs-Kill opportunity but lost "
            "under portfolio competition."
        ),

        (
            "KILL_AVAILABLE_BUT_SCENARIO_RISK means expected Sail value "
            "is positive but worst-case Sail-vs-Kill value is non-positive."
        ),

        (
            "KILL_AVAILABLE_ECONOMICALLY_WEAK means the best available "
            "Sail opportunity is not positive versus KILL."
        ),

        (
            "This step is diagnostic only."
        ),

        (
            "No APIs were called."
        ),
    ],

    "api": {
        "myshiptracking_calls":
            0,

        "myshiptracking_credits":
            0,

        "oilpriceapi_calls":
            0,
    },

    "outputs": {
        "analysis":
            str(
                ANALYSIS_FILE
            ),

        "priority":
            str(
                PRIORITY_FILE
            ),

        "summary":
            str(
                SUMMARY_FILE
            ),

        "report":
            str(
                REPORT_FILE
            ),
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
print("STEP 51K COMPLETE")
print("=" * 80)
print()

print(
    "SAIL:",
    sail_count
)

print(
    "KILL:",
    kill_count
)

print(
    "No current candidate:",
    no_candidate_count
)

print(
    "Portfolio outcompeted:",
    portfolio_outcompeted_count
)

print(
    "Scenario risk:",
    scenario_risk_count
)

print(
    "Economically weak:",
    economically_weak_count
)

print(
    "Capacity filter:",
    capacity_count
)

print(
    "Class filter:",
    class_count
)

print(
    "Positive worst-case opportunities:",
    positive_worst_count
)

print(
    "Positive expected opportunities:",
    positive_expected_count
)

print()
print(
    "Live VLSFO:",
    bunker_price,
    "USD/MT"
)

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
print(
    ANALYSIS_FILE
)

print(
    PRIORITY_FILE
)

print(
    SUMMARY_FILE
)

print(
    REPORT_FILE
)
