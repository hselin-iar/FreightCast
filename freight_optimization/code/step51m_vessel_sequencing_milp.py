#!/usr/bin/env python3

"""
STEP 51M - VESSEL SEQUENCING MILP

LOCAL ONLY
----------
No MyShipTracking API calls.
No MyShipTracking credits.
No OilPriceAPI calls.

PURPOSE
-------
Test a corrected vessel scheduling formulation in which a vessel may
perform multiple voyages when the voyage intervals do not overlap.

This is an experimental/diagnostic model and does not overwrite Step 51I.

IMPORTANT TIME HANDLING
-----------------------
All departure / ETA timestamps are normalized to UTC-aware timestamps.

A date-only departure date is interpreted as:
    00:00:00 UTC

This prevents timezone-naive vs timezone-aware comparison failures.
"""

from pathlib import Path
import json
import os
import time

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
    PROCESSED /
    "step23_contract_sail_kill.csv"
)

VESSEL_FILE = (
    PROCESSED /
    "step49g_vessel_candidates.csv"
)

DATE_FILE = (
    PROCESSED /
    "step51a_optimizer_candidates.csv"
)

BUNKER_FILE = (
    PROCESSED /
    "step50a_bunker_current.csv"
)

SELECTED_FILE = (
    OUTPUTS /
    "step51m_selected.csv"
)

CONFLICT_FILE = (
    OUTPUTS /
    "step51m_conflicts.csv"
)

SUMMARY_FILE = (
    OUTPUTS /
    "step51m_summary.csv"
)

QUALITY_FILE = (
    OUTPUTS /
    "step51m_quality.csv"
)

REPORT_FILE = (
    OUTPUTS /
    "step51m_report.json"
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

USE_CLASS_MATCH = (
    os.environ.get(
        "MILP_USE_CLASS_MATCH",
        "1",
    )
    == "1"
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
        .replace(
            "-",
            "",
        )
        .replace(
            "_",
            "",
        )
        .replace(
            " ",
            "",
        )
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

    if "HANDYSIZE" in s:
        return "HANDYSIZE"

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
    cols,
    name,
):

    missing = [
        c
        for c in cols
        if c not in df.columns
    ]

    if missing:

        raise RuntimeError(
            f"{name} missing columns:\n"
            +
            "\n".join(
                missing
            )
        )


def to_utc_timestamp(value):

    """
    Convert anything timestamp-like into a timezone-aware UTC timestamp.

    Examples:
        2026-09-01
            -> 2026-09-01 00:00:00+00:00

        2026-09-20T05:00:00Z
            -> 2026-09-20 05:00:00+00:00
    """

    if value is None:
        return pd.NaT

    try:

        if pd.isna(value):
            return pd.NaT

    except Exception:

        pass

    try:

        ts = pd.Timestamp(
            value
        )

    except Exception:

        return pd.NaT

    if ts.tzinfo is None:

        return ts.tz_localize(
            "UTC"
        )

    return ts.tz_convert(
        "UTC"
    )


def normalize_timestamp_column(
    series
):

    return series.apply(
        to_utc_timestamp
    )


# =============================================================================
# START
# =============================================================================

print()
print("=" * 80)
print("STEP 51M - VESSEL SEQUENCING MILP")
print("=" * 80)
print()

print(
    "MODE: LOCAL ONLY"
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

print(
    "Maximum Sail:",
    MAX_SAIL
)

print(
    "Risk ratio:",
    RISK_RATIO
)

print(
    "Class matching:",
    USE_CLASS_MATCH
)

print()


# =============================================================================
# FILE CHECK
# =============================================================================

for path in [
    CONTRACT_FILE,
    VESSEL_FILE,
    DATE_FILE,
    BUNKER_FILE,
]:

    if not path.exists():

        raise FileNotFoundError(
            f"Missing input:\n{path}"
        )


# =============================================================================
# 1. LOAD
# =============================================================================

print("=" * 80)
print("1/10 - LOADING INPUT DATA")
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
    "Bunker rows:",
    len(bunker)
)


# =============================================================================
# 2. NORMALIZE CONTRACTS
# =============================================================================

print()
print("=" * 80)
print("2/10 - NORMALIZING CONTRACT DATA")
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
        "contract_volume_mt",
        "scenario",
        "scenario_route_freight_rate",
        "kill_penalty_usd",
        "kill_alternative_value_usd",
    ],
    "Contract data",
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
    .str.lower()
    .str.strip()
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

