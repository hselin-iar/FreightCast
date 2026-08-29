#!/usr/bin/env python3

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

PROCESSED = ROOT / "data" / "processed"
OUTPUTS = ROOT / "outputs"

LIVE_FILE = (
    PROCESSED
    / "step50b_live_bunker_economics.csv"
)

SCENARIO_FILE = (
    PROCESSED
    / "step50b_live_bunker_scenarios.csv"
)

REFERENCE_FILE = (
    PROCESSED
    / "step19b_route_scenario_economics.csv"
)

VALIDATED_FILE = (
    PROCESSED
    / "step50c_validated_scenarios.csv"
)

OPTIMIZER_FILE = (
    PROCESSED
    / "step50c_optimizer_economics.csv"
)

MATRIX_FILE = (
    OUTPUTS
    / "step50c_route_scenario_matrix.csv"
)

PROFIT_SUMMARY_FILE = (
    OUTPUTS
    / "step50c_candidate_profit_summary.csv"
)

SUMMARY_FILE = (
    OUTPUTS
    / "step50c_scenario_summary.csv"
)

QUALITY_FILE = (
    OUTPUTS
    / "step50c_scenario_quality.csv"
)

REPORT_FILE = (
    OUTPUTS
    / "step50c_report.json"
)


# =============================================================================
# SETTINGS
# =============================================================================

EXPECTED_SCENARIOS = [
    "bear",
    "base",
    "bull",
]

SCENARIO_ORDER = {
    "bear": 0,
    "base": 1,
    "bull": 2,
}


# =============================================================================
# HELPERS
# =============================================================================

def now_utc():
    return pd.Timestamp.now(
        tz="UTC"
    ).isoformat()


def normalize_route_id(value):

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


def normalize_scenario(value):

    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except Exception:
        pass

    s = (
        str(value)
        .strip()
        .lower()
        .replace("_", "")
        .replace("-", "")
        .replace(" ", "")
    )

    mapping = {
        "bear": "bear",
        "base": "base",
        "bull": "bull",
        "bearcase": "bear",
        "basecase": "base",
        "bullcase": "bull",
    }

    return mapping.get(
        s,
        s if s else None,
    )


def numeric_series(series):

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
            "\n".join(missing)
        )


# =============================================================================
# START
# =============================================================================

print()
print("=" * 80)
print(
    "STEP 50C - VALIDATE BEAR / BASE / BULL SCENARIOS"
)
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
    LIVE_FILE,
    SCENARIO_FILE,
]:

    if not path.exists():

        raise FileNotFoundError(
            str(path)
        )


# =============================================================================
# LOAD
# =============================================================================

print("=" * 80)
print("1/8 - LOADING DATA")
print("=" * 80)

live = pd.read_csv(
    LIVE_FILE
)

scenario_data = pd.read_csv(
    SCENARIO_FILE
)

print(
    "Live economics rows:",
    len(live)
)

print(
    "Scenario rows:",
    len(scenario_data)
)


# =============================================================================
# VALIDATE ACTUAL STEP 50B LIVE SCHEMA
# =============================================================================

require_columns(
    live,
    [
        "imo",
        "vessel_name",
        "route_id",
        "origin",
        "destination",
        "live_bunker_cost_usd",
        "opex_cost_usd",
        "other_voyage_cost_usd",
        "live_total_voyage_cost_usd",
    ],
    "Step 50B live economics",
)


# =============================================================================
# VALIDATE ACTUAL STEP 50B SCENARIO SCHEMA
# =============================================================================

require_columns(
    scenario_data,
    [
        "imo",
        "vessel_name",
        "route_id",
        "origin",
        "destination",
        "scenario",
        "freight_rate_usd_per_mt",
        "cargo_quantity_mt",
        "freight_revenue_usd",
        "bunker_price_usd_per_mt",
        "bunker_fuel_grade",
        "bunker_market_reference",
        "bunker_cost_usd",
        "opex_cost_usd",
        "other_voyage_cost_usd",
        "total_voyage_cost_usd",
        "estimated_profit_usd",
    ],
    "Step 50B scenario data",
)


# =============================================================================
# NORMALIZE
# =============================================================================

print()
print("=" * 80)
print("2/8 - NORMALIZING IDENTIFIERS")
print("=" * 80)

