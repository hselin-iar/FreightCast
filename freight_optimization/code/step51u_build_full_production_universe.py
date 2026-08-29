#!/usr/bin/env python3

"""
STEP 51U - BUILD FULL PRODUCTION CANDIDATE UNIVERSE

LOCAL ONLY
----------

No MyShipTracking API calls.
No MyShipTracking credits.
No OilPriceAPI calls.

PURPOSE
-------

Correct the Step 51S/51T architecture.

IMPORTANT:
Step 51S incorrectly gated only the 11 assignments selected by Step 51P.

This step DOES NOT start from Step 51P selected rows.

It starts from the COMPLETE Step 51A date-aware candidate universe and
rebuilds every production-eligible contract × vessel × departure-date
decision.

PRODUCTION POLICY
-----------------

Automatic production candidate:

    DWT >= contract cargo
    AND
    exact vessel-class match

Cross-class candidates are retained separately as REVIEW ONLY.

This step does not reject alternatives merely because they were not
selected by Step 51P.

INPUTS
------

data/processed/step51a_optimizer_candidates.csv
data/processed/step49g_vessel_candidates.csv
data/processed/step23_contract_sail_kill.csv
data/processed/step50a_bunker_current.csv
outputs/step51r_route_size_audit.csv

OUTPUTS
-------

data/processed/step51u_full_production_universe.csv
data/processed/step51u_review_universe.csv
outputs/step51u_summary.csv
outputs/step51u_quality.csv
outputs/step51u_report.json

NEXT
----

Step 51V should build the final MILP directly from the complete
Step 51U production universe.
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

DATE_FILE = (
    PROCESSED /
    "step51a_optimizer_candidates.csv"
)

VESSEL_FILE = (
    PROCESSED /
    "step49g_vessel_candidates.csv"
)

CONTRACT_FILE = (
    PROCESSED /
    "step23_contract_sail_kill.csv"
)

BUNKER_FILE = (
    PROCESSED /
    "step50a_bunker_current.csv"
)

ROUTE_AUDIT_FILE = (
    OUTPUTS /
    "step51r_route_size_audit.csv"
)

PRODUCTION_FILE = (
    PROCESSED /
    "step51u_full_production_universe.csv"
)

REVIEW_FILE = (
    PROCESSED /
    "step51u_review_universe.csv"
)

SUMMARY_FILE = (
    OUTPUTS /
    "step51u_summary.csv"
)

QUALITY_FILE = (
    OUTPUTS /
    "step51u_quality.csv"
)

REPORT_FILE = (
    OUTPUTS /
    "step51u_report.json"
)


# =============================================================================
# HELPERS
# =============================================================================

def normalize_id(series):
    return (
        series.astype(str)
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

    if "HANDYSIZE" in s:
        return "HANDYSIZE"

    if "HANDY" in s:
        return "HANDYSIZE"

    if "CAPESIZE" in s:
        return "CAPE"

    if "VLOC" in s:
        return "CAPE"

    if "CAPE" in s:
        return "CAPE"

    return s


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
            f"{name} missing columns:\n"
            + "\n".join(missing)
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
print("STEP 51U - BUILD FULL PRODUCTION CANDIDATE UNIVERSE")
print("=" * 80)
print()

print("MODE: LOCAL ONLY")
print("MyShipTracking API calls: 0")
print("MyShipTracking credits: 0")
print("OilPriceAPI calls: 0")
print()


# =============================================================================
# CHECK FILES
# =============================================================================

for path in [
    DATE_FILE,
    VESSEL_FILE,
    CONTRACT_FILE,
    BUNKER_FILE,
]:

    if not path.exists():
        raise FileNotFoundError(
            f"Missing required input:\n{path}"
        )


# Route audit is useful but not allowed to block the complete rebuild.

route_audit_exists = ROUTE_AUDIT_FILE.exists()


# =============================================================================
# 1/9 LOAD
# =============================================================================

print("=" * 80)
print("1/9 - LOADING COMPLETE INPUT UNIVERSE")
print("=" * 80)
print()

dates = pd.read_csv(
    DATE_FILE
)

vessels = pd.read_csv(
    VESSEL_FILE
)

contracts = pd.read_csv(
    CONTRACT_FILE
)

bunker = pd.read_csv(
    BUNKER_FILE
)


print(
    "Step 51A rows:",
    len(dates)
)

print(
    "Step 49G vessels:",
    len(vessels)
)

print(
    "Contract scenario rows:",
    len(contracts)
)

print(
    "Bunker rows:",
    len(bunker)
)

print(
    "Route audit available:",
    route_audit_exists
)


# =============================================================================
# 2/9 NORMALIZE
# =============================================================================

print()
print("=" * 80)
print("2/9 - NORMALIZING")
print("=" * 80)
print()


require(
    dates,
    [
        "imo",
        "route_id",
        "departure_date",
        "estimated_eta",
    ],
    "Step 51A",
)

require(
    vessels,
    [
        "imo",
        "vessel_name",
        "dwt",
        "dwt_class",
    ],
    "Step 49G",
)

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
    "Contracts",
)

require(
    bunker,
    [
        "price_usd_per_metric_ton",
    ],
    "Bunker",
)


dates["imo"] = normalize_id(
    dates["imo"]
)

dates["route_id"] = normalize_id(
    dates["route_id"]
)

dates["departure_date"] = dates[
    "departure_date"
].apply(to_utc)

dates["estimated_eta"] = dates[
    "estimated_eta"
].apply(to_utc)


vessels["imo"] = normalize_id(
    vessels["imo"]
)

vessels["dwt"] = numeric(
    vessels["dwt"]
)

vessels["vessel_class_norm"] = (
    vessels["dwt_class"]
    .apply(normalize_class)
)


vessels = (
    vessels[
        [
            "imo",
            "vessel_name",
            "dwt",
            "dwt_class",
            "vessel_class_norm",
        ]
    ]
    .drop_duplicates(
        "imo",
        keep="first",
    )
)


contracts["contract_id"] = normalize_id(
    contracts["contract_id"]
)

contracts["route_id"] = normalize_id(
    contracts["route_id"]
)

contracts["contract_volume_mt"] = numeric(
    contracts["contract_volume_mt"]
)

contracts["contract_class_norm"] = (
    contracts["vessel_class"]
    .apply(normalize_class)
)

contracts["scenario"] = (
    contracts["scenario"]
    .astype(str)
    .str.strip()
    .str.lower()
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
        contracts[col] = numeric(
            contracts[col]
        )


# =============================================================================
# 3/9 CONTRACT MASTER
# =============================================================================

print()
print("=" * 80)
print("3/9 - BUILDING CONTRACT MASTER")
print("=" * 80)
print()


contract_meta = (
    contracts[
        [
            "contract_id",
            "route_id",
            "origin",
            "destination",
            "vessel_class",
            "contract_class_norm",
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
    .rename(
        columns={
            "bear": "bear_rate",
            "base": "base_rate",
            "bull": "bull_rate",
        }
    )
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


kill["kill_value"] = (
    numeric(
        kill["kill_alternative_value_usd"]
    )
    -
    numeric(
        kill["kill_penalty_usd"]
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


# =============================================================================
# 4/9 BUILD COMPLETE VESSEL/DATE POOL
# =============================================================================

print()
print("=" * 80)
print("4/9 - BUILDING COMPLETE VESSEL/DATE POOL")
print("=" * 80)
print()


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
        vessels,
        on="imo",
        how="inner",
    )
)


date_pool[
    "departure_dt"
] = date_pool[
    "departure_date"
].apply(
    to_utc
)

date_pool[
    "eta_dt"
] = date_pool[
    "estimated_eta"
].apply(
    to_utc
)


print(
    "Complete date-aware rows:",
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
# 5/9 BUILD ALL PHYSICAL CONTRACT × VESSEL × DATE PAIRS
# =============================================================================

print()
print("=" * 80)
print("5/9 - BUILDING ALL PHYSICAL PAIRS")
print("=" * 80)
print()


all_rows = []


capacity_rejected = 0
strict_class_rejected = 0
cross_class_review = 0


for _, contract in contract_meta.iterrows():

    route_id = contract[
        "route_id"
    ]

    cargo = float(
        contract[
            "contract_volume_mt"
        ]
    )

    contract_class = contract[
        "contract_class_norm"
    ]

    contract_id = contract[
        "contract_id"
    ]


    pool = date_pool[
        date_pool[
            "route_id"
        ]
        ==
        route_id
    ]


    for _, candidate in pool.iterrows():

        dwt = float(
            candidate[
                "dwt"
            ]
        )

        vessel_class = candidate[
            "vessel_class_norm"
        ]


        capacity_ok = (
            dwt >= cargo
        )


        if not capacity_ok:

            capacity_rejected += 1

            continue


        exact_class = (
            contract_class == ""
            or
            vessel_class == ""
            or
            contract_class
            ==
            vessel_class
        )


        row = {
            "contract_id":
                contract_id,

            "route_id":
                route_id,

            "origin":
                contract["origin"],

            "destination":
                contract["destination"],

            "cargo_type":
                contract["cargo_type"],

            "contract_volume_mt":
                cargo,

            "contract_class":
                contract_class,

            "vessel_class":
                vessel_class,

            "vessel_class_raw":
                candidate.get(
                    "dwt_class",
                    "",
                ),

            "imo":
                candidate["imo"],

            "vessel_name":
                candidate["vessel_name"],

            "vessel_dwt":
                dwt,

            "departure_date":
                candidate["departure_date"],

            "estimated_eta":
                candidate["estimated_eta"],

            "departure_dt":
                candidate["departure_dt"],

            "eta_dt":
                candidate["eta_dt"],

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

            "route_distance_nm":
                candidate.get(
                    "route_distance_nm",
                    np.nan,
                ),

            "route_speed_knots":
                candidate.get(
                    "route_speed_knots",
                    np.nan,
                ),

            "sea_hours":
                candidate.get(
                    "sea_hours",
                    np.nan,
                ),

            "port_days":
                candidate.get(
                    "port_days",
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
                contract["bear_rate"],

            "base_rate":
                contract["base_rate"],

            "bull_rate":
                contract["bull_rate"],

            "kill_value":
                contract["kill_value"],

            "capacity_ok":
                True,

            "exact_class_match":
                exact_class,

            "cross_class":
                not exact_class,

            "candidate_source":
                "STEP51A_COMPLETE_UNIVERSE",
        }


        all_rows.append(
            row
        )


        if not exact_class:

            cross_class_review += 1


all_candidates = pd.DataFrame(
    all_rows
)


print(
    "Capacity-feasible rows:",
    len(all_candidates)
)

print(
    "Capacity exclusions:",
    capacity_rejected
)

print(
    "Cross-class rows:",
    cross_class_review
)


# =============================================================================
# 6/9 APPLY ROUTE-SIZE REVIEW INFORMATION
# =============================================================================

print()
print("=" * 80)
print("6/9 - APPLYING ROUTE-SIZE AUDIT INFORMATION")
print("=" * 80)
print()


if route_audit_exists:

    route_audit = pd.read_csv(
        ROUTE_AUDIT_FILE
    )

    route_audit["contract_id"] = (
        normalize_id(
            route_audit[
                "contract_id"
            ]
        )
    )

    route_audit["route_id"] = (
        normalize_id(
            route_audit[
                "route_id"
            ]
        )
    )

    route_audit["imo"] = (
        normalize_id(
            route_audit[
                "imo"
            ]
        )
    )


    route_cols = [
        "contract_id",
        "route_id",
        "imo",
        "route_size_status",
        "production_flag",
    ]


    route_cols = [
        c
        for c in route_cols
        if c in route_audit.columns
    ]


    # 51R contains only the five selected cross-class rows.
    # Therefore this is audit context only.
    #
    # It must NOT remove candidates from the complete universe.

    cross_audit = (
        route_audit[
            route_cols
        ]
        .drop_duplicates(
            [
                "contract_id",
                "route_id",
                "imo",
            ]
        )
        .copy()
    )


    all_candidates = all_candidates.merge(
        cross_audit,
        on=[
            "contract_id",
            "route_id",
            "imo",
        ],
        how="left",
        suffixes=(
            "",
            "_audit",
        ),
    )


else:

    all_candidates[
        "route_size_status"
    ] = np.nan

    all_candidates[
        "production_flag"
    ] = np.nan


# =============================================================================
# 7/9 PRODUCTION GATE
# =============================================================================

print()
print("=" * 80)
print("7/9 - APPLYING COMPLETE PRODUCTION GATE")
print("=" * 80)
print()


# -------------------------------------------------------------------------
# CRITICAL POLICY
#
# Exact class -> production eligible.
#
# Cross class -> review only.
#
# The gate applies to ALL physical candidates, NOT only Step 51P winners.
# -------------------------------------------------------------------------

all_candidates[
    "production_status"
] = np.where(
    all_candidates[
        "exact_class_match"
    ],
    "PRODUCTION_ELIGIBLE",
    "REVIEW_ONLY_CROSS_CLASS",
)


all_candidates[
    "production_eligible"
] = (
    all_candidates[
        "production_status"
    ]
    ==
    "PRODUCTION_ELIGIBLE"
)


all_candidates[
    "review_only"
] = (
    all_candidates[
        "production_status"
    ]
    ==
    "REVIEW_ONLY_CROSS_CLASS"
)


all_candidates[
    "automatic_optimizer_allowed"
] = (
    all_candidates[
        "production_eligible"
    ]
)


all_candidates[
    "eligibility_reason"
] = np.where(
    all_candidates[
        "production_eligible"
    ],
    "DWT_CAPABLE_AND_EXACT_CLASS",
    "DWT_CAPABLE_BUT_CROSS_CLASS_REVIEW",
)


production = all_candidates[
    all_candidates[
        "production_eligible"
    ]
].copy()


review = all_candidates[
    all_candidates[
        "review_only"
    ]
].copy()


# De-duplicate exact decision rows.

production = (
    production
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


review = (
    review
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


print(
    "ALL physical candidate rows:",
    len(all_candidates)
)

print(
    "Production-eligible rows:",
    len(production)
)

print(
    "Review-only rows:",
    len(review)
)

print(
    "Production contracts:",
    production[
        "contract_id"
    ].nunique()
)

print(
    "Production vessels:",
    production[
        "imo"
    ].nunique()
)

print(
    "Production routes:",
    production[
        "route_id"
    ].nunique()
)


# =============================================================================
# 8/9 ECONOMIC COMPLETENESS CHECK
# =============================================================================

print()
print("=" * 80)
print("8/9 - CHECKING ECONOMIC COMPLETENESS")
print("=" * 80)
print()


economic_columns = [
    "bear_rate",
    "base_rate",
    "bull_rate",
    "kill_value",
]


for col in economic_columns:

    missing = int(
        production[
            col
        ].isna().sum()
    )

    print(
        f"{col}: missing {missing}"
    )

    if missing > 0:

        raise RuntimeError(
            f"Production universe has "
            f"{missing} missing values in {col}."
        )


print(
    "Economic completeness: PASS"
)


# =============================================================================
# 9/9 SAVE
# =============================================================================

print()
print("=" * 80)
print("9/9 - SAVING COMPLETE UNIVERSE")
print("=" * 80)
print()


production_columns = [
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
    "vessel_class_raw",
    "contract_class",
    "departure_date",
    "estimated_eta",
    "departure_dt",
    "eta_dt",
    "reposition_distance_nm",
    "reposition_hours",
    "route_distance_nm",
    "route_speed_knots",
    "sea_hours",
    "port_days",
    "total_voyage_hours",
    "total_voyage_days",
    "bear_rate",
    "base_rate",
    "bull_rate",
    "kill_value",
    "capacity_ok",
    "exact_class_match",
    "cross_class",
    "route_size_status",
    "production_flag",
    "production_status",
    "production_eligible",
    "review_only",
    "eligibility_reason",
    "automatic_optimizer_allowed",
    "candidate_source",
]


production_columns = [
    c
    for c in production_columns
    if c in production.columns
]


review_columns = [
    c
    for c in production_columns
    if c in review.columns
]


production[
    production_columns
].to_csv(
    PRODUCTION_FILE,
    index=False,
)


review[
    review_columns
].to_csv(
    REVIEW_FILE,
    index=False,
)


# =============================================================================
# SUMMARY
# =============================================================================

unique_production_contracts = (
    production[
        "contract_id"
    ].nunique()
)

unique_production_vessels = (
    production[
        "imo"
    ].nunique()
)

unique_production_routes = (
    production[
        "route_id"
    ].nunique()
)


unique_review_contracts = (
    review[
        "contract_id"
    ].nunique()
) if not review.empty else 0


unique_review_vessels = (
    review[
        "imo"
    ].nunique()
) if not review.empty else 0


cross_class_rows = int(
    all_candidates[
        "cross_class"
    ].sum()
)


exact_class_rows = int(
    all_candidates[
        "exact_class_match"
    ].sum()
)


summary = pd.DataFrame(
    [
        {
            "generated_utc":
                now_utc(),

            "step51a_input_rows":
                len(dates),

            "contract_scenario_rows":
                len(contracts),

            "unique_contracts":
                len(contract_meta),

            "complete_physical_candidates":
                len(all_candidates),

            "capacity_excluded":
                capacity_rejected,

            "exact_class_candidates":
                exact_class_rows,

            "cross_class_review_candidates":
                cross_class_rows,

            "production_candidate_rows":
                len(production),

            "review_only_rows":
                len(review),

            "production_contracts":
                unique_production_contracts,

            "production_vessels":
                unique_production_vessels,

            "production_routes":
                unique_production_routes,

            "review_contracts":
                unique_review_contracts,

            "review_vessels":
                unique_review_vessels,

            "live_bunker_price_usd_per_mt":
                float(
                    bunker[
                        "price_usd_per_metric_ton"
                    ].iloc[0]
                ),

            "myshiptracking_api_calls":
                0,

            "myshiptracking_credits":
                0,

            "oilpriceapi_calls":
                0,

            "status":
                "FULL_PRODUCTION_UNIVERSE_READY",
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
                "step51a_input_rows",
            "value":
                len(dates),
        },

        {
            "metric":
                "unique_contracts",
            "value":
                len(contract_meta),
        },

        {
            "metric":
                "complete_physical_candidates",
            "value":
                len(all_candidates),
        },

        {
            "metric":
                "capacity_excluded",
            "value":
                capacity_rejected,
        },

        {
            "metric":
                "exact_class_candidates",
            "value":
                exact_class_rows,
        },

        {
            "metric":
                "cross_class_review_candidates",
            "value":
                cross_class_rows,
        },

        {
            "metric":
                "production_candidate_rows",
            "value":
                len(production),
        },

        {
            "metric":
                "review_only_rows",
            "value":
                len(review),
        },

        {
            "metric":
                "production_contracts",
            "value":
                unique_production_contracts,
        },

        {
            "metric":
                "production_vessels",
            "value":
                unique_production_vessels,
        },

        {
            "metric":
                "production_routes",
            "value":
                unique_production_routes,
        },

        {
            "metric":
                "production_rows_missing_bear",
            "value":
                int(
                    production[
                        "bear_rate"
                    ].isna().sum()
                ),
        },

        {
            "metric":
                "production_rows_missing_base",
            "value":
                int(
                    production[
                        "base_rate"
                    ].isna().sum()
                ),
        },

        {
            "metric":
                "production_rows_missing_bull",
            "value":
                int(
                    production[
                        "bull_rate"
                    ].isna().sum()
                ),
        },

        {
            "metric":
                "production_rows_missing_kill_value",
            "value":
                int(
                    production[
                        "kill_value"
                    ].isna().sum()
                ),
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
        "FULL_PRODUCTION_UNIVERSE_READY",

    "critical_correction":
        (
            "Step 51U rebuilds the production universe from all Step 51A "
            "candidate rows rather than from the subset selected by Step 51P."
        ),

    "policy": {
        "capacity":
            "DWT >= contract cargo",

        "production_class":
            "exact declared vessel-class match",

        "cross_class":
            "review only",

        "route_size_audit":
            (
                "informational/review evidence; does not delete "
                "otherwise valid exact-class candidates"
            ),
    },

    "counts": {
        "step51a_rows":
            len(dates),

        "unique_contracts":
            len(contract_meta),

        "complete_physical_candidates":
            len(all_candidates),

        "capacity_excluded":
            capacity_rejected,

        "exact_class_candidates":
            exact_class_rows,

        "cross_class_review_candidates":
            cross_class_rows,

        "production_candidate_rows":
            len(production),

        "review_only_rows":
            len(review),
    },

    "production_dimensions": {
        "contracts":
            unique_production_contracts,

        "vessels":
            unique_production_vessels,

        "routes":
            unique_production_routes,
    },

    "bunker": {
        "price_usd_per_metric_ton":
            float(
                bunker[
                    "price_usd_per_metric_ton"
                ].iloc[0]
            ),
    },

    "api": {
        "myshiptracking_calls":
            0,

        "myshiptracking_credits":
            0,

        "oilpriceapi_calls":
            0,
    },

    "next_step":
        (
            "Build Step 51V final MILP from the COMPLETE Step 51U "
            "production universe, not from Step 51P or Step 51S."
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
print("STEP 51U COMPLETE")
print("=" * 80)
print()

print(
    "Step 51A input rows:",
    len(dates)
)

print(
    "Complete physical candidates:",
    len(all_candidates)
)

print(
    "Exact-class candidates:",
    exact_class_rows
)

print(
    "Cross-class review candidates:",
    cross_class_rows
)

print(
    "Production candidate rows:",
    len(production)
)

print(
    "Review-only rows:",
    len(review)
)

print(
    "Production contracts:",
    unique_production_contracts
)

print(
    "Production vessels:",
    unique_production_vessels
)

print(
    "Production routes:",
    unique_production_routes
)

print()
print(
    "Live VLSFO:",
    float(
        bunker[
            "price_usd_per_metric_ton"
        ].iloc[0]
    ),
    "USD/MT"
)

print()
print("NO API CALLS")
print("NO CREDITS CONSUMED")

print()
print("SAVED:")
print(
    PRODUCTION_FILE
)

print(
    REVIEW_FILE
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