contracts[
    "contract_volume_mt"
] = numeric(
    contracts[
        "contract_volume_mt"
    ]
)


for col in [
    "scenario_route_freight_rate",
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
# CONTRACT META
# =============================================================================

contract_meta = (
    contracts[
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
    .copy()
)


require(
    contract_meta,
    [
        "contract_id",
        "route_id",
        "origin",
        "destination",
        "vessel_class",
        "vessel_class_norm",
        "cargo_type",
        "contract_volume_mt",
    ],
    "Contract metadata",
)


# =============================================================================
# 3. SCENARIO ECONOMICS
# =============================================================================

print()
print("=" * 80)
print("3/10 - BUILDING SCENARIO ECONOMICS")
print("=" * 80)
print()


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
    .rename(
        columns={
            "bear":
                "bear_rate",

            "base":
                "base_rate",

            "bull":
                "bull_rate",
        }
    )
)


kill_table = (
    contracts[
        [
            "contract_id",
            "kill_penalty_usd",
            "kill_alternative_value_usd",
        ]
    ]
    .drop_duplicates(
        "contract_id"
    )
)


kill_table[
    "kill_value"
] = (
    kill_table[
        "kill_alternative_value_usd"
    ]
    -
    kill_table[
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
        kill_table[
            [
                "contract_id",
                "kill_value",
            ]
        ],
        on="contract_id",
        how="left",
    )
)


# =============================================================================
# 4. VESSEL / DATE POOL
# =============================================================================

print()
print("=" * 80)
print("4/10 - BUILDING VESSEL / DATE POOL")
print("=" * 80)
print()


require(
    vessels,
    [
        "imo",
        "vessel_name",
        "dwt",
    ],
    "Vessels",
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
)


require(
    dates,
    [
        "imo",
        "route_id",
        "departure_date",
        "estimated_eta",
    ],
    "Step 51A date data",
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


# IMPORTANT:
# Normalize both timestamp fields explicitly to UTC-aware.

dates[
    "departure_date"
] = normalize_timestamp_column(
    dates[
        "departure_date"
    ]
)

dates[
    "estimated_eta"
] = normalize_timestamp_column(
    dates[
        "estimated_eta"
    ]
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

        dates[
            col
        ] = numeric(
            dates[
                col
            ]
        )


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
    .merge(
        vessel_master,
        on="imo",
        how="inner",
    )
)


# Explicitly normalize again AFTER merge.

date_pool[
    "departure_dt"
] = normalize_timestamp_column(
    date_pool[
        "departure_date"
    ]
)

date_pool[
    "eta_dt"
] = normalize_timestamp_column(
    date_pool[
        "estimated_eta"
    ]
)


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
        "departure_dt",
        "eta_dt",
    ],
    "Vessel/date pool",
)


# Check timezone consistency.

if (
    date_pool[
        "departure_dt"
    ].notna().any()
):

    sample_departure = date_pool[
        "departure_dt"
    ].dropna().iloc[0]

    if sample_departure.tzinfo is None:

        raise RuntimeError(
            "departure_dt is still timezone-naive."
        )


if (
    date_pool[
        "eta_dt"
    ].notna().any()
):

    sample_eta = date_pool[
        "eta_dt"
    ].dropna().iloc[0]

    if sample_eta.tzinfo is None:

        raise RuntimeError(
            "eta_dt is still timezone-naive."
        )