live[
    "route_id"
] = (
    live[
        "route_id"
    ]
    .apply(
        normalize_route_id
    )
)

scenario_data[
    "route_id"
] = (
    scenario_data[
        "route_id"
    ]
    .apply(
        normalize_route_id
    )
)

scenario_data[
    "scenario"
] = (
    scenario_data[
        "scenario"
    ]
    .apply(
        normalize_scenario
    )
)


for column in [
    "freight_rate_usd_per_mt",
    "cargo_quantity_mt",
    "freight_revenue_usd",
    "bunker_price_usd_per_mt",
    "bunker_cost_usd",
    "opex_cost_usd",
    "other_voyage_cost_usd",
    "total_voyage_cost_usd",
    "estimated_profit_usd",
]:

    scenario_data[
        column
    ] = numeric_series(
        scenario_data[
            column
        ]
    )


# =============================================================================
# SCENARIO NAME VALIDATION
# =============================================================================

print()
print("=" * 80)
print("3/8 - CHECKING SCENARIO NAMES")
print("=" * 80)

scenario_names = sorted(
    scenario_data[
        "scenario"
    ]
    .dropna()
    .unique()
    .tolist()
)

print(
    "Scenario names found:",
    scenario_names
)

unknown_scenarios = [
    name
    for name in scenario_names
    if name not in EXPECTED_SCENARIOS
]

print(
    "Unexpected scenarios:",
    unknown_scenarios
)


validated = scenario_data[
    scenario_data[
        "scenario"
    ].isin(
        EXPECTED_SCENARIOS
    )
].copy()


# =============================================================================
# DUPLICATES
# =============================================================================

print()
print("=" * 80)
print("4/8 - CHECKING DUPLICATES")
print("=" * 80)

duplicate_keys = [
    "imo",
    "route_id",
    "scenario",
]

duplicate_mask = (
    validated
    .duplicated(
        subset=duplicate_keys,
        keep=False,
    )
)

duplicate_rows = int(
    duplicate_mask.sum()
)

print(
    "Duplicate scenario rows:",
    duplicate_rows
)

validated[
    "duplicate_scenario_row"
] = duplicate_mask

validated = (
    validated
    .sort_values(
        duplicate_keys
    )
    .drop_duplicates(
        subset=duplicate_keys,
        keep="first",
    )
    .reset_index(
        drop=True
    )
)


# =============================================================================
# COVERAGE
# =============================================================================

print()
print("=" * 80)
print("5/8 - CHECKING BEAR / BASE / BULL COVERAGE")
print("=" * 80)

coverage_rows = []

for route_id, group in validated.groupby(
    "route_id"
):

    present = set(
        group[
            "scenario"
        ]
        .dropna()
        .tolist()
    )

    coverage_rows.append(
        {
            "route_id":
                route_id,

            "has_bear":
                "bear" in present,

            "has_base":
                "base" in present,

            "has_bull":
                "bull" in present,

            "complete_three_scenarios":
                (
                    "bear" in present
                    and
                    "base" in present
                    and
                    "bull" in present
                ),
        }
    )


coverage = pd.DataFrame(
    coverage_rows
)

print(
    coverage.to_string(
        index=False
    )
)


# =============================================================================
# RATE ORDERING
# =============================================================================

print()
print("=" * 80)
print("6/8 - CHECKING FREIGHT-RATE ORDERING")
print("=" * 80)

rate_rows = []

for route_id, group in validated.groupby(
    "route_id"
):

    rate_map = {}

    for scenario_name in EXPECTED_SCENARIOS:

        subset = group[
            group[
                "scenario"
            ]
            ==
            scenario_name
        ]

        if subset.empty:

            rate_map[
                scenario_name
            ] = np.nan

        else:

            rate_map[
                scenario_name
            ] = float(
                subset.iloc[0][
                    "freight_rate_usd_per_mt"
                ]
            )

    bear = rate_map["bear"]
    base = rate_map["base"]
    bull = rate_map["bull"]

    if (
        pd.isna(bear)
        or
        pd.isna(base)
        or
        pd.isna(bull)
    ):

        order = "INCOMPLETE"

    elif (
        bear <= base
        and
        base <= bull
    ):

        if (
            bear == base
            and
            base == bull
        ):

            order = "ALL_EQUAL"

        else:

            order = "VALID"

    else:

        order = "INVALID"

    rate_rows.append(
        {
            "route_id":
                route_id,

            "bear_rate":
                bear,

            "base_rate":
                base,

            "bull_rate":
                bull,

            "rate_order":
                order,
        }
    )


