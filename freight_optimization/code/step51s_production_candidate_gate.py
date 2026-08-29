#!/usr/bin/env python3

"""
STEP 51S - PRODUCTION CANDIDATE GATE

LOCAL ONLY
----------

No MyShipTracking API calls.
No OilPriceAPI calls.
No credits.

PURPOSE
-------

Create a production-safe candidate universe from Step 51P.

POLICY
------

1. DWT capacity is mandatory.
2. Exact class match is production eligible.
3. Cross-class assignments are review-only.
4. Route-size concerns remain audit information.
5. Cross-class opportunities are NOT deleted; they are retained in
   review_only output.
6. This step does not modify Step 51I or Step 51P.

INPUTS
------

data/processed/step51a_optimizer_candidates.csv
data/processed/step49g_vessel_candidates.csv
data/processed/step23_contract_sail_kill.csv
data/processed/step50a_bunker_current.csv

outputs/step51p_calibrated_selected.csv
outputs/step51r_route_size_audit.csv

OUTPUTS
-------

outputs/step51s_production_candidates.csv
outputs/step51s_review_only_candidates.csv
outputs/step51s_summary.csv
outputs/step51s_quality.csv
outputs/step51s_report.json
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

CALIBRATED_SELECTED_FILE = (
    OUTPUTS /
    "step51p_calibrated_selected.csv"
)

ROUTE_SIZE_AUDIT_FILE = (
    OUTPUTS /
    "step51r_route_size_audit.csv"
)


PRODUCTION_FILE = (
    OUTPUTS /
    "step51s_production_candidates.csv"
)

REVIEW_FILE = (
    OUTPUTS /
    "step51s_review_only_candidates.csv"
)

SUMMARY_FILE = (
    OUTPUTS /
    "step51s_summary.csv"
)

QUALITY_FILE = (
    OUTPUTS /
    "step51s_quality.csv"
)

REPORT_FILE = (
    OUTPUTS /
    "step51s_report.json"
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
            "\n".join(
                missing
            )
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
print("STEP 51S - PRODUCTION CANDIDATE GATE")
print("=" * 80)
print()

print("MODE: LOCAL ONLY")
print("MyShipTracking API calls: 0")
print("MyShipTracking credits: 0")
print("OilPriceAPI calls: 0")
print()


# =============================================================================
# INPUT CHECK
# =============================================================================

for path in [
    DATE_FILE,
    VESSEL_FILE,
    CONTRACT_FILE,
    BUNKER_FILE,
    CALIBRATED_SELECTED_FILE,
    ROUTE_SIZE_AUDIT_FILE,
]:

    if not path.exists():

        raise FileNotFoundError(
            f"Required input missing:\n{path}"
        )


# =============================================================================
# 1/8 - LOAD
# =============================================================================

print("=" * 80)
print("1/8 - LOADING INPUTS")
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

selected = pd.read_csv(
    CALIBRATED_SELECTED_FILE
)

route_audit = pd.read_csv(
    ROUTE_SIZE_AUDIT_FILE
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
    "Contract rows:",
    len(contracts)
)

print(
    "Step 51P selected:",
    len(selected)
)

print(
    "Step 51R audit rows:",
    len(route_audit)
)


# =============================================================================
# 2/8 - NORMALIZE
# =============================================================================

print()
print("=" * 80)
print("2/8 - NORMALIZING")
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
        "vessel_class",
        "contract_volume_mt",
    ],
    "Contracts",
)

require(
    selected,
    [
        "contract_id",
        "route_id",
        "imo",
        "vessel_name",
        "vessel_dwt",
        "vessel_class",
        "contract_class",
        "contract_volume_mt",
        "departure_date",
        "estimated_eta",
        "cross_class",
    ],
    "Step 51P",
)

require(
    route_audit,
    [
        "contract_id",
        "route_id",
        "imo",
        "route_size_status",
        "production_flag",
    ],
    "Step 51R",
)


# -------------------------------------------------------------------------
# Normalize date candidate identifiers
# -------------------------------------------------------------------------

dates["imo"] = normalize_id(
    dates["imo"]
)

dates["route_id"] = normalize_id(
    dates["route_id"]
)

dates["departure_date"] = dates[
    "departure_date"
].apply(
    to_utc
)

dates["estimated_eta"] = dates[
    "estimated_eta"
].apply(
    to_utc
)


# -------------------------------------------------------------------------
# Normalize vessel identifiers
# -------------------------------------------------------------------------

vessels["imo"] = normalize_id(
    vessels["imo"]
)

vessels["dwt"] = numeric(
    vessels["dwt"]
)

vessels["vessel_class_norm"] = (
    vessels["dwt_class"]
    .apply(
        normalize_class
    )
)


# -------------------------------------------------------------------------
# Normalize contracts
# -------------------------------------------------------------------------

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
    .apply(
        normalize_class
    )
)


# -------------------------------------------------------------------------
# Normalize selected output
# -------------------------------------------------------------------------

selected["contract_id"] = normalize_id(
    selected["contract_id"]
)

selected["route_id"] = normalize_id(
    selected["route_id"]
)

selected["imo"] = normalize_id(
    selected["imo"]
)

selected["vessel_dwt"] = numeric(
    selected["vessel_dwt"]
)

selected["contract_volume_mt"] = numeric(
    selected["contract_volume_mt"]
)

selected["vessel_class_norm"] = (
    selected["vessel_class"]
    .apply(
        normalize_class
    )
)

selected["contract_class_norm"] = (
    selected["contract_class"]
    .apply(
        normalize_class
    )
)

selected["cross_class"] = (
    selected["cross_class"]
    .astype(str)
    .str.strip()
    .str.lower()
    .isin(
        [
            "true",
            "1",
            "yes",
        ]
    )
)

selected["departure_date"] = selected[
    "departure_date"
].apply(
    to_utc
)

selected["estimated_eta"] = selected[
    "estimated_eta"
].apply(
    to_utc
)


# -------------------------------------------------------------------------
# Normalize route audit
# -------------------------------------------------------------------------

route_audit["contract_id"] = normalize_id(
    route_audit["contract_id"]
)

route_audit["route_id"] = normalize_id(
    route_audit["route_id"]
)

route_audit["imo"] = normalize_id(
    route_audit["imo"]
)

route_audit["vessel_dwt"] = numeric(
    route_audit["vessel_dwt"]
)

route_audit["contract_volume_mt"] = numeric(
    route_audit["contract_volume_mt"]
)


# =============================================================================
# 3/8 - APPLY BASE ELIGIBILITY
# =============================================================================

print()
print("=" * 80)
print("3/8 - APPLYING BASE ELIGIBILITY")
print("=" * 80)
print()


# -------------------------------------------------------------------------
# Capacity
# -------------------------------------------------------------------------

selected["capacity_ok"] = (
    selected[
        "vessel_dwt"
    ]
    >=
    selected[
        "contract_volume_mt"
    ]
)


# -------------------------------------------------------------------------
# Exact declared-class match
# -------------------------------------------------------------------------

selected["exact_class_match"] = (
    selected[
        "vessel_class_norm"
    ]
    ==
    selected[
        "contract_class_norm"
    ]
)


# -------------------------------------------------------------------------
# Route audit information
# -------------------------------------------------------------------------

route_info_cols = [
    "contract_id",
    "route_id",
    "imo",
    "route_size_status",
    "production_flag",
]


route_info_cols = [
    c
    for c in route_info_cols
    if c in route_audit.columns
]


route_info = (
    route_audit[
        route_info_cols
    ]
    .drop_duplicates(
        [
            "contract_id",
            "route_id",
            "imo",
        ]
    )
)


selected = selected.merge(
    route_info,
    on=[
        "contract_id",
        "route_id",
        "imo",
    ],
    how="left",
    suffixes=(
        "",
        "_route",
    )
)


# =============================================================================
# CRITICAL FIX:
# Add ALL derived columns to selected BEFORE creating production/review
# subsets.
# =============================================================================

print()
print(
    "Building eligibility/status fields..."
)


selected[
    "eligibility_reason"
] = np.select(
    [
        ~selected[
            "capacity_ok"
        ],

        selected[
            "exact_class_match"
        ],

        ~selected[
            "exact_class_match"
        ],
    ],
    [
        "DWT_INSUFFICIENT",

        "EXACT_CLASS_AND_DWT_FEASIBLE",

        "CROSS_CLASS_REQUIRES_REVIEW",
    ],
    default="UNKNOWN",
)


selected[
    "production_status"
] = np.select(
    [
        ~selected[
            "capacity_ok"
        ],

        selected[
            "exact_class_match"
        ],
    ],
    [
        "REJECT_CAPACITY",

        "PRODUCTION_ELIGIBLE",
    ],
    default="REVIEW_ONLY_CROSS_CLASS",
)


selected[
    "production_eligible"
] = (
    selected[
        "production_status"
    ]
    ==
    "PRODUCTION_ELIGIBLE"
)


selected[
    "review_only"
] = (
    selected[
        "production_status"
    ]
    ==
    "REVIEW_ONLY_CROSS_CLASS"
)


selected[
    "automatic_optimizer_allowed"
] = (
    selected[
        "production_eligible"
    ]
)


# =============================================================================
# 4/8 - BUILD SUBSETS
# =============================================================================

print()
print("=" * 80)
print("4/8 - BUILDING PRODUCTION / REVIEW SETS")
print("=" * 80)
print()


production = selected[
    selected[
        "production_eligible"
    ]
].copy()


review_only = selected[
    selected[
        "review_only"
    ]
].copy()


rejected = selected[
    ~selected[
        "production_eligible"
    ]
    &
    ~selected[
        "review_only"
    ]
].copy()


print(
    "Production eligible:",
    len(production)
)

print(
    "Review only:",
    len(review_only)
)

print(
    "Rejected:",
    len(rejected)
)


# =============================================================================
# 5/8 - CROSS-CLASS DETAILS
# =============================================================================

print()
print("=" * 80)
print("5/8 - CHECKING CROSS-CLASS ASSIGNMENTS")
print("=" * 80)
print()


cross_class_total = int(
    selected[
        "cross_class"
    ].sum()
)


cross_class_review = int(
    review_only[
        "cross_class"
    ].sum()
)


cross_class_production = int(
    production[
        "cross_class"
    ].sum()
)


print(
    "Cross-class selected:",
    cross_class_total
)

print(
    "Cross-class in review:",
    cross_class_review
)

print(
    "Cross-class in production:",
    cross_class_production
)


# =============================================================================
# 6/8 - OUTPUT COLUMNS
# =============================================================================

print()
print("=" * 80)
print("6/8 - PREPARING OUTPUT SCHEMA")
print("=" * 80)
print()


output_columns = [
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
    "vessel_class_norm",
    "contract_class_norm",
    "exact_class_match",
    "cross_class",
    "departure_date",
    "estimated_eta",
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
    "capacity_ok",
    "route_size_status",
    "production_flag",
    "production_status",
    "production_eligible",
    "review_only",
    "eligibility_reason",
    "automatic_optimizer_allowed",
]


# -------------------------------------------------------------------------
# Add missing optional columns as NA instead of failing.
# -------------------------------------------------------------------------

for col in output_columns:

    if col not in selected.columns:

        selected[
            col
        ] = np.nan


# IMPORTANT:
# Re-slice AFTER all columns have been created.

production = selected[
    selected[
        "production_eligible"
    ]
].copy()

review_only = selected[
    selected[
        "review_only"
    ]
].copy()

rejected = selected[
    ~selected[
        "production_eligible"
    ]
    &
    ~selected[
        "review_only"
    ]
].copy()


# =============================================================================
# 7/8 - SAVE
# =============================================================================

print()
print("=" * 80)
print("7/8 - SAVING")
print("=" * 80)
print()


production[
    output_columns
].to_csv(
    PRODUCTION_FILE,
    index=False,
)


review_only[
    output_columns
].to_csv(
    REVIEW_FILE,
    index=False,
)


# Save rejected too, so no selected opportunity disappears.

REJECTED_FILE = (
    OUTPUTS /
    "step51s_rejected_candidates.csv"
)


rejected[
    output_columns
].to_csv(
    REJECTED_FILE,
    index=False,
)


# =============================================================================
# QUALITY
# =============================================================================

production_capacity_failures = int(
    (
        production[
            "capacity_ok"
        ]
        ==
        False
    ).sum()
)


production_cross_class = int(
    (
        production[
            "cross_class"
        ]
        ==
        True
    ).sum()
)


review_cross_class = int(
    (
        review_only[
            "cross_class"
        ]
        ==
        True
    ).sum()
)


route_size_review_count = int(
    (
        selected[
            "production_flag"
        ]
        ==
        "REVIEW_LARGE_VESSEL"
    ).sum()
)


quality = pd.DataFrame(
    [
        {
            "metric":
                "step51p_selected_rows",

            "value":
                len(selected),
        },

        {
            "metric":
                "production_eligible_rows",

            "value":
                len(production),
        },

        {
            "metric":
                "review_only_rows",

            "value":
                len(review_only),
        },

        {
            "metric":
                "rejected_rows",

            "value":
                len(rejected),
        },

        {
            "metric":
                "exact_class_rows",

            "value":
                int(
                    selected[
                        "exact_class_match"
                    ].sum()
                ),
        },

        {
            "metric":
                "cross_class_rows",

            "value":
                cross_class_total,
        },

        {
            "metric":
                "production_cross_class_rows",

            "value":
                production_cross_class,
        },

        {
            "metric":
                "review_cross_class_rows",

            "value":
                review_cross_class,
        },

        {
            "metric":
                "capacity_feasible_rows",

            "value":
                int(
                    selected[
                        "capacity_ok"
                    ].sum()
                ),
        },

        {
            "metric":
                "production_capacity_failures",

            "value":
                production_capacity_failures,
        },

        {
            "metric":
                "route_size_large_vessel_reviews",

            "value":
                route_size_review_count,
        },

        {
            "metric":
                "automatic_optimizer_allowed_rows",

            "value":
                len(production),
        },

        {
            "metric":
                "myshiptracking_api_calls",

            "value":
                0,
        },

        {
            "metric":
                "myshiptracking_credits",

            "value":
                0,
        },

        {
            "metric":
                "oilpriceapi_calls",

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
# 8/8 - SUMMARY + REPORT
# =============================================================================

print()
print("=" * 80)
print("8/8 - WRITING SUMMARY")
print("=" * 80)
print()


bunker_price = float(
    bunker[
        "price_usd_per_metric_ton"
    ].iloc[0]
)


summary = pd.DataFrame(
    [
        {
            "generated_utc":
                now_utc(),

            "step51p_selected":
                len(selected),

            "exact_class_selected":
                int(
                    selected[
                        "exact_class_match"
                    ].sum()
                ),

            "cross_class_selected":
                cross_class_total,

            "capacity_feasible_selected":
                int(
                    selected[
                        "capacity_ok"
                    ].sum()
                ),

            "production_eligible":
                len(production),

            "review_only":
                len(review_only),

            "rejected":
                len(rejected),

            "production_cross_class":
                production_cross_class,

            "review_cross_class":
                review_cross_class,

            "large_vessel_route_reviews":
                route_size_review_count,

            "automatic_optimizer_allowed":
                len(production),

            "live_bunker_price_usd_per_mt":
                bunker_price,

            "myshiptracking_api_calls":
                0,

            "myshiptracking_credits":
                0,

            "oilpriceapi_calls":
                0,

            "status":
                "PRODUCTION_CANDIDATE_GATE_COMPLETE",
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
        "PRODUCTION_CANDIDATE_GATE_COMPLETE",

    "purpose":
        (
            "Separate automatically production-eligible exact-class "
            "assignments from cross-class review-only assignments."
        ),

    "policy": {
        "dwt_is_hard_constraint":
            True,

        "exact_class_is_production_eligible":
            True,

        "cross_class_is_review_only":
            True,

        "cross_class_is_not_deleted":
            True,

        "route_typical_dwt_is":
            "audit_information_not_absolute_rejection",
    },

    "counts": {
        "step51p_selected":
            len(selected),

        "exact_class_selected":
            int(
                selected[
                    "exact_class_match"
                ].sum()
            ),

        "cross_class_selected":
            cross_class_total,

        "production_eligible":
            len(production),

        "review_only":
            len(review_only),

        "rejected":
            len(rejected),

        "production_cross_class":
            production_cross_class,

        "review_cross_class":
            review_cross_class,

        "large_vessel_route_reviews":
            route_size_review_count,
    },

    "production_rule":
        (
            "Automatic production optimizer eligibility requires "
            "DWT >= cargo and exact declared vessel-class match."
        ),

    "review_rule":
        (
            "Cross-class assignments remain visible in the review-only "
            "dataset and are not automatically sent to the production MILP."
        ),

    "important":
        (
            "The review-only dataset preserves economically attractive "
            "cross-class opportunities for later operational validation."
        ),

    "bunker": {
        "price_usd_per_metric_ton":
            bunker_price,
    },

    "api": {
        "myshiptracking_calls":
            0,

        "myshiptracking_credits":
            0,

        "oilpriceapi_calls":
            0,
    },

    "outputs": {
        "production":
            str(
                PRODUCTION_FILE
            ),

        "review_only":
            str(
                REVIEW_FILE
            ),

        "rejected":
            str(
                REJECTED_FILE
            ),

        "summary":
            str(
                SUMMARY_FILE
            ),

        "quality":
            str(
                QUALITY_FILE
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
# FINAL DISPLAY
# =============================================================================

print()
print("=" * 80)
print("STEP 51S COMPLETE")
print("=" * 80)
print()

print(
    "Step 51P selected:",
    len(selected)
)

print(
    "Exact-class selected:",
    int(
        selected[
            "exact_class_match"
        ].sum()
    )
)

print(
    "Cross-class selected:",
    cross_class_total
)

print(
    "Capacity-feasible selected:",
    int(
        selected[
            "capacity_ok"
        ].sum()
    )
)

print(
    "Production eligible:",
    len(production)
)

print(
    "Review only:",
    len(review_only)
)

print(
    "Rejected:",
    len(rejected)
)

print(
    "Production cross-class:",
    production_cross_class
)

print(
    "Review cross-class:",
    review_cross_class
)

print(
    "Large-vessel route reviews:",
    route_size_review_count
)

print()
print(
    "Live VLSFO:",
    bunker_price,
    "USD/MT"
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
    PRODUCTION_FILE
)

print(
    REVIEW_FILE
)

print(
    REJECTED_FILE
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
