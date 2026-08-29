#!/usr/bin/env python3

"""
STEP 51A - DEPARTURE DATE FEASIBILITY

LOCAL ONLY
----------
MyShipTracking API calls: 0
MyShipTracking credits: 0
OilPriceAPI calls: 0

Purpose
-------
Build:

    VESSEL × ROUTE × DEPARTURE DATE

and calculate:

    AIS position
        ↓
    loading-port repositioning distance
        ↓
    repositioning time
        ↓
    physical departure feasibility
        ↓
    route transit time
        ↓
    ETA

This step does not claim commercial charter availability.

A feasible row means the vessel can physically reach the
route origin by the planned departure date under the deterministic
assumptions used here.

Inputs
------
step49i_enriched_vessel_candidates.csv
route_distance_master.csv
step50c_optimizer_economics.csv

Outputs
-------
step51a_departure_feasibility_all.csv
step51a_optimizer_candidates.csv

and reports under outputs/
"""


from pathlib import Path
from datetime import datetime, timezone
import json
import math
import os

import numpy as np
import pandas as pd


# =============================================================================
# PATHS
# =============================================================================

ROOT = Path(
    "/home/aryashekhar/freight-optimization"
)

PROCESSED = (
    ROOT / "data" / "processed"
)

OUTPUTS = (
    ROOT / "outputs"
)

VESSEL_FILE = (
    PROCESSED
    / "step49i_enriched_vessel_candidates.csv"
)

ROUTE_FILE = (
    PROCESSED
    / "route_distance_master.csv"
)

ECONOMICS_FILE = (
    PROCESSED
    / "step50c_optimizer_economics.csv"
)

ALL_FILE = (
    PROCESSED
    / "step51a_departure_feasibility_all.csv"
)

OPTIMIZER_FILE = (
    PROCESSED
    / "step51a_optimizer_candidates.csv"
)

SUMMARY_FILE = (
    OUTPUTS
    / "step51a_summary.csv"
)

QUALITY_FILE = (
    OUTPUTS
    / "step51a_quality.csv"
)

VRD_SUMMARY_FILE = (
    OUTPUTS
    / "step51a_vessel_route_date_summary.csv"
)

REPORT_FILE = (
    OUTPUTS
    / "step51a_report.json"
)


# =============================================================================
# CONFIG
# =============================================================================

DEFAULT_START_DATE = "2026-08-29"
DEFAULT_END_DATE = "2026-09-07"

START_DATE = pd.Timestamp(
    os.environ.get(
        "START_DATE",
        DEFAULT_START_DATE,
    )
)

END_DATE = pd.Timestamp(
    os.environ.get(
        "END_DATE",
        DEFAULT_END_DATE,
    )
)

if END_DATE < START_DATE:
    raise RuntimeError(
        "END_DATE is earlier than START_DATE."
    )

DEPARTURE_DATES = pd.date_range(
    START_DATE,
    END_DATE,
    freq="D",
)

REPOSITION_BUFFER_HOURS = 6.0

DEFAULT_SPEED_KNOTS = 10.0


# =============================================================================
# HELPERS
# =============================================================================

def now_utc():
    return pd.Timestamp.now(
        tz="UTC"
    ).isoformat()


def safe_float(
    value,
    default=np.nan,
):

    try:

        if pd.isna(value):
            return default

        return float(value)

    except Exception:

        return default


def normalize_route_id(
    value
):

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

        return str(
            value
        ).strip()


def haversine_nm(
    lat1,
    lon1,
    lat2,
    lon2,
):

    values = [
        lat1,
        lon1,
        lat2,
        lon2,
    ]

    if any(
        pd.isna(x)
        for x in values
    ):

        return np.nan

    radius_nm = 3440.065

    phi1 = math.radians(
        float(lat1)
    )

    phi2 = math.radians(
        float(lat2)
    )

    dphi = math.radians(
        float(lat2) - float(lat1)
    )

    dlambda = math.radians(
        float(lon2) - float(lon1)
    )

    a = (
        math.sin(dphi / 2.0) ** 2
        +
        math.cos(phi1)
        *
        math.cos(phi2)
        *
        math.sin(dlambda / 2.0) ** 2
    )

    a = min(
        1.0,
        max(
            0.0,
            a,
        ),
    )

    c = (
        2.0
        *
        math.atan2(
            math.sqrt(a),
            math.sqrt(
                1.0 - a
            ),
        )
    )

    return (
        radius_nm
        *
        c
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
            f"{name} missing columns:\n"
            +
            "\n".join(missing)
        )


