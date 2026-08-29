#!/usr/bin/env python3

"""
STEP 51H - REPAIR DWT / CAPACITY PROPAGATION

LOCAL ONLY
----------
MyShipTracking API calls: 0
MyShipTracking credits: 0
OilPriceAPI calls: 0

PURPOSE
-------
Repair missing DWT propagation into the MILP input.

AUTHORITATIVE DWT SOURCE
------------------------
data/processed/step49g_vessel_candidates.csv

Step 49G was previously verified to contain:

    36 vessel candidates
    12 vessels with known DWT

The current Step 51B file contains no DWT field.

Therefore this step:
    1. Loads Step 49G
    2. Uses `dwt` as authoritative DWT
    3. Joins DWT to Step 51B by IMO
    4. Preserves all existing Step 51B columns
    5. Adds:
         vessel_dwt
         capacity_known
         capacity_feasible
         capacity_margin_mt
    6. Saves repaired MILP input

NO API CALLS.
NO CREDIT CONSUMPTION.
NO MILP EXECUTION.

NEXT
----
Point Step 51G INPUT_FILE to:

    step51h_repaired_milp_input.csv

and rerun Step 51G.
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

STEP49G_FILE = (
    PROCESSED
    / "step49g_vessel_candidates.csv"
)

STEP51B_FILE = (
    PROCESSED
    / "step51b_milp_input.csv"
)

REPAIRED_FILE = (
    PROCESSED
    / "step51h_repaired_milp_input.csv"
)

SUMMARY_FILE = (
    OUTPUTS
    / "step51h_capacity_summary.csv"
)

QUALITY_FILE = (
    OUTPUTS
    / "step51h_capacity_quality.csv"
)

VESSEL_FILE = (
    OUTPUTS
    / "step51h_capacity_vessels.csv"
)

REPORT_FILE = (
    OUTPUTS
    / "step51h_capacity_report.json"
)


# =============================================================================
# HELPERS
# =============================================================================

def normalize_imo(series):

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


def require_columns(
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
print(
    "STEP 51H - REPAIR DWT / CAPACITY PROPAGATION"
)
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

print()


# =============================================================================
# 1. CHECK INPUT FILES
# =============================================================================

print("=" * 80)
print("1/7 - CHECKING INPUT FILES")
print("=" * 80)
print()

if not STEP49G_FILE.exists():

    raise FileNotFoundError(
        STEP49G_FILE
    )

if not STEP51B_FILE.exists():

    raise FileNotFoundError(
        STEP51B_FILE
    )


# =============================================================================
# 2. LOAD
# =============================================================================

print("=" * 80)
print("2/7 - LOADING STEP 49G / 51B")
print("=" * 80)
print()

candidates = pd.read_csv(
    STEP49G_FILE
)

milp_input = pd.read_csv(
    STEP51B_FILE
)

print(
    "Step 49G rows:",
    len(candidates)
)

print(
    "Step 51B rows:",
    len(milp_input)
)


# =============================================================================
# 3. VALIDATE SOURCE DATA
# =============================================================================

print()
print("=" * 80)
print("3/7 - VALIDATING AUTHORITATIVE DWT SOURCE")
print("=" * 80)
print()

require_columns(
    candidates,
    [
        "imo",
        "vessel_name",
        "dwt",
    ],
    "Step 49G vessel candidates",
)

require_columns(
    milp_input,
    [
        "imo",
        "cargo_quantity_mt",
    ],
    "Step 51B MILP input",
)


# =============================================================================
# NORMALIZE IMO
# =============================================================================

candidates[
    "imo"
] = normalize_imo(
    candidates[
        "imo"
    ]
)

milp_input[
    "imo"
] = normalize_imo(
    milp_input[
        "imo"
    ]
)


# =============================================================================
# NORMALIZE DWT / CARGO
# =============================================================================

candidates[
    "dwt"
] = numeric(
    candidates[
        "dwt"
    ]
)

milp_input[
    "cargo_quantity_mt"
] = numeric(
    milp_input[
        "cargo_quantity_mt"
    ]
)


# =============================================================================
# CHECK SOURCE DWT
# =============================================================================

source_unique = (
    candidates[
        [
            "imo",
            "vessel_name",
            "dwt",
        ]
    ]
    .drop_duplicates(
        subset=[
            "imo",
        ],
        keep="first",
    )
)


source_known = source_unique[
    source_unique[
        "dwt"
    ].notna()
    &
    (
        source_unique[
            "dwt"
        ]
        > 0
    )
].copy()


print(
    "Unique Step 49G vessels:",
    source_unique[
        "imo"
    ].nunique()
)

print(
    "Unique vessels with known DWT:",
    source_known[
        "imo"
    ].nunique()
)


print()
print(
    "Authoritative DWT records:"
)

if not source_known.empty:

    print(
        source_known
        [
            [
                "imo",
                "vessel_name",
                "dwt",
            ]
        ]
        .sort_values(
            "imo"
        )
        .to_string(
            index=False
        )
    )


# =============================================================================
# 4. BUILD DWT LOOKUP
# =============================================================================

print()
print("=" * 80)
print("4/7 - JOINING DWT INTO STEP 51B")
print("=" * 80)
print()

dwt_lookup = (
    source_unique[
        [
            "imo",
            "dwt",
        ]
    ]
    .rename(
        columns={
            "dwt":
                "_authoritative_dwt"
        }
    )
)


# Check whether any duplicate IMO mappings exist.

duplicate_source_imos = int(
    source_unique[
        "imo"
    ]
    .duplicated(
        keep=False
    )
    .sum()
)

print(
    "Duplicate IMO source rows:",
    duplicate_source_imos
)


# Merge by IMO.

repaired = milp_input.merge(
    dwt_lookup,
    on="imo",
    how="left",
)


# =============================================================================
# CREATE vessel_dwt
# =============================================================================

# If an old vessel_dwt somehow exists in 51B, preserve a valid value.
#
# Otherwise use authoritative Step 49G DWT.

if "vessel_dwt" in repaired.columns:

    repaired[
        "vessel_dwt"
    ] = numeric(
        repaired[
            "vessel_dwt"
        ]
    )

    repaired[
        "vessel_dwt"
    ] = (
        repaired[
            "vessel_dwt"
        ]
        .combine_first(
            repaired[
                "_authoritative_dwt"
            ]
        )
    )

else:

    repaired[
        "vessel_dwt"
    ] = repaired[
        "_authoritative_dwt"
    ]


repaired[
    "vessel_dwt"
] = numeric(
    repaired[
        "vessel_dwt"
    ]
)


repaired = repaired.drop(
    columns=[
        "_authoritative_dwt"
    ]
)


# =============================================================================
# 5. CAPACITY FEASIBILITY
# =============================================================================

print()
print("=" * 80)
print("5/7 - APPLYING CAPACITY CHECK")
print("=" * 80)
print()

repaired[
    "capacity_known"
] = (
    repaired[
        "vessel_dwt"
    ]
    .notna()
    &
    (
        repaired[
            "vessel_dwt"
        ]
        > 0
    )
)


repaired[
    "capacity_margin_mt"
] = (
    repaired[
        "vessel_dwt"
    ]
    -
    repaired[
        "cargo_quantity_mt"
    ]
)


# Unknown DWT is NOT automatically declared infeasible.
#
# We retain it, because absence of metadata does not prove the vessel
# cannot carry the cargo.
#
# But the MILP can choose to exclude unknown-capacity vessels later
# depending on the production policy.

repaired[
    "capacity_feasible"
] = (
    ~repaired[
        "capacity_known"
    ]
    |
    (
        repaired[
            "capacity_margin_mt"
        ]
        >=
        0
    )
)


capacity_known_rows = int(
    repaired[
        "capacity_known"
    ]
    .sum()
)


capacity_unknown_rows = int(
    (
        ~repaired[
            "capacity_known"
        ]
    )
    .sum()
)


capacity_infeasible_rows = int(
    (
        repaired[
            "capacity_known"
        ]
        &
        (
            repaired[
                "capacity_margin_mt"
            ]
            < 0
        )
    )
    .sum()
)


capacity_feasible_known_rows = int(
    (
        repaired[
            "capacity_known"
        ]
        &
        repaired[
            "capacity_feasible"
        ]
    )
    .sum()
)


print(
    "Capacity-known rows:",
    capacity_known_rows
)

print(
    "Capacity-unknown rows:",
    capacity_unknown_rows
)

print(
    "Known-capacity feasible rows:",
    capacity_feasible_known_rows
)

print(
    "Known-capacity infeasible rows:",
    capacity_infeasible_rows
)


# =============================================================================
# CAPACITY-READY VESSEL SUMMARY
# =============================================================================

vessel_capacity = (
    repaired[
        [
            "imo",
            "vessel_name",
            "vessel_dwt",
            "capacity_known",
        ]
    ]
    .drop_duplicates(
        subset=[
            "imo",
        ],
        keep="first",
    )
)


vessel_capacity[
    "max_cargo_seen_mt"
] = (
    repaired
    .groupby(
        "imo"
    )[
        "cargo_quantity_mt"
    ]
    .transform(
        "max"
    )
)


# Rebuild against unique rows cleanly.

max_cargo = (
    repaired
    .groupby(
        [
            "imo",
            "vessel_name",
        ],
        dropna=False,
    )[
        "cargo_quantity_mt"
    ]
    .max()
    .reset_index(
        name="max_cargo_seen_mt"
    )
)


vessel_capacity = (
    repaired[
        [
            "imo",
            "vessel_name",
            "vessel_dwt",
            "capacity_known",
        ]
    ]
    .drop_duplicates(
        subset=[
            "imo",
        ],
        keep="first",
    )
    .merge(
        max_cargo,
        on=[
            "imo",
            "vessel_name",
        ],
        how="left",
    )
)


vessel_capacity[
    "can_cover_max_cargo"
] = (
    ~vessel_capacity[
        "capacity_known"
    ]
    |
    (
        vessel_capacity[
            "vessel_dwt"
        ]
        >=
        vessel_capacity[
            "max_cargo_seen_mt"
        ]
    )
)


# =============================================================================
# 6. SAVE
# =============================================================================

print()
print("=" * 80)
print("6/7 - SAVING REPAIRED INPUT")
print("=" * 80)
print()

repaired.to_csv(
    REPAIRED_FILE,
    index=False,
)

vessel_capacity.to_csv(
    VESSEL_FILE,
    index=False,
)


# =============================================================================
# QUALITY
# =============================================================================

quality = pd.DataFrame(
    [
        {
            "metric":
                "step49g_rows",
            "value":
                len(candidates),
        },

        {
            "metric":
                "step49g_unique_vessels",
            "value":
                candidates[
                    "imo"
                ].nunique(),
        },

        {
            "metric":
                "step49g_known_dwt_vessels",
            "value":
                source_known[
                    "imo"
                ].nunique(),
        },

        {
            "metric":
                "step51b_rows",
            "value":
                len(milp_input),
        },

        {
            "metric":
                "repaired_rows",
            "value":
                len(repaired),
        },

        {
            "metric":
                "capacity_known_rows",
            "value":
                capacity_known_rows,
        },

        {
            "metric":
                "capacity_unknown_rows",
            "value":
                capacity_unknown_rows,
        },

        {
            "metric":
                "capacity_feasible_known_rows",
            "value":
                capacity_feasible_known_rows,
        },

        {
            "metric":
                "capacity_infeasible_rows",
            "value":
                capacity_infeasible_rows,
        },

        {
            "metric":
                "unique_capacity_known_vessels",
            "value":
                vessel_capacity[
                    "capacity_known"
                ].sum(),
        },

        {
            "metric":
                "unique_vessels_covering_max_cargo",
            "value":
                vessel_capacity[
                    "can_cover_max_cargo"
                ].sum(),
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
# SUMMARY
# =============================================================================

summary = pd.DataFrame(
    [
        {
            "generated_utc":
                now_utc(),

            "step49g_vessels":
                candidates[
                    "imo"
                ].nunique(),

            "step49g_known_dwt_vessels":
                source_known[
                    "imo"
                ].nunique(),

            "step51b_rows":
                len(milp_input),

            "repaired_rows":
                len(repaired),

            "capacity_known_rows":
                capacity_known_rows,

            "capacity_unknown_rows":
                capacity_unknown_rows,

            "capacity_feasible_known_rows":
                capacity_feasible_known_rows,

            "capacity_infeasible_rows":
                capacity_infeasible_rows,

            "unique_capacity_known_vessels":
                int(
                    vessel_capacity[
                        "capacity_known"
                    ].sum()
                ),

            "unique_vessels_covering_max_cargo":
                int(
                    vessel_capacity[
                        "can_cover_max_cargo"
                    ].sum()
                ),

            "api_calls_myshiptracking":
                0,

            "myshiptracking_credits_consumed":
                0,

            "oilpriceapi_calls":
                0,

            "status":
                "CAPACITY_FIELDS_REPAIRED",
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

    "status":
        "CAPACITY_FIELDS_REPAIRED",

    "authoritative_source":
        str(
            STEP49G_FILE
        ),

    "authoritative_dwt_column":
        "dwt",

    "target_file":
        str(
            STEP51B_FILE
        ),

    "repaired_file":
        str(
            REPAIRED_FILE
        ),

    "statistics": {
        "step49g_unique_vessels":
            int(
                candidates[
                    "imo"
                ].nunique()
            ),

        "step49g_known_dwt_vessels":
            int(
                source_known[
                    "imo"
                ].nunique()
            ),

        "step51b_rows":
            int(
                len(milp_input)
            ),

        "repaired_rows":
            int(
                len(repaired)
            ),

        "capacity_known_rows":
            capacity_known_rows,

        "capacity_unknown_rows":
            capacity_unknown_rows,

        "capacity_feasible_known_rows":
            capacity_feasible_known_rows,

        "capacity_infeasible_rows":
            capacity_infeasible_rows,
    },

    "capacity_policy":
        (
            "Known DWT must be >= cargo quantity. "
            "Unknown DWT is retained rather than falsely "
            "declared infeasible."
        ),

    "important": [
        (
            "Step 51B had no DWT column, so there was no field "
            "to read from Step 51B."
        ),

        (
            "Step 49G dwt is used as the authoritative source."
        ),

        (
            "DWT is joined using IMO."
        ),

        (
            "Step 51G must use the repaired file for capacity "
            "to participate."
        ),

        "No API calls were made.",
        "No MyShipTracking credits were consumed.",
        "No OilPriceAPI calls were made.",
        "No MILP was run.",
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
print("STEP 51H COMPLETE")
print("=" * 80)
print()

print(
    "Step 49G unique vessels:",
    candidates[
        "imo"
    ].nunique()
)

print(
    "Step 49G known-DWT vessels:",
    source_known[
        "imo"
    ].nunique()
)

print(
    "Step 51B rows:",
    len(milp_input)
)

print(
    "Repaired rows:",
    len(repaired)
)

print(
    "Capacity-known rows:",
    capacity_known_rows
)

print(
    "Capacity-unknown rows:",
    capacity_unknown_rows
)

print(
    "Known-capacity feasible rows:",
    capacity_feasible_known_rows
)

print(
    "Known-capacity infeasible rows:",
    capacity_infeasible_rows
)

print()
print(
    "Capacity-known vessels:"
)

print(
    vessel_capacity
    .sort_values(
        "imo"
    )
    .to_string(
        index=False
    )
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
print("=" * 80)
print("SAVED")
print("=" * 80)
print()

print(
    REPAIRED_FILE
)

print(
    VESSEL_FILE
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
print("DO NOT RUN 51G UNTIL YOU REVIEW THE CAPACITY COUNTS")
print("=" * 80)