rate_check = pd.DataFrame(
    rate_rows
)

print(
    rate_check.to_string(
        index=False
    )
)


# =============================================================================
# JOIN LIVE BUNKER COST
# =============================================================================

print()
print("=" * 80)
print("7/8 - REBUILDING SCENARIO PROFIT WITH LIVE BUNKER")
print("=" * 80)

# IMPORTANT:
# Actual Step 50B column is:
#
#     live_bunker_cost_usd
#
# and timestamp is:
#
#     bunker_updated_at
#
# NOT live_bunker_updated_at.

live_columns = [
    "imo",
    "route_id",
    "live_bunker_cost_usd",
    "opex_cost_usd",
    "other_voyage_cost_usd",
    "live_total_voyage_cost_usd",
    "live_bunker_price_usd_per_mt",
    "bunker_market_reference",
    "bunker_updated_at",
]

live_columns = [
    c
    for c in live_columns
    if c in live.columns
]

live_lookup = (
    live[
        live_columns
    ]
    .drop_duplicates(
        subset=[
            "imo",
            "route_id",
        ],
        keep="last",
    )
)


scenario_live = validated.merge(
    live_lookup,
    on=[
        "imo",
        "route_id",
    ],
    how="left",
    suffixes=(
        "",
        "_live",
    ),
    indicator=True,
)


scenario_live[
    "live_cost_joined"
] = (
    scenario_live[
        "_merge"
    ]
    ==
    "both"
)


scenario_live = (
    scenario_live
    .drop(
        columns=[
            "_merge"
        ]
    )
)


# =============================================================================
# HANDLE COLUMN COLLISIONS
# =============================================================================

# scenario file already has:
# bunker_cost_usd
# opex_cost_usd
# other_voyage_cost_usd
# total_voyage_cost_usd
#
# live file has:
# live_bunker_cost_usd
# opex_cost_usd
# other_voyage_cost_usd
# live_total_voyage_cost_usd
#
# Pandas therefore keeps the scenario versions unchanged and creates
# *_live only for overlapping names.

if "live_total_voyage_cost_usd" not in scenario_live.columns:

    raise RuntimeError(
        "live_total_voyage_cost_usd was not preserved after merge."
    )


# =============================================================================
# REBUILD LIVE SCENARIO REVENUE
# =============================================================================

scenario_live[
    "live_scenario_revenue_usd"
] = (
    scenario_live[
        "freight_rate_usd_per_mt"
    ]
    *
    scenario_live[
        "cargo_quantity_mt"
    ]
)


# =============================================================================
# REBUILD LIVE SCENARIO PROFIT
# =============================================================================

scenario_live[
    "live_scenario_profit_usd"
] = (
    scenario_live[
        "live_scenario_revenue_usd"
    ]
    -
    scenario_live[
        "live_total_voyage_cost_usd"
    ]
)


# =============================================================================
# COMPARE WITH STEP 50B SCENARIO PROFIT
# =============================================================================

scenario_live[
    "profit_rebuild_delta_usd"
] = (
    scenario_live[
        "live_scenario_profit_usd"
    ]
    -
    scenario_live[
        "estimated_profit_usd"
    ]
)


# =============================================================================
# PROFITABILITY
# =============================================================================

scenario_live[
    "profitable"
] = (
    scenario_live[
        "live_scenario_profit_usd"
    ]
    >
    0
)


scenario_live[
    "loss_making"
] = (
    scenario_live[
        "live_scenario_profit_usd"
    ]
    <
    0
)


# =============================================================================
# VESSEL × ROUTE PROFIT SUMMARY
# =============================================================================

profit_summary = (
    scenario_live
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
        scenario_count=(
            "scenario",
            "count",
        ),

        minimum_profit_usd=(
            "live_scenario_profit_usd",
            "min",
        ),

        maximum_profit_usd=(
            "live_scenario_profit_usd",
            "max",
        ),

        profitable_scenarios=(
            "profitable",
            "sum",
        ),

        loss_scenarios=(
            "loss_making",
            "sum",
        ),
    )
    .reset_index()
)


# Base-case profit.

