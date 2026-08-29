#!/usr/bin/env python3

"""
STEP 50B - LIVE BUNKER VOYAGE ECONOMICS

LOCAL COMPUTATION ONLY
----------------------
MyShipTracking API calls: 0
MyShipTracking credits: 0

Inputs
------
1. data/processed/step49j_strict_ais_route_candidates.csv
2. data/processed/route_distance_master.csv
3. data/processed/step50a_bunker_current.csv
4. data/processed/step19b_route_scenario_economics.csv

Purpose
-------
Build an economics layer for the strict AIS vessel × route candidates.

Architecture
------------

AIS candidate
    +
canonical route master
    +
current OilPriceAPI VLSFO
    ↓
live voyage economics
    ↓
existing Bear / Base / Bull freight scenarios
    ↓
later MILP

This step does NOT:
    - call MyShipTracking
    - consume MyShipTracking credits
    - overwrite existing economics files
    - invent freight scenarios
    - invent bunker prices
    - run the MILP
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


# =============================================================================
# PATHS
# =============================================================================

ROOT = Path(
    "/home/aryashekhar/freight-optimization"
)

PROCESSED = (
    ROOT
    / "data"
    / "processed"
)

OUTPUTS = (
    ROOT
    / "outputs"
)

CANDIDATE_FILE = (
    PROCESSED
    / "step49j_strict_ais_route_candidates.csv"
)

ROUTE_MASTER_FILE = (
    PROCESSED
    / "route_distance_master.csv"
)

BUNKER_FILE = (
    PROCESSED
    / "step50a_bunker_current.csv"
)

SCENARIO_FILE = (
    PROCESSED
    / "step19b_route_scenario_economics.csv"
)

LIVE_FILE = (
    PROCESSED
    / "step50b_live_bunker_economics.csv"
)

SCENARIO_OUTPUT_FILE = (
    PROCESSED
    / "step50b_live_bunker_scenarios.csv"
)

SUMMARY_FILE = (
    OUTPUTS
    / "step50b_live_bunker_summary.csv"
)

QUALITY_FILE = (
    OUTPUTS
    / "step50b_live_bunker_quality.csv"
)

REPORT_FILE = (
    OUTPUTS
    / "step50b_live_bunker_report.json"
)


# =============================================================================
# HELPERS
# =============================================================================

def now_utc() -> str:
    return (
        pd.Timestamp
        .now(
            tz="UTC"
        )
        .isoformat()
    )


def normalize_route_id(value):
    """
    Normalize route IDs such as:

        0
        0.0
        "0"

    into:

        "0"
    """

    if value is None:
        return None

    try:

        if pd.isna(value):
            return None

    except Exception:
        pass

    try:

        return str(
            int(
                float(value)
            )
        )

    except Exception:

        return str(value).strip()


def numeric(
    series
):
    return pd.to_numeric(
        series,
        errors="coerce",
    )


def get_optional(
    df,
    column,
):

    if column in df.columns:
        return numeric(
            df[column]
        )

    return pd.Series(
        np.nan,
        index=df.index,
        dtype="float64",
    )


# =============================================================================
# START
# =============================================================================

print()
print("=" * 80)
print("STEP 50B - LIVE BUNKER VOYAGE ECONOMICS")
print("=" * 80)
print()

print(
    "MODE: LOCAL COMPUTATION"
)

print(
    "MyShipTracking API calls: 0"
)

print(
    "MyShipTracking credits consumed: 0"
)

print()


# =============================================================================
# CHECK INPUTS
# =============================================================================

required_files = [
    CANDIDATE_FILE,
    ROUTE_MASTER_FILE,
    BUNKER_FILE,
]

for path in required_files:

    if not path.exists():

        raise FileNotFoundError(
            f"Required file missing:\n{path}"
        )


# =============================================================================
# LOAD
# =============================================================================

print("=" * 80)
print("1/8 - LOADING INPUTS")
print("=" * 80)
print()

candidates = pd.read_csv(
    CANDIDATE_FILE
)

routes = pd.read_csv(
    ROUTE_MASTER_FILE
)

bunker = pd.read_csv(
    BUNKER_FILE
)

print(
    "Candidate rows:",
    len(candidates)
)

print(
    "Route master rows:",
    len(routes)
)

print(
    "Bunker rows:",
    len(bunker)
)


# =============================================================================
# STRICT CANDIDATE FILTER
# =============================================================================

if "match_type" in candidates.columns:

    candidates = candidates[
        candidates[
            "match_type"
        ]
        .isin(
            [
                "STRONG",
                "CLASS_MATCH_DWT_UNKNOWN",
            ]
        )
    ].copy()

print(
    "Strict candidate rows:",
    len(candidates)
)

if candidates.empty:

    raise RuntimeError(
        "No strict Step 49J candidates."
    )


# =============================================================================
# CANDIDATE SCHEMA
# =============================================================================

if "imo" not in candidates.columns:

    raise RuntimeError(
        "Step 49J file has no IMO column."
    )

if "vessel_name" not in candidates.columns:

    raise RuntimeError(
        "Step 49J file has no vessel_name column."
    )


# Step 49J actually stores the route identifier in `route`.
# Normalize it into a canonical `route_id`.

if "route_id" in candidates.columns:

    candidates[
        "route_id"
    ] = (
        candidates[
            "route_id"
        ]
        .apply(
            normalize_route_id
        )
    )

elif "route" in candidates.columns:

    candidates[
        "route_id"
    ] = (
        candidates[
            "route"
        ]
        .apply(
            normalize_route_id
        )
    )

else:

    raise RuntimeError(
        "Neither 'route_id' nor 'route' exists in Step 49J."
    )


# =============================================================================
# ROUTE MASTER SCHEMA
# =============================================================================

required_route_columns = [
    "route_id",
    "origin",
    "destination",
    "distance_nm",
    "speed_knots",
    "bunker_mt_per_day",
    "port_days",
    "daily_opex_usd",
    "other_voyage_cost_usd",
    "cargo_quantity_mt",
    "latest_observed_freight_rate",
    "freight_rate_unit",
]

missing_route = [
    c
    for c in required_route_columns
    if c not in routes.columns
]

if missing_route:

    raise RuntimeError(
        "Route master missing columns:\n"
        +
        "\n".join(
            missing_route
        )
    )


# Normalize route IDs.

routes[
    "route_id"
] = (
    routes[
        "route_id"
    ]
    .apply(
        normalize_route_id
    )
)


# =============================================================================
# ROUTE MASTER DEDUP
# =============================================================================

if "assessment_date" in routes.columns:

    routes[
        "_assessment_date"
    ] = pd.to_datetime(
        routes[
            "assessment_date"
        ],
        errors="coerce",
    )

    routes = (
        routes
        .sort_values(
            "_assessment_date",
            ascending=False,
            na_position="last",
        )
        .drop_duplicates(
            subset=[
                "route_id"
            ],
            keep="first",
        )
        .drop(
            columns=[
                "_assessment_date"
            ]
        )
    )

else:

    routes = (
        routes
        .drop_duplicates(
            subset=[
                "route_id"
            ],
            keep="first",
        )
    )


print(
    "Unique route-master IDs:",
    routes[
        "route_id"
    ]
    .nunique()
)


# =============================================================================
# BUNKER
# =============================================================================

print()
print("=" * 80)
print("2/8 - LOADING CURRENT BUNKER PRICE")
print("=" * 80)
print()

if bunker.empty:

    raise RuntimeError(
        "Bunker file is empty."
    )

if "updated_at" in bunker.columns:

    bunker[
        "_updated"
    ] = pd.to_datetime(
        bunker[
            "updated_at"
        ],
        utc=True,
        errors="coerce",
    )

    bunker = (
        bunker
        .sort_values(
            "_updated",
            ascending=False,
            na_position="last",
        )
        .iloc[0]
    )

else:

    bunker = bunker.iloc[0]


live_bunker_price = numeric(
    pd.Series(
        [
            bunker[
                "price_usd_per_metric_ton"
            ]
        ]
    )
).iloc[0]

fuel_grade = bunker.get(
    "fuel_grade",
    "VLSFO",
)

market_reference = bunker.get(
    "market_reference",
    "UNKNOWN",
)

bunker_updated_at = bunker.get(
    "updated_at",
    None,
)

project_usable = bool(
    bunker.get(
        "project_usable",
        False,
    )
)

print(
    "Fuel grade:",
    fuel_grade
)

print(
    "Market reference:",
    market_reference
)

print(
    "Price:",
    live_bunker_price,
    "USD/MT"
)

print(
    "Updated:",
    bunker_updated_at
)

print(
    "Project usable:",
    project_usable
)


if not project_usable:

    raise RuntimeError(
        "OilPriceAPI bunker price is not marked project-usable."
    )

if pd.isna(
    live_bunker_price
) or live_bunker_price <= 0:

    raise RuntimeError(
        "Invalid bunker price."
    )


# =============================================================================
# MERGE ROUTE MASTER
# =============================================================================

print()
print("=" * 80)
print("3/8 - MERGING CANONICAL ROUTE ECONOMICS")
print("=" * 80)
print()

route_fields = [
    "route_id",
    "origin",
    "destination",
    "vessel_class",
    "cargo_type",
    "latest_observed_freight_rate",
    "freight_rate_unit",
    "distance_nm",
    "distance_source",
    "typical_dwt_min",
    "typical_dwt_max",
    "average_dwt_assumption",
    "cargo_quantity_mt",
    "speed_knots",
    "bunker_mt_per_day",
    "port_days",
    "daily_opex_usd",
    "other_voyage_cost_usd",
    "cargo_utilization",
    "production_ready",
    "physics_status",
]

route_fields = [
    c
    for c in route_fields
    if c in routes.columns
]

route_lookup = routes[
    route_fields
].copy()

merged = candidates.merge(
    route_lookup,
    on="route_id",
    how="left",
    suffixes=(
        "_candidate",
        "_route",
    ),
    indicator=True,
)

route_matches = int(
    (
        merged[
            "_merge"
        ]
        ==
        "both"
    ).sum()
)

route_missing = int(
    (
        merged[
            "_merge"
        ]
        !=
        "both"
    ).sum()
)

print(
    "Candidate rows matched to route master:",
    route_matches
)

print(
    "Candidate rows missing route master:",
    route_missing
)

if route_missing:

    missing_ids = (
        merged.loc[
            merged[
                "_merge"
            ]
            != "both",
            "route_id",
        ]
        .dropna()
        .astype(str)
        .drop_duplicates()
        .tolist()
    )

    print()
    print(
        "Missing route IDs:"
    )

    for rid in missing_ids:
        print(
            " ",
            rid
        )

    raise RuntimeError(
        "Route master join incomplete."
    )

merged = merged.drop(
    columns=[
        "_merge"
    ]
)


# =============================================================================
# EXTRACT ROUTE VALUES
# =============================================================================

print()
print("=" * 80)
print("4/8 - NORMALIZING ECONOMIC INPUTS")
print("=" * 80)
print()


def route_col(
    name
):

    route_name = (
        name
        +
        "_route"
    )

    if route_name in merged.columns:

        return merged[
            route_name
        ]

    if name in merged.columns:

        return merged[
            name
        ]

    return pd.Series(
        np.nan,
        index=merged.index,
    )


merged[
    "origin"
] = route_col(
    "origin"
)

merged[
    "destination"
] = route_col(
    "destination"
)

merged[
    "cargo_type"
] = route_col(
    "cargo_type"
)

merged[
    "distance_nm"
] = numeric(
    route_col(
        "distance_nm"
    )
)

merged[
    "speed_knots"
] = numeric(
    route_col(
        "speed_knots"
    )
)

merged[
    "bunker_mt_per_day"
] = numeric(
    route_col(
        "bunker_mt_per_day"
    )
)

merged[
    "port_days"
] = numeric(
    route_col(
        "port_days"
    )
)

merged[
    "daily_opex_usd"
] = numeric(
    route_col(
        "daily_opex_usd"
    )
)

merged[
    "other_voyage_cost_usd"
] = numeric(
    route_col(
        "other_voyage_cost_usd"
    )
)

merged[
    "cargo_quantity_mt"
] = numeric(
    route_col(
        "cargo_quantity_mt"
    )
)

merged[
    "freight_rate_usd_per_mt"
] = numeric(
    route_col(
        "latest_observed_freight_rate"
    )
)

merged[
    "freight_rate_unit"
] = route_col(
    "freight_rate_unit"
)

merged[
    "route_vessel_class"
] = route_col(
    "vessel_class"
)


# =============================================================================
# VOYAGE ECONOMICS
# =============================================================================

print(
    "Calculating voyage economics..."
)

merged[
    "sea_days"
] = (
    merged[
        "distance_nm"
    ]
    /
    merged[
        "speed_knots"
    ]
    /
    24.0
)

merged.loc[
    (
        merged[
            "distance_nm"
        ].isna()
        |
        merged[
            "speed_knots"
        ].isna()
        |
        (
            merged[
                "speed_knots"
            ]
            <= 0
        )
    ),
    "sea_days",
] = np.nan


merged[
    "total_voyage_days"
] = (
    merged[
        "sea_days"
    ]
    +
    merged[
        "port_days"
    ]
)


# =============================================================================
# FUEL
# =============================================================================

merged[
    "fuel_consumption_mt"
] = (
    merged[
        "bunker_mt_per_day"
    ]
    *
    merged[
        "total_voyage_days"
    ]
)


merged.loc[
    (
        merged[
            "bunker_mt_per_day"
        ].isna()
        |
        merged[
            "total_voyage_days"
        ].isna()
    ),
    "fuel_consumption_mt",
] = np.nan


merged[
    "live_bunker_price_usd_per_mt"
] = live_bunker_price


merged[
    "bunker_fuel_grade"
] = fuel_grade


merged[
    "bunker_market_reference"
] = market_reference


merged[
    "bunker_updated_at"
] = bunker_updated_at


merged[
    "live_bunker_cost_usd"
] = (
    merged[
        "fuel_consumption_mt"
    ]
    *
    merged[
        "live_bunker_price_usd_per_mt"
    ]
)


# =============================================================================
# OPEX
# =============================================================================

merged[
    "opex_cost_usd"
] = (
    merged[
        "daily_opex_usd"
    ]
    *
    merged[
        "total_voyage_days"
    ]
)


# =============================================================================
# TOTAL COST
# =============================================================================

merged[
    "live_total_voyage_cost_usd"
] = (
    merged[
        "live_bunker_cost_usd"
    ]
    +
    merged[
        "opex_cost_usd"
    ]
    +
    merged[
        "other_voyage_cost_usd"
    ]
)


# =============================================================================
# FREIGHT REVENUE
# =============================================================================

merged[
    "freight_revenue_usd"
] = (
    merged[
        "freight_rate_usd_per_mt"
    ]
    *
    merged[
        "cargo_quantity_mt"
    ]
)


# =============================================================================
# PROFIT
# =============================================================================

merged[
    "estimated_profit_usd"
] = (
    merged[
        "freight_revenue_usd"
    ]
    -
    merged[
        "live_total_voyage_cost_usd"
    ]
)


# =============================================================================
# READINESS
# =============================================================================

merged[
    "has_distance"
] = (
    merged[
        "distance_nm"
    ]
    .notna()
)

merged[
    "has_speed"
] = (
    merged[
        "speed_knots"
    ]
    .notna()
    &
    (
        merged[
            "speed_knots"
        ]
        >
        0
    )
)

merged[
    "has_bunker_consumption"
] = (
    merged[
        "bunker_mt_per_day"
    ]
    .notna()
    &
    (
        merged[
            "bunker_mt_per_day"
        ]
        >
        0
    )
)

merged[
    "has_cargo"
] = (
    merged[
        "cargo_quantity_mt"
    ]
    .notna()
    &
    (
        merged[
            "cargo_quantity_mt"
        ]
        >
        0
    )
)

merged[
    "has_freight_rate"
] = (
    merged[
        "freight_rate_usd_per_mt"
    ]
    .notna()
    &
    (
        merged[
            "freight_rate_usd_per_mt"
        ]
        >
        0
    )
)

merged[
    "economics_ready"
] = (
    merged[
        "has_distance"
    ]
    &
    merged[
        "has_speed"
    ]
    &
    merged[
        "has_bunker_consumption"
    ]
    &
    merged[
        "has_cargo"
    ]
    &
    merged[
        "has_freight_rate"
    ]
    &
    merged[
        "estimated_profit_usd"
    ].notna()
)


# =============================================================================
# SOURCE
# =============================================================================

merged[
    "economics_source"
] = (
    "STEP49J_AIS"
    "+"
    "ROUTE_MASTER"
    "+"
    "OILPRICEAPI_VLSFO"
)


# =============================================================================
# SAVE LIVE ECONOMICS
# =============================================================================

print()
print("=" * 80)
print("5/8 - SAVING LIVE ECONOMICS")
print("=" * 80)
print()

# Select clean output columns.

output_columns = [
    "candidate_id",
    "imo",
    "vessel_name",
    "mmsi",
    "vessel_dwt",
    "vessel_dwt_class",

    "ais_lat",
    "ais_lon",
    "ais_speed_knots",
    "ais_freshness_minutes",

    "route_id",
    "origin",
    "destination",
    "cargo_type",
    "route_vessel_class",

    "cargo_quantity_mt",
    "freight_rate_usd_per_mt",
    "freight_rate_unit",

    "distance_nm",
    "speed_knots",

    "sea_days",
    "port_days",
    "total_voyage_days",

    "bunker_mt_per_day",
    "fuel_consumption_mt",

    "live_bunker_price_usd_per_mt",
    "bunker_fuel_grade",
    "bunker_market_reference",
    "bunker_updated_at",

    "live_bunker_cost_usd",

    "daily_opex_usd",
    "opex_cost_usd",
    "other_voyage_cost_usd",

    "live_total_voyage_cost_usd",
    "freight_revenue_usd",
    "estimated_profit_usd",

    "has_distance",
    "has_speed",
    "has_bunker_consumption",
    "has_cargo",
    "has_freight_rate",
    "economics_ready",

    "economics_source",
]

output_columns = [
    c
    for c in output_columns
    if c in merged.columns
]

live_df = merged[
    output_columns
].copy()


live_df.to_csv(
    LIVE_FILE,
    index=False,
)


# =============================================================================
# EXISTING BEAR / BASE / BULL SCENARIOS
# =============================================================================

print()
print("=" * 80)
print("6/8 - ATTACHING EXISTING BEAR / BASE / BULL SCENARIOS")
print("=" * 80)
print()

scenario_rows = []

if SCENARIO_FILE.exists():

    scenarios = pd.read_csv(
        SCENARIO_FILE
    )

    scenarios[
        "route_id"
    ] = (
        scenarios[
            "route_id"
        ]
        .apply(
            normalize_route_id
        )
    )

    if "scenario" not in scenarios.columns:

        raise RuntimeError(
            "Scenario file has no scenario column."
        )

    scenarios[
        "scenario"
    ] = (
        scenarios[
            "scenario"
        ]
        .astype(str)
        .str.lower()
    )

    scenarios[
        "scenario_route_freight_rate"
    ] = numeric(
        scenarios[
            "scenario_route_freight_rate"
        ]
    )

    scenarios[
        "cargo_quantity_mt"
    ] = numeric(
        scenarios[
            "cargo_quantity_mt"
        ]
    )

    for _, econ in scenarios.iterrows():

        route_id = econ[
            "route_id"
        ]

        scenario_name = econ[
            "scenario"
        ]

        scenario_rate = econ[
            "scenario_route_freight_rate"
        ]

        scenario_cargo = econ[
            "cargo_quantity_mt"
        ]

        if (
            pd.isna(
                scenario_rate
            )
            or
            pd.isna(
                scenario_cargo
            )
        ):
            continue

        route_candidates = live_df[
            live_df[
                "route_id"
            ]
            .apply(
                normalize_route_id
            )
            ==
            route_id
        ]

        for _, candidate in route_candidates.iterrows():

            total_cost = numeric(
                pd.Series(
                    [
                        candidate[
                            "live_total_voyage_cost_usd"
                        ]
                    ]
                )
            ).iloc[0]

            revenue = (
                scenario_rate
                *
                scenario_cargo
            )

            if pd.isna(
                total_cost
            ):

                profit = np.nan

            else:

                profit = (
                    revenue
                    -
                    total_cost
                )

            scenario_rows.append(
                {
                    "candidate_id":
                        candidate.get(
                            "candidate_id"
                        ),

                    "imo":
                        candidate[
                            "imo"
                        ],

                    "vessel_name":
                        candidate[
                            "vessel_name"
                        ],

                    "route_id":
                        candidate[
                            "route_id"
                        ],

                    "origin":
                        candidate[
                            "origin"
                        ],

                    "destination":
                        candidate[
                            "destination"
                        ],

                    "scenario":
                        scenario_name,

                    "freight_rate_usd_per_mt":
                        scenario_rate,

                    "cargo_quantity_mt":
                        scenario_cargo,

                    "freight_revenue_usd":
                        revenue,

                    "bunker_price_usd_per_mt":
                        live_bunker_price,

                    "bunker_fuel_grade":
                        fuel_grade,

                    "bunker_market_reference":
                        market_reference,

                    "bunker_cost_usd":
                        candidate[
                            "live_bunker_cost_usd"
                        ],

                    "opex_cost_usd":
                        candidate[
                            "opex_cost_usd"
                        ],

                    "other_voyage_cost_usd":
                        candidate[
                            "other_voyage_cost_usd"
                        ],

                    "total_voyage_cost_usd":
                        total_cost,

                    "estimated_profit_usd":
                        profit,

                    "economics_source":
                        "STEP19B_SCENARIO"
                        "+"
                        "LIVE_OILPRICEAPI_BUNKER",
                }
            )

else:

    print(
        "WARNING: step19b_route_scenario_economics.csv not found."
    )

scenario_df = pd.DataFrame(
    scenario_rows
)

scenario_df.to_csv(
    SCENARIO_OUTPUT_FILE,
    index=False,
)


# =============================================================================
# QUALITY
# =============================================================================

print()
print("=" * 80)
print("7/8 - QUALITY REPORT")
print("=" * 80)
print()

economics_ready_rows = int(
    live_df[
        "economics_ready"
    ]
    .fillna(False)
    .sum()
)

profit_rows = int(
    live_df[
        "estimated_profit_usd"
    ]
    .notna()
    .sum()
)

bunker_rows = int(
    live_df[
        "live_bunker_cost_usd"
    ]
    .notna()
    .sum()
)

revenue_rows = int(
    live_df[
        "freight_revenue_usd"
    ]
    .notna()
    .sum()
)

quality = pd.DataFrame(
    [
        {
            "metric":
                "strict_candidate_rows",
            "value":
                len(candidates),
        },

        {
            "metric":
                "route_master_rows",
            "value":
                len(routes),
        },

        {
            "metric":
                "route_matches",
            "value":
                route_matches,
        },

        {
            "metric":
                "route_missing",
            "value":
                route_missing,
        },

        {
            "metric":
                "live_economics_rows",
            "value":
                len(live_df),
        },

        {
            "metric":
                "bunker_cost_rows",
            "value":
                bunker_rows,
        },

        {
            "metric":
                "freight_revenue_rows",
            "value":
                revenue_rows,
        },

        {
            "metric":
                "profit_rows",
            "value":
                profit_rows,
        },

        {
            "metric":
                "economics_ready_rows",
            "value":
                economics_ready_rows,
        },

        {
            "metric":
                "scenario_rows",
            "value":
                len(scenario_df),
        },

        {
            "metric":
                "live_bunker_price_usd_per_mt",
            "value":
                live_bunker_price,
        },

        {
            "metric":
                "bunker_market_reference",
            "value":
                market_reference,
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
                "oilpriceapi_calls_in_step50b",
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
# SUMMARY
# =============================================================================

summary = pd.DataFrame(
    [
        {
            "generated_utc":
                now_utc(),

            "strict_candidate_rows":
                len(candidates),

            "route_master_rows":
                len(routes),

            "route_matches":
                route_matches,

            "live_economics_rows":
                len(live_df),

            "economics_ready_rows":
                economics_ready_rows,

            "live_bunker_price_usd_per_mt":
                live_bunker_price,

            "bunker_grade":
                fuel_grade,

            "bunker_market_reference":
                market_reference,

            "bunker_updated_at":
                bunker_updated_at,

            "bunker_project_usable":
                project_usable,

            "scenario_rows":
                len(scenario_df),

            "myshiptracking_api_calls":
                0,

            "myshiptracking_credits_consumed":
                0,

            "oilpriceapi_calls_in_step50b":
                0,

            "status":
                "LIVE_BUNKER_ECONOMICS_READY",
        }
    ]
)

summary.to_csv(
    SUMMARY_FILE,
    index=False,
)


# =============================================================================
# REPORT
# =============================================================================

report = {
    "generated_utc":
        now_utc(),

    "mode":
        "LOCAL_COMPUTATION",

    "inputs": {
        "step49j_candidates":
            str(
                CANDIDATE_FILE
            ),

        "route_master":
            str(
                ROUTE_MASTER_FILE
            ),

        "bunker_current":
            str(
                BUNKER_FILE
            ),

        "existing_scenarios":
            str(
                SCENARIO_FILE
            ),
    },

    "outputs": {
        "live_economics":
            str(
                LIVE_FILE
            ),

        "scenario_economics":
            str(
                SCENARIO_OUTPUT_FILE
            ),

        "summary":
            str(
                SUMMARY_FILE
            ),

        "quality":
            str(
                QUALITY_FILE
            ),
    },

    "bunker": {
        "price_usd_per_mt":
            live_bunker_price,

        "fuel_grade":
            fuel_grade,

        "market_reference":
            market_reference,

        "updated_at":
            bunker_updated_at,

        "project_usable":
            project_usable,
    },

    "statistics": {
        "strict_candidates":
            len(candidates),

        "route_matches":
            route_matches,

        "live_economics_rows":
            len(live_df),

        "economics_ready_rows":
            economics_ready_rows,

        "profit_rows":
            profit_rows,

        "scenario_rows":
            len(scenario_df),
    },

    "logic": [
        "Step 49J supplies strict AIS vessel-route candidates.",
        "route_distance_master.csv supplies canonical route economics.",
        "OilPriceAPI supplies the current Singapore VLSFO benchmark.",
        "Bunker cost = fuel consumption × live VLSFO price.",
        "Freight revenue = freight rate × cargo quantity.",
        "Profit = freight revenue - total voyage cost.",
        "Existing Step 19B Bear/Base/Bull freight scenarios are reused.",
        "No new freight scenarios are invented.",
        "Existing economics files are not overwritten.",
        "No MyShipTracking API calls were made.",
        "No MyShipTracking credits were consumed.",
        "No OilPriceAPI request was made in Step 50B.",
        "MILP optimization is not performed here.",
    ],
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
# FINAL DISPLAY
# =============================================================================

print()
print("=" * 80)
print("STEP 50B SUMMARY")
print("=" * 80)
print()

print(
    "Strict candidates:",
    len(candidates)
)

print(
    "Route matches:",
    route_matches
)

print(
    "Live economics rows:",
    len(live_df)
)

print(
    "Economics-ready rows:",
    economics_ready_rows
)

print(
    "Live VLSFO:",
    live_bunker_price,
    "USD/MT"
)

print(
    "Market reference:",
    market_reference
)

print(
    "Scenario rows:",
    len(scenario_df)
)

print()
print(
    "MyShipTracking API calls:",
    0
)

print(
    "MyShipTracking credits consumed:",
    0
)

print(
    "OilPriceAPI calls in Step 50B:",
    0
)

print()
print("=" * 80)
print("SAVED")
print("=" * 80)
print()

print(
    LIVE_FILE
)

print(
    SCENARIO_OUTPUT_FILE
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

print()
print("=" * 80)
print("STEP 50B COMPLETE")
print("=" * 80)
print()
print(
    "Next: inspect the economics before connecting to MILP."
)