print(
    "Vessel/date pool rows:",
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
# 5. BUILD CONTRACT/VESSEL/DATE CANDIDATES
# =============================================================================

print()
print("=" * 80)
print("5/10 - BUILDING CONTRACT/VESSEL/DATE CANDIDATES")
print("=" * 80)
print()


candidate_rows = []

capacity_removed = 0
class_removed = 0
no_route_contracts = 0


for _, contract in contract_meta.iterrows():

    cid = contract[
        "contract_id"
    ]

    route_id = contract[
        "route_id"
    ]

    cargo = float(
        contract[
            "contract_volume_mt"
        ]
    )

    required_class = contract[
        "vessel_class_norm"
    ]


    route_pool = date_pool[
        date_pool[
            "route_id"
        ]
        ==
        route_id
    ].copy()


    if route_pool.empty:

        no_route_contracts += 1

        continue


    for _, candidate in route_pool.iterrows():

        dwt = float(
            candidate[
                "dwt"
            ]
        )


        if dwt < cargo:

            capacity_removed += 1
            continue


        vessel_class = candidate[
            "vessel_class_norm"
        ]


        class_match = (
            required_class == ""
            or
            vessel_class == ""
            or
            required_class == vessel_class
        )


        if (
            USE_CLASS_MATCH
            and
            not class_match
        ):

            class_removed += 1
            continue


        cargo_type = str(
            contract[
                "cargo_type"
            ]
        )


        candidate_rows.append(
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

                "cargo_type":
                    cargo_type,

                "contract_volume_mt":
                    cargo,

                "contract_class":
                    required_class,

                "imo":
                    candidate[
                        "imo"
                    ],

                "vessel_name":
                    candidate[
                        "vessel_name"
                    ],

                "vessel_dwt":
                    dwt,

                "vessel_class":
                    vessel_class,

                "departure_date":
                    candidate[
                        "departure_date"
                    ],

                "estimated_eta":
                    candidate[
                        "estimated_eta"
                    ],

                # CRITICAL:
                # already UTC-aware.

                "departure_dt":
                    candidate[
                        "departure_dt"
                    ],

                "eta_dt":
                    candidate[
                        "eta_dt"
                    ],

                "reposition_distance_nm":
                    candidate.get(
                        "reposition_distance_nm",
                        np.nan,
                    ),

                "reposition_hours":
                    candidate.get(
                        "reposition_hours",
                        np.nan,
                    ),

                "total_voyage_hours":
                    candidate.get(
                        "total_voyage_hours",
                        np.nan,
                    ),

                "total_voyage_days":
                    candidate.get(
                        "total_voyage_days",
                        np.nan,
                    ),

                "bear_rate":
                    float(
                        contract[
                            "bear_rate"
                        ]
                    ),

                "base_rate":
                    float(
                        contract[
                            "base_rate"
                        ]
                    ),

                "bull_rate":
                    float(
                        contract[
                            "bull_rate"
                        ]
                    ),

                "kill_value":
                    float(
                        contract[
                            "kill_value"
                        ]
                    ),
            }
        )


candidates = pd.DataFrame(
    candidate_rows
)


print(
    "Candidate decisions:",
    len(candidates)
)

print(
    "Capacity removed:",
    capacity_removed
)

print(
    "Class removed:",
    class_removed
)

print(
    "Contracts without route/date candidate:",
    no_route_contracts
)


if candidates.empty:

    raise RuntimeError(
        "No feasible contract/vessel/date candidates."
    )


# =============================================================================
# TIMESTAMP NORMALIZATION AGAIN
# =============================================================================

candidates[
    "departure_dt"
] = normalize_timestamp_column(
    candidates[
        "departure_dt"
    ]
)

candidates[
    "eta_dt"
] = normalize_timestamp_column(
    candidates[
        "eta_dt"
    ]
)


# =============================================================================
# 6. ECONOMICS
# =============================================================================