# =============================================================================
# START
# =============================================================================

print()
print("=" * 80)
print(
    "STEP 51A - DEPARTURE DATE FEASIBILITY"
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

print(
    "Planning window:",
    START_DATE.strftime("%Y-%m-%d"),
    "to",
    END_DATE.strftime("%Y-%m-%d"),
)

print(
    "Departure dates:",
    len(DEPARTURE_DATES),
)


# =============================================================================
# INPUT CHECK
# =============================================================================

for path in [
    VESSEL_FILE,
    ROUTE_FILE,
    ECONOMICS_FILE,
]:

    if not path.exists():

        raise FileNotFoundError(
            str(path)
        )


# =============================================================================
# LOAD
# =============================================================================

print()
print("=" * 80)
print("1/7 - LOADING EXISTING DATA")
print("=" * 80)
print()

vessels = pd.read_csv(
    VESSEL_FILE
)

routes = pd.read_csv(
    ROUTE_FILE
)

economics = pd.read_csv(
    ECONOMICS_FILE
)

print(
    "Vessel rows:",
    len(vessels)
)

print(
    "Route rows:",
    len(routes)
)

print(
    "Economics rows:",
    len(economics)
)


# =============================================================================
# VALIDATION
# =============================================================================

require_columns(
    vessels,
    [
        "imo",
        "vessel_name",
        "lat",
        "lon",
    ],
    "Step 49I vessel file",
)

require_columns(
    routes,
    [
        "route_id",
        "origin",
        "destination",
        "origin_latitude",
        "origin_longitude",
        "distance_nm",
        "speed_knots",
        "port_days",
    ],
    "route_distance_master",
)

require_columns(
    economics,
    [
        "imo",
        "route_id",
        "scenario",
    ],
    "Step 50C optimizer economics",
)


# =============================================================================
# NORMALIZE IDs
# =============================================================================

vessels[
    "imo"
] = (
    vessels[
        "imo"
    ]
    .astype(str)
    .str.strip()
)

economics[
    "imo"
] = (
    economics[
        "imo"
    ]
    .astype(str)
    .str.strip()
)

economics[
    "route_id"
] = (
    economics[
        "route_id"
    ]
    .apply(
        normalize_route_id
    )
)

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
# FILTER AIS VESSELS
# =============================================================================

if "optimizer_vessel_ready" in vessels.columns:

    vessels = vessels[
        vessels[
            "optimizer_vessel_ready"
        ]
        .fillna(False)
    ].copy()


print(
    "Optimizer-ready vessel rows:",
    len(vessels)
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


# =============================================================================
# BUILD ECONOMIC VESSEL-ROUTE PAIRS
# =============================================================================

print()
print("=" * 80)
print("2/7 - BUILDING ECONOMIC VESSEL-ROUTE PAIRS")
print("=" * 80)
print()

economic_pairs = (
    economics[
        [
            "imo",
            "route_id",
        ]
    ]
    .drop_duplicates()
    .reset_index(drop=True)
)

print(
    "Economic vessel-route pairs:",
    len(economic_pairs)
)


# =============================================================================
# JOIN AIS VESSEL DATA
# =============================================================================

pairs = economic_pairs.merge(
    vessels,
    on="imo",
    how="inner",
)


print(
    "Pairs with AIS vessels:",
    len(pairs)
)


# =============================================================================
# JOIN ROUTE DATA
#
# Explicit suffixing is used here to prevent destination/origin collisions.
# =============================================================================

route_fields = [
    "route_id",
    "origin",
    "destination",
    "origin_latitude",
    "origin_longitude",
    "distance_nm",
    "speed_knots",
    "port_days",
    "cargo_type",
]


route_fields = [
    c
    for c in route_fields
    if c in routes.columns
]


route_subset = routes[
    route_fields
].copy()


route_subset = route_subset.rename(
    columns={
        "origin":
            "route_origin",

        "destination":
            "route_destination",

        "origin_latitude":
            "route_origin_latitude",

        "origin_longitude":
            "route_origin_longitude",

        "distance_nm":
            "route_distance_nm",

        "speed_knots":
            "route_speed_knots",

        "port_days":
            "route_port_days",

        "cargo_type":
            "route_cargo_type",
    }
)


pairs = pairs.merge(
    route_subset,
    on="route_id",
    how="left",
    indicator=True,
)


missing_route_rows = int(
    (
        pairs[
            "_merge"
        ]
        != "both"
    ).sum()
)


print(
    "Pairs missing route master:",
    missing_route_rows
)


if missing_route_rows:

    missing_ids = (
        pairs.loc[
            pairs[
                "_merge"
            ]
            != "both",
            "route_id",
        ]
        .dropna()
        .drop_duplicates()
        .tolist()
    )

    print(
        "Missing route IDs:",
        missing_ids
    )

    raise RuntimeError(
        "Some economic route IDs are missing from route_distance_master.csv."
    )


pairs = pairs.drop(
    columns=[
        "_merge"
    ]
)


# =============================================================================
# DISPLAY ROUTE FIELDS
# =============================================================================

print()
print(
    "Route metadata columns successfully joined:"
)

print(
    [
        "route_origin",
        "route_destination",
        "route_origin_latitude",
        "route_origin_longitude",
        "route_distance_nm",
        "route_speed_knots",
        "route_port_days",
    ]
)


# =============================================================================
# NUMERIC ROUTE FIELDS
# =============================================================================

for col in [
    "route_origin_latitude",
    "route_origin_longitude",
    "route_distance_nm",
    "route_speed_knots",
    "route_port_days",
]:

    pairs[
        col
    ] = pd.to_numeric(
        pairs[
            col
        ],
        errors="coerce",
    )


# =============================================================================
# BUILD DATE MATRIX
# =============================================================================

print()
print("=" * 80)
print("3/7 - CALCULATING REPOSITIONING AND ETA")
print("=" * 80)
print()

records = []


for _, pair in pairs.iterrows():

    imo = pair[
        "imo"
    ]

    vessel_name = pair[
        "vessel_name"
    ]

    route_id = pair[
        "route_id"
    ]

    # -------------------------------------------------------------------------
    # Explicit route fields — no ambiguous origin/destination access.
    # -------------------------------------------------------------------------

    origin = pair[
        "route_origin"
    ]

    destination = pair[
        "route_destination"
    ]

    vessel_lat = safe_float(
        pair[
            "lat"
        ]
    )

    vessel_lon = safe_float(
        pair[
            "lon"
        ]
    )

    origin_lat = safe_float(
        pair[
            "route_origin_latitude"
        ]
    )

    origin_lon = safe_float(
        pair[
            "route_origin_longitude"
        ]
    )

    route_distance_nm = safe_float(
        pair[
            "route_distance_nm"
        ]
    )

    route_speed = safe_float(
        pair[
            "route_speed_knots"
        ]
    )

    route_port_days = safe_float(
        pair[
            "route_port_days"
        ],
        default=0.0,
    )

    # -------------------------------------------------------------------------
    # Route speed
    # -------------------------------------------------------------------------

    if (
        pd.isna(route_speed)
        or
        route_speed <= 0
    ):

        route_speed = (
            DEFAULT_SPEED_KNOTS
        )

        speed_source = (
            "DEFAULT_ROUTE_SPEED"
        )

    else:

        speed_source = (
            "ROUTE_MASTER_SPEED"
        )


    # -------------------------------------------------------------------------
    # Current AIS -> loading origin
    # -------------------------------------------------------------------------

    reposition_nm = haversine_nm(
        vessel_lat,
        vessel_lon,
        origin_lat,
        origin_lon,
    )


    if (
        not pd.isna(reposition_nm)
        and
        route_speed > 0
    ):

        reposition_hours = (
            reposition_nm
            /
            route_speed
        )

        reposition_hours_buffered = (
            reposition_hours
            +
            REPOSITION_BUFFER_HOURS
        )

    else:

        reposition_hours = np.nan
        reposition_hours_buffered = np.nan


    # -------------------------------------------------------------------------
    # Route transit
    # -------------------------------------------------------------------------

    if (
        not pd.isna(route_distance_nm)
        and
        route_speed > 0
    ):

        sea_hours = (
            route_distance_nm
            /
            route_speed
        )

    else:

        sea_hours = np.nan


    if not pd.isna(
        sea_hours
    ):

        total_voyage_hours = (
            sea_hours
            +
            route_port_days * 24.0
        )

    else:

        total_voyage_hours = np.nan


    if not pd.isna(
        total_voyage_hours
    ):

        total_voyage_days = (
            total_voyage_hours
            /
            24.0
        )

    else:

        total_voyage_days = np.nan


    # -------------------------------------------------------------------------
    # AIS observation timestamp
    # -------------------------------------------------------------------------

    observation_timestamp = pd.NaT

    timestamp_candidates = [
        "ais_received_timestamp",
        "last_observation_timestamp",
        "observation_timestamp",
        "received",
    ]

    for column in timestamp_candidates:

        if column in pair.index:

            value = pair[
                column
            ]

            if pd.notna(value):

                observation_timestamp = pd.to_datetime(
                    value,
                    utc=True,
                    errors="coerce",
                )

                if not pd.isna(
                    observation_timestamp
                ):

                    break


    # If Step 49I candidate file doesn't carry the original AIS timestamp,
    # use the current planning timestamp rather than inventing an old one.

    if pd.isna(
        observation_timestamp
    ):

        observation_timestamp = pd.Timestamp.now(
            tz="UTC"
        )


    # -------------------------------------------------------------------------
    # Earliest arrival at loading origin
    # -------------------------------------------------------------------------

    if not pd.isna(
        reposition_hours_buffered
    ):

        earliest_origin_arrival = (
            observation_timestamp
            +
            pd.to_timedelta(
                reposition_hours_buffered,
                unit="h",
            )
        )

    else:

        earliest_origin_arrival = pd.NaT


    if not pd.isna(
        earliest_origin_arrival
    ):

        earliest_departure_date = (
            earliest_origin_arrival
            .normalize()
        )

    else:

        earliest_departure_date = pd.NaT


    # -------------------------------------------------------------------------
    # One row for every planned departure date
    # -------------------------------------------------------------------------

    for departure_date in DEPARTURE_DATES:

        departure_datetime = (
            departure_date
            .tz_localize(
                "UTC"
            )
        )


        if (
            not pd.isna(
                earliest_origin_arrival
            )
            and
            departure_datetime
            >=
            earliest_origin_arrival
        ):

            departure_feasible = True

            physical_status = (
                "FEASIBLE"
            )

        else:

            departure_feasible = False

            physical_status = (
                "NOT_REACHABLE_BY_DEPARTURE"
            )


        if (
            departure_feasible
            and
            not pd.isna(
                total_voyage_hours
            )
        ):

            estimated_eta = (
                departure_datetime
                +
                pd.to_timedelta(
                    total_voyage_hours,
                    unit="h",
                )
            )

        else:

            estimated_eta = pd.NaT


        records.append(
            {
                "imo":
                    imo,

                "vessel_name":
                    vessel_name,

                "route_id":
                    route_id,

                "origin":
                    origin,

                "destination":
                    destination,

                "departure_date":
                    departure_date.strftime(
                        "%Y-%m-%d"
                    ),

                "departure_datetime_utc":
                    departure_datetime,

                "ais_observation_timestamp":
                    observation_timestamp,

                "vessel_lat":
                    vessel_lat,

                "vessel_lon":
                    vessel_lon,

                "origin_latitude":
                    origin_lat,

                "origin_longitude":
                    origin_lon,

                "reposition_distance_nm":
                    reposition_nm,

                "reposition_hours":
                    reposition_hours,

                "reposition_buffer_hours":
                    REPOSITION_BUFFER_HOURS,

                "reposition_hours_buffered":
                    reposition_hours_buffered,

                "earliest_origin_arrival":
                    earliest_origin_arrival,

                "earliest_departure_date":
                    earliest_departure_date,

                "route_distance_nm":
                    route_distance_nm,

                "route_speed_knots":
                    route_speed,

                "speed_source":
                    speed_source,

                "sea_hours":
                    sea_hours,

                "port_days":
                    route_port_days,

                "total_voyage_hours":
                    total_voyage_hours,

                "total_voyage_days":
                    total_voyage_days,

                "estimated_eta":
                    estimated_eta,

                "departure_feasible":
                    departure_feasible,

                "physical_status":
                    physical_status,

                "ais_freshness_minutes":
                    pair.get(
                        "freshness_minutes",
                        np.nan,
                    ),

                "source":
                    "STEP49I_AIS_PLUS_ROUTE_MASTER",
            }
        )


all_dates = pd.DataFrame(
    records
)


print(
    "All vessel-route-date rows:",
    len(all_dates)
)


# =============================================================================
# FEASIBLE SUBSET
# =============================================================================

print()
print("=" * 80)
print("4/7 - FILTERING PHYSICALLY FEASIBLE DATES")
print("=" * 80)
print()

feasible = all_dates[
    all_dates[
        "departure_feasible"
    ]
    .fillna(False)
].copy()


print(
    "Feasible vessel-route-date rows:",
    len(feasible)
)

print(
    "Unique feasible vessels:",
    feasible[
        "imo"
    ].nunique()
)

print(
    "Unique feasible routes:",
    feasible[
        "route_id"
    ].nunique()
)

print(
    "Unique feasible departure dates:",
    feasible[
        "departure_date"
    ].nunique()
)


# =============================================================================
# JOIN SCENARIOS
# =============================================================================

print()
print("=" * 80)
print("5/7 - ATTACHING BEAR / BASE / BULL ECONOMICS")
print("=" * 80)
print()

scenario_fields = [
    "imo",
    "route_id",
    "scenario",
    "freight_rate_usd_per_mt",
    "cargo_quantity_mt",
    "live_scenario_revenue_usd",
    "live_bunker_price_usd_per_mt",
    "bunker_market_reference",
    "live_bunker_cost_usd",
    "live_total_voyage_cost_usd",
    "live_scenario_profit_usd",
]

scenario_fields = [
    c
    for c in scenario_fields
    if c in economics.columns
]


scenario_lookup = (
    economics[
        scenario_fields
    ]
    .drop_duplicates(
        subset=[
            "imo",
            "route_id",
            "scenario",
        ],
        keep="last",
    )
)


final_candidates = feasible.merge(
    scenario_lookup,
    on=[
        "imo",
        "route_id",
    ],
    how="left",
)


final_candidates[
    "scenario_economics_available"
] = (
    final_candidates[
        "scenario"
    ]
    .notna()
)


print(
    "Date-feasible rows:",
    len(feasible)
)

print(
    "Date × scenario rows:",
    len(final_candidates)
)

print(
    "Rows with scenario economics:",
    int(
        final_candidates[
            "scenario_economics_available"
        ]
        .sum()
    )
)


# =============================================================================
# STABLE KEY
# =============================================================================

final_candidates[
    "planner_candidate_key"
] = (
    final_candidates[
        "imo"
    ].astype(str)
    +
    "_R"
    +
    final_candidates[
        "route_id"
    ].astype(str)
    +
    "_"
    +
    final_candidates[
        "departure_date"
    ].astype(str)
    +
    "_"
    +
    final_candidates[
        "scenario"
    ].fillna(
        "unknown"
    ).astype(str)
)


# =============================================================================
# SAVE
# =============================================================================

print()
print("=" * 80)
print("6/7 - SAVING")
print("=" * 80)
print()

all_dates.to_csv(
    ALL_FILE,
    index=False,
)

final_candidates.to_csv(
    OPTIMIZER_FILE,
    index=False,
)


# =============================================================================
# VESSEL-ROUTE SUMMARY
# =============================================================================

if feasible.empty:

    vrd_summary = pd.DataFrame(
        columns=[
            "imo",
            "vessel_name",
            "route_id",
            "origin",
            "destination",
            "feasible_departure_dates",
            "first_feasible_departure",
            "last_feasible_departure",
            "reposition_distance_nm",
            "reposition_hours",
            "estimated_total_voyage_days",
        ]
    )

else:

    vrd_summary = (
        feasible
        .groupby(
            [
                "imo",
                "vessel_name",
                "route_id",
                "origin",
                "destination",
            ],
            dropna=False,
        )
        .agg(
            feasible_departure_dates=(
                "departure_date",
                "count",
            ),

            first_feasible_departure=(
                "departure_date",
                "min",
            ),

            last_feasible_departure=(
                "departure_date",
                "max",
            ),

            reposition_distance_nm=(
                "reposition_distance_nm",
                "first",
            ),

            reposition_hours=(
                "reposition_hours",
                "first",
            ),

            estimated_total_voyage_days=(
                "total_voyage_days",
                "first",
            ),
        )
        .reset_index()
    )


vrd_summary.to_csv(
    VRD_SUMMARY_FILE,
    index=False,
)


# =============================================================================
# QUALITY
# =============================================================================

all_rows = len(
    all_dates
)

feasible_rows = len(
    feasible
)

not_reachable_rows = (
    all_rows
    -
    feasible_rows
)

final_rows = len(
    final_candidates
)

economics_rows = int(
    final_candidates[
        "scenario_economics_available"
    ]
    .fillna(False)
    .sum()
)


quality = pd.DataFrame(
    [
        {
            "metric":
                "vessel_candidates_input",
            "value":
                len(vessels),
        },

        {
            "metric":
                "economic_vessel_route_pairs",
            "value":
                len(economic_pairs),
        },

        {
            "metric":
                "physical_vessel_route_pairs",
            "value":
                len(pairs),
        },

        {
            "metric":
                "planning_departure_dates",
            "value":
                len(DEPARTURE_DATES),
        },

        {
            "metric":
                "all_vessel_route_date_rows",
            "value":
                all_rows,
        },

        {
            "metric":
                "feasible_vessel_route_date_rows",
            "value":
                feasible_rows,
        },

        {
            "metric":
                "not_reachable_date_rows",
            "value":
                not_reachable_rows,
        },

        {
            "metric":
                "final_date_scenario_rows",
            "value":
                final_rows,
        },

        {
            "metric":
                "final_rows_with_economics",
            "value":
                economics_rows,
        },

        {
            "metric":
                "unique_final_vessels",
            "value":
                final_candidates[
                    "imo"
                ].nunique(),
        },

        {
            "metric":
                "unique_final_routes",
            "value":
                final_candidates[
                    "route_id"
                ].nunique(),
        },

        {
            "metric":
                "unique_final_departure_dates",
            "value":
                final_candidates[
                    "departure_date"
                ].nunique(),
        },

        {
            "metric":
                "unique_final_scenarios",
            "value":
                final_candidates[
                    "scenario"
                ].nunique(),
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
# SUMMARY
# =============================================================================

summary = pd.DataFrame(
    [
        {
            "generated_utc":
                now_utc(),

            "planning_start_date":
                START_DATE.strftime(
                    "%Y-%m-%d"
                ),

            "planning_end_date":
                END_DATE.strftime(
                    "%Y-%m-%d"
                ),

            "planning_departure_dates":
                len(DEPARTURE_DATES),

            "vessel_candidates":
                len(vessels),

            "economic_vessel_route_pairs":
                len(economic_pairs),

            "physical_vessel_route_pairs":
                len(pairs),

            "all_vessel_route_date_rows":
                all_rows,

            "feasible_vessel_route_date_rows":
                feasible_rows,

            "not_reachable_date_rows":
                not_reachable_rows,

            "final_date_scenario_rows":
                final_rows,

            "scenario_rows_with_economics":
                economics_rows,

            "unique_final_vessels":
                final_candidates[
                    "imo"
                ].nunique(),

            "unique_final_routes":
                final_candidates[
                    "route_id"
                ].nunique(),

            "unique_final_departure_dates":
                final_candidates[
                    "departure_date"
                ].nunique(),

            "unique_final_scenarios":
                final_candidates[
                    "scenario"
                ].nunique(),

            "api_calls_myshiptracking":
                0,

            "myshiptracking_credits_consumed":
                0,

            "oilpriceapi_calls":
                0,

            "status":
                "DEPARTURE_DATE_FEASIBILITY_READY",
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
        "LOCAL_ONLY",

    "planning_window": {
        "start":
            START_DATE.strftime(
                "%Y-%m-%d"
            ),

        "end":
            END_DATE.strftime(
                "%Y-%m-%d"
            ),

        "departure_dates":
            len(DEPARTURE_DATES),
    },

    "inputs": {
        "vessel_candidates":
            str(
                VESSEL_FILE
            ),

        "route_master":
            str(
                ROUTE_FILE
            ),

        "economics":
            str(
                ECONOMICS_FILE
            ),
    },

    "outputs": {
        "all_dates":
            str(
                ALL_FILE
            ),

        "optimizer_candidates":
            str(
                OPTIMIZER_FILE
            ),

        "summary":
            str(
                SUMMARY_FILE
            ),

        "quality":
            str(
                QUALITY_FILE
            ),

        "vessel_route_date_summary":
            str(
                VRD_SUMMARY_FILE
            ),
    },

    "statistics": {
        "vessel_candidates":
            len(vessels),

        "economic_pairs":
            len(economic_pairs),

        "physical_pairs":
            len(pairs),

        "all_date_rows":
            all_rows,

        "feasible_date_rows":
            feasible_rows,

        "final_date_scenario_rows":
            final_rows,

        "unique_vessels":
            final_candidates[
                "imo"
            ].nunique(),

        "unique_routes":
            final_candidates[
                "route_id"
            ].nunique(),

        "unique_departure_dates":
            final_candidates[
                "departure_date"
            ].nunique(),

        "unique_scenarios":
            final_candidates[
                "scenario"
            ].nunique(),
    },

    "physical_logic": {
        "reposition_distance":
            "great-circle haversine nautical miles",

        "reposition_time":
            "reposition_distance / route_speed",

        "reposition_buffer_hours":
            REPOSITION_BUFFER_HOURS,

        "sea_time":
            "route_distance / route_speed",

        "eta":
            "planned departure + sea_time + port_days",
    },

    "interpretation": [
        "Departure date is a planning decision.",
        "AIS does not prove commercial charter availability.",
        "A feasible row means the vessel can physically reach the loading origin.",
        "Route master provides route distance, speed and port days.",
        "Step 50C provides scenario economics.",
        "No MyShipTracking API calls were made.",
        "No MyShipTracking credits were consumed.",
        "No OilPriceAPI calls were made.",
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
# FINAL
# =============================================================================

print()
print("=" * 80)
print("STEP 51A SUMMARY")
print("=" * 80)
print()

print(
    "Planning dates:",
    len(DEPARTURE_DATES)
)

print(
    "Vessel candidates:",
    len(vessels)
)

print(
    "Economic vessel-route pairs:",
    len(economic_pairs)
)

print(
    "Physical vessel-route pairs:",
    len(pairs)
)

print(
    "All vessel-route-date rows:",
    all_rows
)

print(
    "Feasible vessel-route-date rows:",
    feasible_rows
)

print(
    "Not reachable date rows:",
    not_reachable_rows
)

print(
    "Final date-scenario rows:",
    final_rows
)

print(
    "Rows with economics:",
    economics_rows
)

print(
    "Final unique vessels:",
    final_candidates[
        "imo"
    ].nunique()
)

print(
    "Final unique routes:",
    final_candidates[
        "route_id"
    ].nunique()
)

print(
    "Final unique departure dates:",
    final_candidates[
        "departure_date"
    ].nunique()
)

print(
    "Final unique scenarios:",
    final_candidates[
        "scenario"
    ].nunique()
)

print()
print(
    "MyShipTracking API calls:",
    0
)

print(
    "MyShipTracking credits:",
    0
)

print(
    "OilPriceAPI calls:",
    0
)

print()
print("=" * 80)
print("SAVED")
print("=" * 80)
print()

print(
    ALL_FILE
)

print(
    OPTIMIZER_FILE
)

print(
    SUMMARY_FILE
)

print(
    QUALITY_FILE
)

print(
    VRD_SUMMARY_FILE
)

print(
    REPORT_FILE
)

print()
print("=" * 80)
print("STEP 51A COMPLETE")
print("=" * 80)