base_profit = (
    scenario_live[
        scenario_live[
            "scenario"
        ]
        ==
        "base"
    ][
        [
            "imo",
            "route_id",
            "live_scenario_profit_usd",
        ]
    ]
    .drop_duplicates(
        subset=[
            "imo",
            "route_id",
        ]
    )
    .rename(
        columns={
            "live_scenario_profit_usd":
                "base_profit_usd",
        }
    )
)


profit_summary = profit_summary.merge(
    base_profit,
    on=[
        "imo",
        "route_id",
    ],
    how="left",
)


profit_summary[
    "economic_status"
] = "MIXED"


profit_summary.loc[
    (
        profit_summary[
            "scenario_count"
        ]
        ==
        profit_summary[
            "profitable_scenarios"
        ]
    ),
    "economic_status",
] = "PROFITABLE_ALL_SCENARIOS"


profit_summary.loc[
    (
        profit_summary[
            "scenario_count"
        ]
        ==
        profit_summary[
            "loss_scenarios"
        ]
    ),
    "economic_status",
] = "LOSS_ALL_SCENARIOS"


# =============================================================================
# OPTIMIZER ECONOMICS
# =============================================================================

optimizer = scenario_live[
    [
        "imo",
        "vessel_name",
        "route_id",
        "origin",
        "destination",
        "scenario",
        "freight_rate_usd_per_mt",
        "cargo_quantity_mt",
        "live_scenario_revenue_usd",
        "live_bunker_price_usd_per_mt",
        "bunker_market_reference",
        "bunker_updated_at",
        "live_bunker_cost_usd",
        "live_total_voyage_cost_usd",
        "live_scenario_profit_usd",
        "profitable",
        "loss_making",
        "live_cost_joined",
    ]
].copy()


optimizer[
    "scenario_code"
] = optimizer[
    "scenario"
].map(
    SCENARIO_ORDER
)


optimizer[
    "candidate_key"
] = (
    optimizer[
        "imo"
    ].astype(str)
    +
    "_R"
    +
    optimizer[
        "route_id"
    ].astype(str)
    +
    "_"
    +
    optimizer[
        "scenario"
    ].astype(str)
)


# =============================================================================
# ROUTE SCENARIO MATRIX
# =============================================================================

matrix = (
    validated[
        [
            "route_id",
            "scenario",
            "freight_rate_usd_per_mt",
        ]
    ]
    .drop_duplicates()
    .pivot(
        index="route_id",
        columns="scenario",
        values="freight_rate_usd_per_mt",
    )
    .reset_index()
)


for scenario_name in EXPECTED_SCENARIOS:

    if scenario_name not in matrix.columns:

        matrix[
            scenario_name
        ] = np.nan


matrix = matrix[
    [
        "route_id",
        "bear",
        "base",
        "bull",
    ]
]


matrix = matrix.rename(
    columns={
        "bear":
            "bear_freight_rate_usd_per_mt",

        "base":
            "base_freight_rate_usd_per_mt",

        "bull":
            "bull_freight_rate_usd_per_mt",
    }
)


matrix = matrix.merge(
    rate_check,
    on="route_id",
    how="left",
)


# =============================================================================
# SAVE
# =============================================================================

validated.to_csv(
    VALIDATED_FILE,
    index=False,
)

optimizer.to_csv(
    OPTIMIZER_FILE,
    index=False,
)

matrix.to_csv(
    MATRIX_FILE,
    index=False,
)

profit_summary.to_csv(
    PROFIT_SUMMARY_FILE,
    index=False,
)


# =============================================================================
# METRICS
# =============================================================================

complete_routes = int(
    coverage[
        "complete_three_scenarios"
    ]
    .sum()
)

incomplete_routes = int(
    (
        ~coverage[
            "complete_three_scenarios"
        ]
    )
    .sum()
)

valid_routes = int(
    (
        rate_check[
            "rate_order"
        ]
        ==
        "VALID"
    ).sum()
)

invalid_routes = int(
    (
        rate_check[
            "rate_order"
        ]
        ==
        "INVALID"
    ).sum()
)

equal_routes = int(
    (
        rate_check[
            "rate_order"
        ]
        ==
        "ALL_EQUAL"
    ).sum()
)

incomplete_rate_routes = int(
    (
        rate_check[
            "rate_order"
        ]
        ==
        "INCOMPLETE"
    ).sum()
)