print()
print("=" * 80)
print("6/10 - CALCULATING ECONOMICS")
print("=" * 80)
print()


bunker_price = float(
    bunker[
        "price_usd_per_metric_ton"
    ].iloc[0]
)


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
        ]
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

    route_econ[
        col
    ] = numeric(
        route_econ[
            col
        ]
    )


base_route = (
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
                "route_fuel_mt",

            "bunker_mt_per_day":
                "route_bunker_day",

            "daily_opex_usd":
                "route_opex_day",

            "opex_cost_usd":
                "route_opex_total",

            "other_voyage_cost_usd":
                "route_other_cost",

            "total_voyage_days":
                "route_days",
        }
    )
    .drop_duplicates(
        "route_id"
    )
)


candidates = candidates.merge(
    base_route[
        [
            "route_id",
            "route_fuel_mt",
            "route_bunker_day",
            "route_opex_day",
            "route_opex_total",
            "route_other_cost",
            "route_days",
        ]
    ],
    on="route_id",
    how="left",
)


# Date-aware duration has priority.

candidates[
    "voyage_days"
] = candidates[
    "total_voyage_days"
].combine_first(
    candidates[
        "route_days"
    ]
)


# Bunker.

candidates[
    "bunker_cost"
] = (
    candidates[
        "route_fuel_mt"
    ]
    *
    bunker_price
)


fallback_bunker = (
    candidates[
        "bunker_cost"
    ].isna()
    &
    candidates[
        "route_bunker_day"
    ].notna()
    &
    candidates[
        "voyage_days"
    ].notna()
)


candidates.loc[
    fallback_bunker,
    "bunker_cost",
] = (
    candidates.loc[
        fallback_bunker,
        "route_bunker_day",
    ]
    *
    candidates.loc[
        fallback_bunker,
        "voyage_days",
    ]
    *
    bunker_price
)


# OPEX.

candidates[
    "opex_cost_live"
] = (
    candidates[
        "route_opex_day"
    ]
    *
    candidates[
        "voyage_days"
    ]
)


fallback_opex = (
    candidates[
        "opex_cost_live"
    ].isna()
    &
    candidates[
        "route_opex_total"
    ].notna()
)


candidates.loc[
    fallback_opex,
    "opex_cost_live",
] = candidates.loc[
    fallback_opex,
    "route_opex_total",
]


# Total.

candidates[
    "total_cost"
] = (
    candidates[
        "bunker_cost"
    ]
    +
    candidates[
        "opex_cost_live"
    ]
    +
    candidates[
        "route_other_cost"
    ]
)


# Sail values.

candidates[
    "bear_sail"
] = (
    candidates[
        "bear_rate"
    ]
    *
    candidates[
        "contract_volume_mt"
    ]
    -
    candidates[
        "total_cost"
    ]
)


candidates[
    "base_sail"
] = (
    candidates[
        "base_rate"
    ]
    *
    candidates[
        "contract_volume_mt"
    ]
    -
    candidates[
        "total_cost"
    ]
)


candidates[
    "bull_sail"
] = (
    candidates[
        "bull_rate"
    ]
    *
    candidates[
        "contract_volume_mt"
    ]
    -
    candidates[
        "total_cost"
    ]
)


# Incremental Sail vs Kill.

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


candidates = candidates[
    candidates[
        "total_cost"
    ].notna()
    &
    candidates[
        "worst_incremental"
    ].notna()
].copy()


print(
    "Economically valid candidates:",
    len(candidates)
)


# =============================================================================
# 7. DE-DUPLICATE + CONFLICT GRAPH
# =============================================================================

print()
print("=" * 80)
print("7/10 - BUILDING TEMPORAL CONFLICT GRAPH")
print("=" * 80)
print()


candidates = (
    candidates
    .drop_duplicates(
        [
            "contract_id",
            "imo",
            "departure_dt",
        ]
    )
    .reset_index(
        drop=True
    )
)


