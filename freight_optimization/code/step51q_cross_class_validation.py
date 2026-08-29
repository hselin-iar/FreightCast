#!/usr/bin/env python3

"""
STEP 51Q - CROSS-CLASS ASSIGNMENT VALIDATION

LOCAL ONLY
----------

No MyShipTracking API calls.
No MyShipTracking credits.
No OilPriceAPI calls.

PURPOSE
-------

Validate the cross-class assignments selected by Step 51P before they
are allowed into the production MILP.

This step does NOT change Step 51I or Step 51P.

Checks:

    1. DWT >= contract cargo
    2. DWT margin
    3. DWT utilization
    4. contract class
    5. vessel class
    6. exact / cross-class status
    7. selected departure date
    8. selected ETA
    9. Step 51A candidate verification
   10. repositioning information
   11. route distance
   12. voyage duration
   13. draft information when available
   14. current economics
   15. operational evidence completeness

IMPORTANT
---------

DWT sufficiency proves capacity feasibility only.

It does NOT prove:

    - commercial charter acceptance
    - port/berth acceptance
    - draft restrictions
    - cargo gear suitability
    - contractual restrictions

Therefore the result distinguishes:

    CROSS_CLASS_PHYSICALLY_SUPPORTED
    CROSS_CLASS_REQUIRES_OPERATIONAL_REVIEW

No external facts are invented.

INPUTS
------

data/processed/step23_contract_sail_kill.csv
data/processed/step49g_vessel_candidates.csv
data/processed/step51a_optimizer_candidates.csv
data/processed/step50a_bunker_current.csv
outputs/step51p_calibrated_selected.csv

OPTIONAL
--------

data/processed/route_distance_master.csv

OUTPUTS
-------

outputs/step51q_cross_class_audit.csv
outputs/step51q_route_operational_audit.csv
outputs/step51q_summary.csv
outputs/step51q_report.json
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
    "step51p_calibrated_selected.csv"
)

ROUTE_FILE = (
    PROCESSED /
    "route_distance_master.csv"
)


AUDIT_FILE = (
    OUTPUTS /
    "step51q_cross_class_audit.csv"
)

ROUTE_AUDIT_FILE = (
    OUTPUTS /
    "step51q_route_operational_audit.csv"
)

SUMMARY_FILE = (
    OUTPUTS /
    "step51q_summary.csv"
)

REPORT_FILE = (
    OUTPUTS /
    "step51q_report.json"
)


# =============================================================================
# HELPERS
# =============================================================================

def now_utc():
    return (
        pd.Timestamp.now(
            tz="UTC"
        ).isoformat()
    )


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
            f"{name} missing required columns:\n"
            +
            "\n".join(
                missing
            )
        )


def first_existing(
    df,
    candidates,
):

    for col in candidates:

        if col in df.columns:
            return col

    return None


# =============================================================================
# START
# =============================================================================

print()
print("=" * 80)
print("STEP 51Q - CROSS-CLASS ASSIGNMENT VALIDATION")
print("=" * 80)
print()

print("MODE: LOCAL ONLY")
print("MyShipTracking API calls: 0")
print("MyShipTracking credits: 0")
print("OilPriceAPI calls: 0")
print()


# =============================================================================
# INPUT FILE CHECK
# =============================================================================

for path in [
    CONTRACT_FILE,
    VESSEL_FILE,
    DATE_FILE,
    BUNKER_FILE,
    SELECTED_FILE,
]:

    if not path.exists():

        raise FileNotFoundError(
            f"Required file not found:\n{path}"
        )


# =============================================================================
# 1/8 - LOAD
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

bunker = pd.read_csv(
    BUNKER_FILE
)

selected = pd.read_csv(
    SELECTED_FILE
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
    "Selected Step 51P rows:",
    len(selected)
)


# =============================================================================
# 2/8 - NORMALIZE
# =============================================================================

print()
print("=" * 80)
print("2/8 - NORMALIZING IDENTIFIERS")
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
    ],
    "Contracts",
)

require(
    vessels,
    [
        "imo",
        "vessel_name",
        "dwt",
        "dwt_class",
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
    "Step 51A",
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
    "Step 51P selected",
)


# -------------------------------------------------------------------------
# Contracts
# -------------------------------------------------------------------------

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
    "contract_volume_mt"
] = numeric(
    contracts[
        "contract_volume_mt"
    ]
)

contracts[
    "contract_class_norm"
] = (
    contracts[
        "vessel_class"
    ]
    .apply(
        normalize_class
    )
)


# -------------------------------------------------------------------------
# Vessel master
# -------------------------------------------------------------------------

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
        "imo"
    )
)


# -------------------------------------------------------------------------
# Date candidates
# -------------------------------------------------------------------------

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
] = dates[
    "departure_date"
].apply(
    to_utc
)

dates[
    "estimated_eta"
] = dates[
    "estimated_eta"
].apply(
    to_utc
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


# -------------------------------------------------------------------------
# Step 51P selected
# -------------------------------------------------------------------------

selected[
    "contract_id"
] = normalize_id(
    selected[
        "contract_id"
    ]
)

selected[
    "route_id"
] = normalize_id(
    selected[
        "route_id"
    ]
)

selected[
    "imo"
] = normalize_id(
    selected[
        "imo"
    ]
)

selected[
    "vessel_dwt"
] = numeric(
    selected[
        "vessel_dwt"
    ]
)

selected[
    "contract_volume_mt"
] = numeric(
    selected[
        "contract_volume_mt"
    ]
)

selected[
    "vessel_class_norm"
] = (
    selected[
        "vessel_class"
    ]
    .apply(
        normalize_class
    )
)

selected[
    "contract_class_norm"
] = (
    selected[
        "contract_class"
    ]
    .apply(
        normalize_class
    )
)

selected[
    "cross_class"
] = (
    selected[
        "cross_class"
    ]
    .astype(str)
    .str.lower()
    .isin(
        [
            "true",
            "1",
            "yes",
        ]
    )
)

selected[
    "departure_date"
] = (
    selected[
        "departure_date"
    ]
    .apply(
        to_utc
    )
)

selected[
    "estimated_eta"
] = (
    selected[
        "estimated_eta"
    ]
    .apply(
        to_utc
    )
)


# =============================================================================
# 3/8 - ROUTE MASTER
# =============================================================================

print()
print("=" * 80)
print("3/8 - CHECKING ROUTE MASTER")
print("=" * 80)
print()


route_master = pd.DataFrame()

route_master_loaded = False


if ROUTE_FILE.exists():

    try:

        route_master = pd.read_csv(
            ROUTE_FILE
        )

        route_master_loaded = True

        if "route_id" in route_master.columns:

            route_master[
                "route_id"
            ] = normalize_id(
                route_master[
                    "route_id"
                ]
            )

        print(
            "Route master loaded:",
            len(route_master)
        )

        print(
            "Route columns:",
            list(
                route_master.columns
            )
        )

    except Exception as exc:

        print(
            "Route master read failed:",
            exc
        )

else:

    print(
        "Route master not found."
    )


# =============================================================================
# 4/8 - SELECT CROSS-CLASS
# =============================================================================

print()
print("=" * 80)
print("4/8 - IDENTIFYING CROSS-CLASS ASSIGNMENTS")
print("=" * 80)
print()


cross = selected[
    selected[
        "cross_class"
    ]
].copy()


print(
    "Selected assignments:",
    len(selected)
)

print(
    "Cross-class assignments:",
    len(cross)
)


# =============================================================================
# 5/8 - CROSS-CLASS VALIDATION
# =============================================================================

print()
print("=" * 80)
print("5/8 - VALIDATING CROSS-CLASS ASSIGNMENTS")
print("=" * 80)
print()


audit_rows = []


for _, row in cross.iterrows():

    contract_id = row[
        "contract_id"
    ]

    route_id = row[
        "route_id"
    ]

    imo = row[
        "imo"
    ]

    vessel_name = row[
        "vessel_name"
    ]

    vessel_class = row[
        "vessel_class_norm"
    ]

    contract_class = row[
        "contract_class_norm"
    ]

    vessel_dwt = float(
        row[
            "vessel_dwt"
        ]
    )

    cargo_mt = float(
        row[
            "contract_volume_mt"
        ]
    )

    departure = to_utc(
        row[
            "departure_date"
        ]
    )

    eta = to_utc(
        row[
            "estimated_eta"
        ]
    )


    # -------------------------------------------------------------------------
    # DWT
    # -------------------------------------------------------------------------

    dwt_margin_mt = (
        vessel_dwt
        -
        cargo_mt
    )

    dwt_utilization = (
        cargo_mt / vessel_dwt
        if vessel_dwt > 0
        else np.nan
    )

    capacity_ok = (
        vessel_dwt >= cargo_mt
    )


    # -------------------------------------------------------------------------
    # Class
    # -------------------------------------------------------------------------

    exact_class_match = (
        vessel_class
        ==
        contract_class
    )


    # -------------------------------------------------------------------------
    # Step 51A route/date candidate lookup
    # -------------------------------------------------------------------------

    matching = dates[
        (
            dates[
                "imo"
            ]
            ==
            imo
        )
        &
        (
            dates[
                "route_id"
            ]
            ==
            route_id
        )
    ].copy()


    route_date_found = (
        not matching.empty
    )


    date_verified = False

    selected_date_diff_minutes = np.nan
    selected_eta_diff_minutes = np.nan


    if not matching.empty:

        # Timestamp columns are UTC-aware.
        matching[
            "_dep_diff"
        ] = (
            matching[
                "departure_date"
            ]
            -
            departure
        ).abs()


        matching[
            "_eta_diff"
        ] = (
            matching[
                "estimated_eta"
            ]
            -
            eta
        ).abs()


        # FIX:
        # Parentheses close BEFORE bool conversion.
        #
        # We are computing:
        #
        #     ((condition1) & (condition2)).any()
        #
        # rather than:
        #
        #     bool(condition1 & condition2).any()
        #

        selected_date_match_series = (
            (
                matching[
                    "_dep_diff"
                ]
                <=
                pd.Timedelta(
                    minutes=1
                )
            )
            &
            (
                matching[
                    "_eta_diff"
                ]
                <=
                pd.Timedelta(
                    minutes=1
                )
            )
        )


        selected_date_match = bool(
            selected_date_match_series.any()
        )


        date_verified = (
            selected_date_match
        )


        if date_verified:

            matching_verified = (
                matching[
                    selected_date_match_series
                ]
                .copy()
            )

            matching_verified = (
                matching_verified
                .sort_values(
                    [
                        "_dep_diff",
                        "_eta_diff",
                    ]
                )
                .iloc[
                    [0]
                ]
            )


            selected_date_diff_minutes = (
                matching_verified[
                    "_dep_diff"
                ]
                .iloc[0]
                .total_seconds()
                /
                60.0
            )


            selected_eta_diff_minutes = (
                matching_verified[
                    "_eta_diff"
                ]
                .iloc[0]
                .total_seconds()
                /
                60.0
            )


            matching_for_physics = (
                matching_verified
            )

        else:

            matching_for_physics = (
                matching
                .sort_values(
                    [
                        "_dep_diff",
                        "_eta_diff",
                    ]
                )
                .iloc[
                    [0]
                ]
            )

    else:

        matching_for_physics = (
            pd.DataFrame()
        )


    # -------------------------------------------------------------------------
    # Pull route/date physical values
    # -------------------------------------------------------------------------

    reposition_nm = np.nan
    reposition_hours = np.nan
    route_distance_nm = np.nan
    route_speed_knots = np.nan
    voyage_days = np.nan
    voyage_hours = np.nan


    if not matching_for_physics.empty:

        candidate_row = (
            matching_for_physics.iloc[0]
        )


        if (
            "reposition_distance_nm"
            in candidate_row.index
        ):

            reposition_nm = pd.to_numeric(
                candidate_row[
                    "reposition_distance_nm"
                ],
                errors="coerce",
            )


        if (
            "reposition_hours"
            in candidate_row.index
        ):

            reposition_hours = pd.to_numeric(
                candidate_row[
                    "reposition_hours"
                ],
                errors="coerce",
            )


        if (
            "route_distance_nm"
            in candidate_row.index
        ):

            route_distance_nm = pd.to_numeric(
                candidate_row[
                    "route_distance_nm"
                ],
                errors="coerce",
            )


        if (
            "route_speed_knots"
            in candidate_row.index
        ):

            route_speed_knots = pd.to_numeric(
                candidate_row[
                    "route_speed_knots"
                ],
                errors="coerce",
            )


        if (
            "total_voyage_days"
            in candidate_row.index
        ):

            voyage_days = pd.to_numeric(
                candidate_row[
                    "total_voyage_days"
                ],
                errors="coerce",
            )


        if (
            "total_voyage_hours"
            in candidate_row.index
        ):

            voyage_hours = pd.to_numeric(
                candidate_row[
                    "total_voyage_hours"
                ],
                errors="coerce",
            )


    # -------------------------------------------------------------------------
    # Draft
    # -------------------------------------------------------------------------

    draft_col = first_existing(
        selected,
        [
            "draught",
            "draft",
            "vessel_draught",
            "vessel_draft",
        ],
    )


    if draft_col is not None:

        draft_value = pd.to_numeric(
            row[
                draft_col
            ],
            errors="coerce",
        )

    else:

        draft_value = np.nan


    # -------------------------------------------------------------------------
    # Route master comparison
    # -------------------------------------------------------------------------

    route_master_found = False

    typical_route_draft = np.nan
    route_expected_dwt_min = np.nan
    route_expected_dwt_max = np.nan
    route_typical_class = ""


    if (
        route_master_loaded
        and
        "route_id" in route_master.columns
    ):

        rm = route_master[
            route_master[
                "route_id"
            ]
            ==
            route_id
        ]


        if not rm.empty:

            route_master_found = True

            rm_row = rm.iloc[0]


            if "typical_draft_m" in rm_row.index:

                typical_route_draft = pd.to_numeric(
                    rm_row[
                        "typical_draft_m"
                    ],
                    errors="coerce",
                )


            if "typical_dwt_min" in rm_row.index:

                route_expected_dwt_min = pd.to_numeric(
                    rm_row[
                        "typical_dwt_min"
                    ],
                    errors="coerce",
                )


            if "typical_dwt_max" in rm_row.index:

                route_expected_dwt_max = pd.to_numeric(
                    rm_row[
                        "typical_dwt_max"
                    ],
                    errors="coerce",
                )


            if "vessel_class" in rm_row.index:

                route_typical_class = normalize_class(
                    rm_row[
                        "vessel_class"
                    ]
                )


    # -------------------------------------------------------------------------
    # Evidence flags
    # -------------------------------------------------------------------------

    evidence = []


    if capacity_ok:

        evidence.append(
            "DWT_CAPABLE"
        )

    else:

        evidence.append(
            "DWT_INSUFFICIENT"
        )


    evidence.append(
        "CROSS_CLASS"
    )


    if route_date_found:

        evidence.append(
            "ROUTE_DATE_OBSERVED"
        )

    else:

        evidence.append(
            "ROUTE_DATE_NOT_FOUND"
        )


    if date_verified:

        evidence.append(
            "SELECTED_DATE_VERIFIED"
        )

    else:

        evidence.append(
            "SELECTED_DATE_NOT_VERIFIED"
        )


    if pd.notna(reposition_nm):

        evidence.append(
            "REPOSITION_KNOWN"
        )

    else:

        evidence.append(
            "REPOSITION_UNKNOWN"
        )


    if pd.notna(route_distance_nm):

        evidence.append(
            "ROUTE_DISTANCE_KNOWN"
        )

    else:

        evidence.append(
            "ROUTE_DISTANCE_UNKNOWN"
        )


    if pd.notna(draft_value):

        evidence.append(
            "VESSEL_DRAFT_AVAILABLE"
        )

    else:

        evidence.append(
            "VESSEL_DRAFT_UNAVAILABLE"
        )


    if route_master_found:

        evidence.append(
            "ROUTE_MASTER_FOUND"
        )

    else:

        evidence.append(
            "ROUTE_MASTER_NOT_FOUND"
        )


    # -------------------------------------------------------------------------
    # Validation classification
    # -------------------------------------------------------------------------

    if not capacity_ok:

        validation_status = (
            "REJECT_DWT_INSUFFICIENT"
        )

    elif (
        route_date_found
        and
        date_verified
        and
        pd.notna(reposition_nm)
    ):

        validation_status = (
            "CROSS_CLASS_PHYSICALLY_SUPPORTED"
        )

    else:

        validation_status = (
            "CROSS_CLASS_REQUIRES_OPERATIONAL_REVIEW"
        )


    audit_rows.append(
        {
            "contract_id":
                contract_id,

            "route_id":
                route_id,

            "origin":
                row.get(
                    "origin",
                    "",
                ),

            "destination":
                row.get(
                    "destination",
                    "",
                ),

            "cargo_type":
                row.get(
                    "cargo_type",
                    "",
                ),

            "contract_class":
                contract_class,

            "vessel_class":
                vessel_class,

            "imo":
                imo,

            "vessel_name":
                vessel_name,

            "vessel_dwt_mt":
                vessel_dwt,

            "contract_cargo_mt":
                cargo_mt,

            "dwt_margin_mt":
                dwt_margin_mt,

            "dwt_utilization":
                dwt_utilization,

            "capacity_ok":
                capacity_ok,

            "exact_class_match":
                exact_class_match,

            "cross_class":
                True,

            "departure_date":
                departure,

            "estimated_eta":
                eta,

            "route_date_candidate_found":
                route_date_found,

            "selected_date_matches_51a":
                date_verified,

            "selected_departure_diff_minutes":
                selected_date_diff_minutes,

            "selected_eta_diff_minutes":
                selected_eta_diff_minutes,

            "reposition_distance_nm":
                reposition_nm,

            "reposition_hours":
                reposition_hours,

            "route_distance_nm":
                route_distance_nm,

            "route_speed_knots":
                route_speed_knots,

            "voyage_days":
                voyage_days,

            "voyage_hours":
                voyage_hours,

            "vessel_draft":
                draft_value,

            "route_typical_draft_m":
                typical_route_draft,

            "route_typical_dwt_min":
                route_expected_dwt_min,

            "route_typical_dwt_max":
                route_expected_dwt_max,

            "route_typical_class":
                route_typical_class,

            "route_master_found":
                route_master_found,

            "bear_sail_usd":
                row.get(
                    "bear_sail",
                    np.nan,
                ),

            "base_sail_usd":
                row.get(
                    "base_sail",
                    np.nan,
                ),

            "bull_sail_usd":
                row.get(
                    "bull_sail",
                    np.nan,
                ),

            "worst_incremental_usd":
                row.get(
                    "worst_incremental",
                    np.nan,
                ),

            "expected_incremental_usd":
                row.get(
                    "expected_incremental",
                    np.nan,
                ),

            "validation_status":
                validation_status,

            "evidence":
                "|".join(
                    evidence
                ),
        }
    )


audit = pd.DataFrame(
    audit_rows
)


# =============================================================================
# 6/8 - ROUTE OPERATIONAL AUDIT
# =============================================================================

print()
print("=" * 80)
print("6/8 - BUILDING ROUTE OPERATIONAL AUDIT")
print("=" * 80)
print()


if audit.empty:

    route_audit = pd.DataFrame(
        columns=[
            "contract_id",
            "route_id",
            "origin",
            "destination",
            "imo",
            "vessel_name",
            "vessel_class",
            "contract_class",
            "cross_class",
            "route_distance_nm",
            "reposition_distance_nm",
            "reposition_hours",
            "voyage_days",
            "route_date_candidate_found",
            "selected_date_matches_51a",
            "route_status",
        ]
    )

else:

    route_audit = audit[
        [
            "contract_id",
            "route_id",
            "origin",
            "destination",
            "imo",
            "vessel_name",
            "vessel_class",
            "contract_class",
            "cross_class",
            "route_distance_nm",
            "reposition_distance_nm",
            "reposition_hours",
            "voyage_days",
            "route_date_candidate_found",
            "selected_date_matches_51a",
        ]
    ].copy()


    route_audit[
        "route_status"
    ] = np.where(
        route_audit[
            "route_date_candidate_found"
        ],
        "AIS_ROUTE_DATE_OBSERVED",
        "ROUTE_DATE_NOT_VERIFIED",
    )


# =============================================================================
# 7/8 - SUMMARY
# =============================================================================

print()
print("=" * 80)
print("7/8 - SUMMARY")
print("=" * 80)
print()


cross_count = len(
    audit
)

dwt_capable_count = int(
    audit[
        "capacity_ok"
    ].sum()
) if not audit.empty else 0


route_date_count = int(
    audit[
        "route_date_candidate_found"
    ].sum()
) if not audit.empty else 0


date_verified_count = int(
    audit[
        "selected_date_matches_51a"
    ].sum()
) if not audit.empty else 0


reposition_known_count = int(
    audit[
        "reposition_distance_nm"
    ].notna().sum()
) if not audit.empty else 0


route_distance_known_count = int(
    audit[
        "route_distance_nm"
    ].notna().sum()
) if not audit.empty else 0


draft_available_count = int(
    audit[
        "vessel_draft"
    ].notna().sum()
) if not audit.empty else 0


physically_supported_count = int(
    (
        audit[
            "validation_status"
        ]
        ==
        "CROSS_CLASS_PHYSICALLY_SUPPORTED"
    ).sum()
) if not audit.empty else 0


review_count = int(
    (
        audit[
            "validation_status"
        ]
        ==
        "CROSS_CLASS_REQUIRES_OPERATIONAL_REVIEW"
    ).sum()
) if not audit.empty else 0


reject_count = int(
    (
        audit[
            "validation_status"
        ]
        ==
        "REJECT_DWT_INSUFFICIENT"
    ).sum()
) if not audit.empty else 0


print(
    "Cross-class assignments:",
    cross_count
)

print(
    "DWT capable:",
    dwt_capable_count
)

print(
    "Route/date observed:",
    route_date_count
)

print(
    "Selected date verified:",
    date_verified_count
)

print(
    "Reposition known:",
    reposition_known_count
)

print(
    "Route distance known:",
    route_distance_known_count
)

print(
    "Draft available:",
    draft_available_count
)

print(
    "Physically supported:",
    physically_supported_count
)

print(
    "Requires operational review:",
    review_count
)

print(
    "DWT rejected:",
    reject_count
)


# =============================================================================
# 8/8 - SAVE
# =============================================================================

print()
print("=" * 80)
print("8/8 - SAVING OUTPUTS")
print("=" * 80)
print()


audit.to_csv(
    AUDIT_FILE,
    index=False,
)

route_audit.to_csv(
    ROUTE_AUDIT_FILE,
    index=False,
)


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

            "selected_assignments":
                len(selected),

            "cross_class_selected":
                cross_count,

            "dwt_capable_cross_class":
                dwt_capable_count,

            "route_date_verified_cross_class":
                route_date_count,

            "selected_date_verified_cross_class":
                date_verified_count,

            "reposition_known_cross_class":
                reposition_known_count,

            "route_distance_known_cross_class":
                route_distance_known_count,

            "draft_available_cross_class":
                draft_available_count,

            "cross_class_physically_supported":
                physically_supported_count,

            "cross_class_requires_operational_review":
                review_count,

            "cross_class_dwt_rejected":
                reject_count,

            "live_bunker_price_usd_per_mt":
                bunker_price,

            "myshiptracking_api_calls":
                0,

            "myshiptracking_credits":
                0,

            "oilpriceapi_calls":
                0,

            "status":
                "CROSS_CLASS_AUDIT_COMPLETE",
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
        "CROSS_CLASS_AUDIT_COMPLETE",

    "purpose":
        (
            "Validate cross-class assignments selected by Step 51P "
            "without automatically assuming commercial approval."
        ),

    "selected_assignments":
        len(selected),

    "cross_class_selected":
        cross_count,

    "counts": {
        "dwt_capable":
            dwt_capable_count,

        "route_date_verified":
            route_date_count,

        "selected_date_verified":
            date_verified_count,

        "reposition_known":
            reposition_known_count,

        "route_distance_known":
            route_distance_known_count,

        "draft_available":
            draft_available_count,

        "physically_supported":
            physically_supported_count,

        "requires_operational_review":
            review_count,

        "dwt_rejected":
            reject_count,
    },

    "policy": {
        "dwt_is_hard_capacity_constraint":
            True,

        "cross_class_auto_approval":
            False,

        "cross_class_without_operational_evidence":
            "REQUIRES_OPERATIONAL_REVIEW",
    },

    "important": [
        (
            "DWT sufficiency proves capacity feasibility only."
        ),

        (
            "An AIS route/date observation verifies that the candidate "
            "exists in the current dataset; it does not prove charter "
            "availability or port acceptance."
        ),

        (
            "Draft compatibility is not inferred when draft data is absent."
        ),

        (
            "Commercial restrictions not present in the input data "
            "are not invented."
        ),

        (
            "This step does not modify Step 51I or Step 51P."
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
        "cross_class_audit":
            str(
                AUDIT_FILE
            ),

        "route_operational_audit":
            str(
                ROUTE_AUDIT_FILE
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
print("STEP 51Q COMPLETE")
print("=" * 80)
print()

print(
    "Cross-class selected:",
    cross_count
)

print(
    "DWT capable:",
    dwt_capable_count
)

print(
    "Route/date verified:",
    route_date_count
)

print(
    "Selected date verified:",
    date_verified_count
)

print(
    "Reposition known:",
    reposition_known_count
)

print(
    "Route distance known:",
    route_distance_known_count
)

print(
    "Draft available:",
    draft_available_count
)

print(
    "Physically supported:",
    physically_supported_count
)

print(
    "Requires operational review:",
    review_count
)

print(
    "DWT rejected:",
    reject_count
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
    AUDIT_FILE
)

print(
    ROUTE_AUDIT_FILE
)

print(
    SUMMARY_FILE
)

print(
    REPORT_FILE
)