joined_rows = int(
    scenario_live[
        "live_cost_joined"
    ]
    .fillna(False)
    .sum()
)

profitable_rows = int(
    optimizer[
        "profitable"
    ]
    .fillna(False)
    .sum()
)

loss_rows = int(
    optimizer[
        "loss_making"
    ]
    .fillna(False)
    .sum()
)

all_profitable_pairs = int(
    (
        profit_summary[
            "economic_status"
        ]
        ==
        "PROFITABLE_ALL_SCENARIOS"
    )
    .sum()
)

mixed_pairs = int(
    (
        profit_summary[
            "economic_status"
        ]
        ==
        "MIXED"
    )
    .sum()
)

all_loss_pairs = int(
    (
        profit_summary[
            "economic_status"
        ]
        ==
        "LOSS_ALL_SCENARIOS"
    )
    .sum()
)


# =============================================================================
# QUALITY OUTPUT
# =============================================================================

quality = pd.DataFrame(
    [
        {
            "metric":
                "live_economics_rows",
            "value":
                len(live),
        },

        {
            "metric":
                "raw_scenario_rows",
            "value":
                len(scenario_data),
        },

        {
            "metric":
                "validated_scenario_rows",
            "value":
                len(validated),
        },

        {
            "metric":
                "unique_vessels",
            "value":
                validated[
                    "imo"
                ].nunique(),
        },

        {
            "metric":
                "unique_routes",
            "value":
                validated[
                    "route_id"
                ].nunique(),
        },

        {
            "metric":
                "duplicate_scenario_rows",
            "value":
                duplicate_rows,
        },

        {
            "metric":
                "unexpected_scenarios",
            "value":
                len(unknown_scenarios),
        },

        {
            "metric":
                "complete_three_scenario_routes",
            "value":
                complete_routes,
        },

        {
            "metric":
                "incomplete_routes",
            "value":
                incomplete_routes,
        },

        {
            "metric":
                "valid_rate_order_routes",
            "value":
                valid_routes,
        },

        {
            "metric":
                "invalid_rate_order_routes",
            "value":
                invalid_routes,
        },

        {
            "metric":
                "all_equal_rate_routes",
            "value":
                equal_routes,
        },

        {
            "metric":
                "incomplete_rate_routes",
            "value":
                incomplete_rate_routes,
        },

        {
            "metric":
                "scenario_rows_joined_to_live_cost",
            "value":
                joined_rows,
        },

        {
            "metric":
                "optimizer_rows",
            "value":
                len(optimizer),
        },

        {
            "metric":
                "profitable_scenario_rows",
            "value":
                profitable_rows,
        },

        {
            "metric":
                "loss_making_scenario_rows",
            "value":
                loss_rows,
        },

        {
            "metric":
                "all_scenario_profitable_pairs",
            "value":
                all_profitable_pairs,
        },

        {
            "metric":
                "mixed_vessel_route_pairs",
            "value":
                mixed_pairs,
        },

        {
            "metric":
                "all_scenario_loss_pairs",
            "value":
                all_loss_pairs,
        },

        {
            "metric":
                "myshiptracking_api_calls",
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

            "live_economics_rows":
                len(live),

            "raw_scenario_rows":
                len(scenario_data),

            "validated_scenario_rows":
                len(validated),

            "unique_vessels":
                validated[
                    "imo"
                ].nunique(),

            "unique_routes":
                validated[
                    "route_id"
                ].nunique(),

            "duplicate_scenario_rows":
                duplicate_rows,

            "complete_three_scenario_routes":
                complete_routes,

            "incomplete_routes":
                incomplete_routes,

            "valid_rate_order_routes":
                valid_routes,

            "invalid_rate_order_routes":
                invalid_routes,

            "optimizer_scenario_rows":
                len(optimizer),

            "profitable_scenario_rows":
                profitable_rows,

            "loss_making_scenario_rows":
                loss_rows,

            "all_scenario_profitable_pairs":
                all_profitable_pairs,

            "mixed_vessel_route_pairs":
                mixed_pairs,

            "all_scenario_loss_pairs":
                all_loss_pairs,

            "live_bunker_price_usd_per_mt":
                (
                    live[
                        "live_bunker_price_usd_per_mt"
                    ]
                    .dropna()
                    .iloc[0]
                    if
                    "live_bunker_price_usd_per_mt"
                    in live.columns
                    and
                    live[
                        "live_bunker_price_usd_per_mt"
                    ]
                    .notna()
                    .any()
                    else
                    np.nan
                ),

            "bunker_market_reference":
                (
                    live[
                        "bunker_market_reference"
                    ]
                    .dropna()
                    .iloc[0]
                    if
                    "bunker_market_reference"
                    in live.columns
                    and
                    live[
                        "bunker_market_reference"
                    ]
                    .notna()
                    .any()
                    else
                    None
                ),

            "myshiptracking_api_calls":
                0,

            "myshiptracking_credits_consumed":
                0,

            "oilpriceapi_calls":
                0,

            "status":
                "SCENARIOS_VALIDATED",
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

    "statistics": {
        "live_rows":
            len(live),

        "raw_scenario_rows":
            len(scenario_data),

        "validated_rows":
            len(validated),

        "unique_vessels":
            validated[
                "imo"
            ].nunique(),

        "unique_routes":
            validated[
                "route_id"
            ].nunique(),

        "duplicate_rows":
            duplicate_rows,

        "complete_routes":
            complete_routes,

        "incomplete_routes":
            incomplete_routes,

        "valid_rate_order_routes":
            valid_routes,

        "invalid_rate_order_routes":
            invalid_routes,

        "optimizer_rows":
            len(optimizer),

        "profitable_rows":
            profitable_rows,

        "loss_rows":
            loss_rows,

        "all_profitable_pairs":
            all_profitable_pairs,

        "mixed_pairs":
            mixed_pairs,

        "all_loss_pairs":
            all_loss_pairs,
    },

    "bunker": {
        "price_usd_per_mt":
            (
                live[
                    "live_bunker_price_usd_per_mt"
                ]
                .dropna()
                .iloc[0]
                if
                "live_bunker_price_usd_per_mt"
                in live.columns
                and
                live[
                    "live_bunker_price_usd_per_mt"
                ]
                .notna()
                .any()
                else
                None
            ),

        "reference":
            (
                live[
                    "bunker_market_reference"
                ]
                .dropna()
                .iloc[0]
                if
                "bunker_market_reference"
                in live.columns
                and
                live[
                    "bunker_market_reference"
                ]
                .notna()
                .any()
                else
                None
            ),
    },

    "important": [
        "Actual Step 50B scenario rate column is freight_rate_usd_per_mt.",
        "Actual Step 50B bunker timestamp column is bunker_updated_at.",
        "Existing Bear/Base/Bull freight scenarios are validated, not invented.",
        "Live bunker cost is reused from Step 50B.",
        "No MyShipTracking API calls were made.",
        "No MyShipTracking credits were consumed.",
        "No OilPriceAPI calls were made.",
        "The MILP is not run here.",
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
print("STEP 50C SUMMARY")
print("=" * 80)
print()

print(
    "Live economics rows:",
    len(live)
)

print(
    "Raw scenario rows:",
    len(scenario_data)
)

print(
    "Validated scenario rows:",
    len(validated)
)

print(
    "Unique vessels:",
    validated[
        "imo"
    ].nunique()
)

print(
    "Unique routes:",
    validated[
        "route_id"
    ].nunique()
)

print(
    "Duplicate scenario rows:",
    duplicate_rows
)

print(
    "Complete 3-scenario routes:",
    complete_routes
)

print(
    "Incomplete routes:",
    incomplete_routes
)

print(
    "Valid rate-order routes:",
    valid_routes
)

print(
    "Invalid rate-order routes:",
    invalid_routes
)

print(
    "Optimizer scenario rows:",
    len(optimizer)
)

print(
    "Profitable scenario rows:",
    profitable_rows
)

print(
    "Loss-making scenario rows:",
    loss_rows
)

print(
    "All-scenario-profitable pairs:",
    all_profitable_pairs
)

print(
    "Mixed vessel-route pairs:",
    mixed_pairs
)

print(
    "All-scenario-loss pairs:",
    all_loss_pairs
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
    VALIDATED_FILE
)

print(
    OPTIMIZER_FILE
)

print(
    MATRIX_FILE
)

print(
    PROFIT_SUMMARY_FILE
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
print("STEP 50C COMPLETE")
print("=" * 80)