# Final timezone assertion.

for col in [
    "departure_dt",
    "eta_dt",
]:

    if candidates[col].notna().any():

        sample = (
            candidates[col]
            .dropna()
            .iloc[0]
        )

        if sample.tzinfo is None:

            raise RuntimeError(
                f"{col} contains timezone-naive timestamps."
            )


conflict_rows = []


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


            a_start = candidates.loc[
                a,
                "departure_dt",
            ]

            a_end = candidates.loc[
                a,
                "eta_dt",
            ]

            b_start = candidates.loc[
                b,
                "departure_dt",
            ]

            b_end = candidates.loc[
                b,
                "eta_dt",
            ]


            if (
                pd.isna(a_start)
                or
                pd.isna(a_end)
                or
                pd.isna(b_start)
                or
                pd.isna(b_end)
            ):

                continue


            # Both timestamps are UTC-aware here.

            if (
                a_start < b_end
                and
                b_start < a_end
            ):

                conflict_rows.append(
                    {
                        "a":
                            a,

                        "b":
                            b,

                        "contract_a":
                            candidates.loc[
                                a,
                                "contract_id",
                            ],

                        "contract_b":
                            candidates.loc[
                                b,
                                "contract_id",
                            ],

                        "imo":
                            imo,

                        "vessel_name":
                            candidates.loc[
                                a,
                                "vessel_name",
                            ],

                        "a_departure":
                            a_start,

                        "a_eta":
                            a_end,

                        "b_departure":
                            b_start,

                        "b_eta":
                            b_end,

                        "a_worst_incremental":
                            candidates.loc[
                                a,
                                "worst_incremental",
                            ],

                        "b_worst_incremental":
                            candidates.loc[
                                b,
                                "worst_incremental",
                            ],
                    }
                )


conflicts = pd.DataFrame(
    conflict_rows
)


print(
    "Temporal conflict edges:",
    len(conflicts)
)


# =============================================================================
# 8. MILP
# =============================================================================

print()
print("=" * 80)
print("8/10 - BUILDING / SOLVING MILP")
print("=" * 80)
print()


import pulp


model = pulp.LpProblem(
    "Vessel_Sequencing_Sail_Kill",
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


# Objective.

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


# One Sail per contract.

for contract_id, indices in (
    candidates
    .groupby(
        "contract_id"
    )
    .groups
    .items()
):

    model += (
        pulp.lpSum(
            x[idx]
            for idx in indices
        )
        <= 1
    )


# Maximum Sail.

model += (
    pulp.lpSum(
        x[idx]
        for idx in candidates.index
    )
    <= MAX_SAIL
)


# Temporal overlap.

if not conflicts.empty:

    for _, row in conflicts.iterrows():

        a = int(
            row[
                "a"
            ]
        )

        b = int(
            row[
                "b"
            ]
        )

        model += (
            x[a]
            +
            x[b]
            <= 1
        )


# Downside protection.

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
        )
    )


print(
    "Variables:",
    len(x)
)

print(
    "Contract constraints:",
    candidates[
        "contract_id"
    ].nunique()
)

print(
    "Temporal constraints:",
    len(conflicts)
)


start = time.perf_counter()


solver = pulp.PULP_CBC_CMD(
    msg=False,
    timeLimit=TIME_LIMIT,
)


model.solve(
    solver
)


elapsed = (
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
        elapsed,
        3,
    )
)


if model.status != pulp.LpStatusOptimal:

    raise RuntimeError(
        "MILP was not solved to Optimal.\n"
        f"Status: {status}"
    )


# =============================================================================
# 9. EXTRACT
# =============================================================================

print()
print("=" * 80)
print("9/10 - EXTRACTING SOLUTION")
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


selected = candidates[
    candidates[
        "selected"
    ]
    ==
    1
].copy()


selected = (
    selected
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


# =============================================================================
# 10. VALIDATION + SAVE
# =============================================================================

print()
print("=" * 80)
print("10/10 - VALIDATING + SAVING")
print("=" * 80)
print()


contract_violations = int(
    (
        selected[
            "contract_id"
        ]
        .value_counts()
        >
        1
    )
    .sum()
)


capacity_violations = int(
    (
        selected[
            "vessel_dwt"
        ]
        <
        selected[
            "contract_volume_mt"
        ]
    )
    .sum()
)


overlap_violations = 0


for imo, group in (
    selected
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


            a_start = selected.loc[
                a,
                "departure_dt",
            ]

            a_end = selected.loc[
                a,
                "eta_dt",
            ]

            b_start = selected.loc[
                b,
                "departure_dt",
            ]

            b_end = selected.loc[
                b,
                "eta_dt",
            ]


            # Both are guaranteed UTC-aware.

            if (
                a_start < b_end
                and
                b_start < a_end
            ):

                overlap_violations += 1


robust_incremental = float(
    selected[
        "worst_incremental"
    ].sum()
)

base_incremental = float(
    selected[
        "base_incremental"
    ].sum()
)

expected_incremental = float(
    selected[
        "expected_incremental"
    ].sum()
)


# Save selected.

selected[
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
        "departure_dt",
        "eta_dt",
        "bear_rate",
        "base_rate",
        "bull_rate",
        "bear_sail",
        "base_sail",
        "bull_sail",
        "bear_incremental",
        "base_incremental",
        "bull_incremental",
        "worst_incremental",
        "expected_incremental",
    ]
].to_csv(
    SELECTED_FILE,
    index=False,
)


conflicts.to_csv(
    CONFLICT_FILE,
    index=False,
)


# =============================================================================
# SUMMARY
# =============================================================================

summary = pd.DataFrame(
    [
        {
            "generated_utc":
                now_utc(),

            "status":
                status,

            "input_candidates":
                len(candidates),

            "selected_contracts":
                len(selected),

            "selected_vessels":
                selected[
                    "imo"
                ].nunique(),

            "selected_routes":
                selected[
                    "route_id"
                ].nunique(),

            "selected_departure_dates":
                selected[
                    "departure_date"
                ].nunique(),

            "conflict_edges":
                len(conflicts),

            "contract_violations":
                contract_violations,

            "capacity_violations":
                capacity_violations,

            "temporal_overlap_violations":
                overlap_violations,

            "robust_incremental":
                robust_incremental,

            "base_incremental":
                base_incremental,

            "expected_incremental":
                expected_incremental,

            "max_sail":
                MAX_SAIL,

            "risk_ratio":
                RISK_RATIO,

            "bunker_price_usd_per_mt":
                bunker_price,

            "solve_seconds":
                elapsed,

            "myshiptracking_api_calls":
                0,

            "myshiptracking_credits":
                0,

            "oilpriceapi_calls":
                0,

            "status_detail":
                "VESSEL_SEQUENCING_COMPLETE",
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

quality = pd.DataFrame(
    [
        {
            "metric":
                "contract_rows",
            "value":
                len(contracts),
        },

        {
            "metric":
                "unique_contracts",
            "value":
                contract_meta[
                    "contract_id"
                ].nunique(),
        },

        {
            "metric":
                "date_pool_rows",
            "value":
                len(date_pool),
        },

        {
            "metric":
                "date_pool_unique_vessels",
            "value":
                date_pool[
                    "imo"
                ].nunique(),
        },

        {
            "metric":
                "candidate_decisions",
            "value":
                len(candidates),
        },

        {
            "metric":
                "capacity_removed",
            "value":
                capacity_removed,
        },

        {
            "metric":
                "class_removed",
            "value":
                class_removed,
        },

        {
            "metric":
                "contracts_without_route_candidate",
            "value":
                no_route_contracts,
        },

        {
            "metric":
                "conflict_edges",
            "value":
                len(conflicts),
        },

        {
            "metric":
                "selected_contracts",
            "value":
                len(selected),
        },

        {
            "metric":
                "selected_vessels",
            "value":
                selected[
                    "imo"
                ].nunique(),
        },

        {
            "metric":
                "selected_routes",
            "value":
                selected[
                    "route_id"
                ].nunique(),
        },

        {
            "metric":
                "contract_violations",
            "value":
                contract_violations,
        },

        {
            "metric":
                "capacity_violations",
            "value":
                capacity_violations,
        },

        {
            "metric":
                "temporal_overlap_violations",
            "value":
                overlap_violations,
        },

        {
            "metric":
                "positive_worst_case_candidates",
            "value":
                int(
                    (
                        candidates[
                            "worst_incremental"
                        ]
                        > 0
                    ).sum()
                ),
        },

        {
            "metric":
                "timezone_normalization",
            "value":
                "UTC_AWARE",
        },

        {
            "metric":
                "api_calls_myshiptracking",
            "value":
                0,
        },

        {
            "metric":
                "myshiptracking_credits_consumed",
            "value":
                0,
        },

        {
            "metric":
                "api_calls_oilpriceapi",
            "value":
                0,
        },
    ]
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

    "purpose":
        (
            "Test correct vessel sequencing with multiple sequential "
            "non-overlapping voyages."
        ),

    "configuration": {
        "maximum_sail":
            MAX_SAIL,

        "risk_ratio":
            RISK_RATIO,

        "class_matching":
            USE_CLASS_MATCH,

        "timezone":
            "UTC",
    },

    "dimensions": {
        "contracts":
            len(contract_meta),

        "date_pool_rows":
            len(date_pool),

        "candidate_decisions":
            len(candidates),

        "selected_contracts":
            len(selected),

        "selected_vessels":
            int(
                selected[
                    "imo"
                ].nunique()
            ),

        "selected_routes":
            int(
                selected[
                    "route_id"
                ].nunique()
            ),

        "selected_departure_dates":
            int(
                selected[
                    "departure_date"
                ].nunique()
            ),

        "conflict_edges":
            len(conflicts),
    },

    "result": {
        "robust_incremental":
            robust_incremental,

        "base_incremental":
            base_incremental,

        "expected_incremental":
            expected_incremental,
    },

    "validation": {
        "contract_violations":
            contract_violations,

        "capacity_violations":
            capacity_violations,

        "temporal_overlap_violations":
            overlap_violations,
    },

    "api": {
        "myshiptracking_calls":
            0,

        "myshiptracking_credits":
            0,

        "oilpriceapi_calls":
            0,
    },

    "timezone_policy":
        (
            "All departure and ETA timestamps are converted to "
            "timezone-aware UTC timestamps before overlap comparisons."
        ),
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
print("STEP 51M COMPLETE")
print("=" * 80)
print()

print(
    "CBC status:",
    status
)

print(
    "Candidate decisions:",
    len(candidates)
)

print(
    "Selected contracts:",
    len(selected)
)

print(
    "Selected vessels:",
    selected[
        "imo"
    ].nunique()
)

print(
    "Selected routes:",
    selected[
        "route_id"
    ].nunique()
)

print(
    "Selected dates:",
    selected[
        "departure_date"
    ].nunique()
)

print(
    "Conflict edges:",
    len(conflicts)
)

print()
print(
    "Robust incremental:",
    robust_incremental
)

print(
    "Base incremental:",
    base_incremental
)

print(
    "Expected incremental:",
    expected_incremental
)

print()
print(
    "Contract violations:",
    contract_violations
)

print(
    "Capacity violations:",
    capacity_violations
)

print(
    "Temporal overlap violations:",
    overlap_violations
)

print()
print(
    "Timezone:",
    "UTC-aware"
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
print("SAVED:")
print(
    SELECTED_FILE
)

print(
    CONFLICT_FILE
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
