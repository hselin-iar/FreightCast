#!/usr/bin/env python3

"""
STEP 50A - OILPRICEAPI BUNKER INGESTION

Purpose
-------
Fetch the current VLSFO bunker price from OilPriceAPI and create a
normalized bunker-price dataset for the freight optimization pipeline.

IMPORTANT
---------
- Uses OILPRICEAPI only.
- Does NOT call MyShipTracking.
- Does NOT modify the optimizer.
- Does NOT overwrite existing route economics.
- Static/project bunker assumptions remain available as fallback.
- Raw API response is archived.
- API key is never printed.

Current tested endpoint
-----------------------
GET:

    https://api.oilpriceapi.com/v1/prices/latest?by_code=VLSFO_USD

Authentication:

    Authorization: Token <API KEY>

Expected result:
    VLSFO_SGSIN_USD
    price
    USD
    metric_ton
    timestamp
    source
    data_status
    stale
    synthetic

Outputs
-------
data/raw/bunker/oilpriceapi/
data/processed/step50a_bunker_current.csv
data/processed/step50a_bunker_reference.csv

outputs/step50a_bunker_summary.csv
outputs/step50a_bunker_quality.csv
outputs/step50a_bunker_report.json
"""


from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests


# =============================================================================
# PATHS
# =============================================================================

ROOT = Path(
    __file__
).resolve().parent


RAW_DIR = (
    ROOT
    / "data"
    / "raw"
    / "bunker"
    / "oilpriceapi"
)


PROCESSED_DIR = (
    ROOT
    / "data"
    / "processed"
)


OUTPUT_DIR = (
    ROOT
    / "outputs"
)


CURRENT_FILE = (
    PROCESSED_DIR
    / "step50a_bunker_current.csv"
)


REFERENCE_FILE = (
    PROCESSED_DIR
    / "step50a_bunker_reference.csv"
)


SUMMARY_FILE = (
    OUTPUT_DIR
    / "step50a_bunker_summary.csv"
)


QUALITY_FILE = (
    OUTPUT_DIR
    / "step50a_bunker_quality.csv"
)


REPORT_FILE = (
    OUTPUT_DIR
    / "step50a_bunker_report.json"
)


# =============================================================================
# API CONFIG
# =============================================================================

API_BASE = (
    "https://api.oilpriceapi.com/v1"
)


API_KEY = os.getenv(
    "OILPRICEAPI_KEY"
)


ENDPOINT = (
    "/prices/latest"
)


# We use the code that successfully returned the Singapore VLSFO benchmark
# in your test.

PRICE_CODE = (
    "VLSFO_USD"
)


TIMEOUT_SECONDS = 30


# =============================================================================
# QUALITY / FRESHNESS POLICY
# =============================================================================

# OilPriceAPI itself gives an expected freshness window.
# We retain that information instead of assuming the API is always current.

MAX_ACCEPTABLE_AGE_HOURS = 6.0


# =============================================================================
# HELPERS
# =============================================================================

def utc_now():
    return datetime.now(
        timezone.utc
    )


def utc_iso():
    return utc_now().isoformat()


def timestamp_name():
    return utc_now().strftime(
        "%Y%m%dT%H%M%SZ"
    )


def ensure_directories():

    RAW_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    PROCESSED_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


def parse_timestamp(
    value
):
    """
    Convert API timestamps to UTC pandas Timestamp.
    """

    if value is None:
        return pd.NaT

    try:

        ts = pd.Timestamp(
            value
        )

        if ts.tzinfo is None:

            ts = ts.tz_localize(
                "UTC"
            )

        else:

            ts = ts.tz_convert(
                "UTC"
            )

        return ts

    except Exception:

        return pd.NaT


def get_age_hours(
    timestamp
):

    ts = parse_timestamp(
        timestamp
    )

    if pd.isna(ts):

        return None

    now = pd.Timestamp.now(
        tz="UTC"
    )

    age_seconds = (
        now - ts
    ).total_seconds()

    return max(
        0.0,
        age_seconds / 3600.0
    )


def save_json(
    payload,
    path
):

    with path.open(
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            payload,
            f,
            indent=2,
            ensure_ascii=False,
            default=str,
        )


def safe_float(
    value
):

    try:

        if value is None:

            return None

        return float(
            value
        )

    except Exception:

        return None


# =============================================================================
# API CALL
# =============================================================================

def fetch_bunker_price():

    headers = {
        "Authorization":
            f"Token {API_KEY}",

        "Accept":
            "application/json",
    }

    params = {
        "by_code":
            PRICE_CODE,
    }

    response = requests.get(
        f"{API_BASE}{ENDPOINT}",
        headers=headers,
        params=params,
        timeout=TIMEOUT_SECONDS,
    )

    payload = response.json()

    return (
        response,
        payload,
    )


# =============================================================================
# NORMALIZATION
# =============================================================================

def normalize_price_payload(
    payload
):

    data = payload.get(
        "data"
    )

    if not isinstance(
        data,
        dict,
    ):

        raise RuntimeError(
            "OilPriceAPI response contains no valid data object."
        )

    code = data.get(
        "code"
    )

    price = safe_float(
        data.get(
            "price"
        )
    )

    currency = data.get(
        "currency"
    )

    unit = data.get(
        "unit"
    )

    source = data.get(
        "source"
    )

    source_type = data.get(
        "type"
    )

    created_at = data.get(
        "created_at"
    )

    updated_at = data.get(
        "updated_at"
    )

    as_of = data.get(
        "as_of"
    )

    collected_at = data.get(
        "collected_at"
    )

    data_status = data.get(
        "data_status"
    )

    stale = data.get(
        "stale"
    )

    synthetic = data.get(
        "synthetic"
    )

    formatted = data.get(
        "formatted"
    )

    changes = data.get(
        "changes"
    )

    freshness_obj = data.get(
        "freshness"
    )

    if not isinstance(
        freshness_obj,
        dict,
    ):

        freshness_obj = {}

    api_freshness_status = freshness_obj.get(
        "status"
    )

    api_age_seconds = safe_float(
        freshness_obj.get(
            "age_seconds"
        )
    )

    expected_max_age_seconds = safe_float(
        freshness_obj.get(
            "expected_max_age_seconds"
        )
    )

    circuit_breaker_open = freshness_obj.get(
        "circuit_breaker_open"
    )

    if api_age_seconds is not None:

        observed_age_hours = (
            api_age_seconds
            /
            3600.0
        )

    else:

        timestamp_for_age = (
            updated_at
            or
            as_of
            or
            collected_at
            or
            created_at
        )

        observed_age_hours = get_age_hours(
            timestamp_for_age
        )

    # -------------------------------------------------------------------------
    # Strict project-level acceptance rule
    # -------------------------------------------------------------------------

    if (
        observed_age_hours is not None
        and
        observed_age_hours
        <=
        MAX_ACCEPTABLE_AGE_HOURS
    ):

        project_fresh = True

    else:

        project_fresh = False

    # API says stale explicitly -> never override that.

    if stale is True:

        project_fresh = False

    # Synthetic values are not accepted as production bunker observations.

    if synthetic is True:

        project_usable = False

    else:

        project_usable = (
            price is not None
            and
            currency == "USD"
            and
            unit == "metric_ton"
            and
            project_fresh
        )

    # -------------------------------------------------------------------------
    # Extract 24-hour movement
    # -------------------------------------------------------------------------

    change_24h = {}

    if isinstance(
        changes,
        dict,
    ):

        c24 = changes.get(
            "24h"
        )

        if isinstance(
            c24,
            dict,
        ):

            change_24h = c24

    return {
        "retrieved_at_utc":
            utc_iso(),

        "requested_code":
            PRICE_CODE,

        "returned_code":
            code,

        "fuel_grade":
            "VLSFO",

        "market_reference":
            "Singapore",

        "price_usd_per_metric_ton":
            price,

        "currency":
            currency,

        "unit":
            unit,

        "formatted_price":
            formatted,

        "source":
            source,

        "source_type":
            source_type,

        "created_at":
            created_at,

        "updated_at":
            updated_at,

        "as_of":
            as_of,

        "collected_at":
            collected_at,

        "data_status":
            data_status,

        "stale":
            stale,

        "synthetic":
            synthetic,

        "api_freshness_status":
            api_freshness_status,

        "api_age_seconds":
            api_age_seconds,

        "api_expected_max_age_seconds":
            expected_max_age_seconds,

        "observed_age_hours":
            observed_age_hours,

        "circuit_breaker_open":
            circuit_breaker_open,

        "project_fresh":
            project_fresh,

        "project_usable":
            project_usable,

        "change_24h_amount":
            safe_float(
                change_24h.get(
                    "amount"
                )
            ),

        "change_24h_percent":
            safe_float(
                change_24h.get(
                    "percent"
                )
            ),

        "previous_price":
            safe_float(
                change_24h.get(
                    "previous_price"
                )
            ),

        "previous_timestamp":
            change_24h.get(
                "previous_timestamp"
            ),

        "change_measured_at":
            change_24h.get(
                "measured_at"
            ),
    }


# =============================================================================
# MAIN
# =============================================================================

def main():

    print()
    print("=" * 80)
    print(
        "STEP 50A - OILPRICEAPI BUNKER INGESTION"
    )
    print("=" * 80)

    print()
    print(
        "API:",
        "OilPriceAPI",
    )

    print(
        "Fuel:",
        "VLSFO",
    )

    print(
        "Requested code:",
        PRICE_CODE,
    )

    if not API_KEY:

        raise RuntimeError(
            "\nOILPRICEAPI_KEY is not set.\n\n"
            "Run:\n\n"
            "export OILPRICEAPI_KEY='YOUR_API_KEY'\n"
        )

    ensure_directories()

    # =========================================================================
    # 1. FETCH
    # =========================================================================

    print()
    print("=" * 80)
    print(
        "1/5 - FETCH CURRENT VLSFO"
    )
    print("=" * 80)

    request_started = utc_iso()

    try:

        response, payload = (
            fetch_bunker_price()
        )

    except Exception as exc:

        raise RuntimeError(
            f"OilPriceAPI request failed: {exc}"
        )

    request_finished = utc_iso()

    print(
        "HTTP status:",
        response.status_code,
    )

    if response.status_code != 200:

        print()
        print(
            json.dumps(
                payload,
                indent=2,
            )
        )

        raise RuntimeError(
            f"OilPriceAPI returned HTTP "
            f"{response.status_code}"
        )

    # =========================================================================
    # 2. ARCHIVE RAW
    # =========================================================================

    print()
    print("=" * 80)
    print(
        "2/5 - ARCHIVE RAW RESPONSE"
    )
    print("=" * 80)

    raw_path = (
        RAW_DIR
        /
        (
            "oilpriceapi_vlsfo_"
            +
            timestamp_name()
            +
            ".json"
        )
    )

    save_json(
        {
            "request": {
                "endpoint":
                    f"{API_BASE}{ENDPOINT}",

                "params": {
                    "by_code":
                        PRICE_CODE,
                },

                "started_utc":
                    request_started,

                "finished_utc":
                    request_finished,
            },

            "response": payload,
        },
        raw_path,
    )

    print(
        "Raw response:",
        raw_path,
    )

    # =========================================================================
    # 3. NORMALIZE
    # =========================================================================

    print()
    print("=" * 80)
    print(
        "3/5 - NORMALIZE BUNKER DATA"
    )
    print("=" * 80)

    normalized = normalize_price_payload(
        payload
    )

    print(
        "Returned code:",
        normalized[
            "returned_code"
        ],
    )

    print(
        "Price:",
        normalized[
            "price_usd_per_metric_ton"
        ],
        "USD/MT",
    )

    print(
        "Updated:",
        normalized[
            "updated_at"
        ],
    )

    print(
        "Data status:",
        normalized[
            "data_status"
        ],
    )

    print(
        "Synthetic:",
        normalized[
            "synthetic"
        ],
    )

    print(
        "Stale:",
        normalized[
            "stale"
        ],
    )

    print(
        "Observed age hours:",
        normalized[
            "observed_age_hours"
        ],
    )

    print(
        "Project usable:",
        normalized[
            "project_usable"
        ],
    )

    # =========================================================================
    # 4. SAVE CURRENT
    # =========================================================================

    print()
    print("=" * 80)
    print(
        "4/5 - SAVE NORMALIZED CURRENT PRICE"
    )
    print("=" * 80)

    current_df = pd.DataFrame(
        [
            normalized
        ]
    )

    current_df.to_csv(
        CURRENT_FILE,
        index=False,
    )

    # =========================================================================
    # 5. APPEND REFERENCE HISTORY
    # =========================================================================

    print()
    print("=" * 80)
    print(
        "5/5 - UPDATE LOCAL BUNKER REFERENCE HISTORY"
    )
    print("=" * 80)

    current_row = current_df.copy()

    if REFERENCE_FILE.exists():

        try:

            reference_df = pd.read_csv(
                REFERENCE_FILE
            )

            reference_df = pd.concat(
                [
                    reference_df,
                    current_row,
                ],
                ignore_index=True,
            )

        except Exception:

            reference_df = current_row.copy()

    else:

        reference_df = current_row.copy()

    # Keep one row per retrieval timestamp.

    reference_df = (
        reference_df
        .drop_duplicates(
            subset=[
                "retrieved_at_utc",
                "returned_code",
                "price_usd_per_metric_ton",
            ],
            keep="last",
        )
        .reset_index(
            drop=True
        )
    )

    reference_df.to_csv(
        REFERENCE_FILE,
        index=False,
    )

    # =========================================================================
    # QUALITY
    # =========================================================================

    quality = pd.DataFrame(
        [
            {
                "metric":
                    "http_status",
                "value":
                    response.status_code,
            },

            {
                "metric":
                    "price_available",
                "value":
                    normalized[
                        "price_usd_per_metric_ton"
                    ]
                    is not None,
            },

            {
                "metric":
                    "currency_usd",
                "value":
                    normalized[
                        "currency"
                    ]
                    == "USD",
            },

            {
                "metric":
                    "metric_ton_unit",
                "value":
                    normalized[
                        "unit"
                    ]
                    == "metric_ton",
            },

            {
                "metric":
                    "api_current",
                "value":
                    normalized[
                        "data_status"
                    ]
                    == "current",
            },

            {
                "metric":
                    "not_stale",
                "value":
                    normalized[
                        "stale"
                    ]
                    is False,
            },

            {
                "metric":
                    "not_synthetic",
                "value":
                    normalized[
                        "synthetic"
                    ]
                    is False,
            },

            {
                "metric":
                    "project_fresh",
                "value":
                    normalized[
                        "project_fresh"
                    ],
            },

            {
                "metric":
                    "project_usable",
                "value":
                    normalized[
                        "project_usable"
                    ],
            },

            {
                "metric":
                    "api_calls",
                "value":
                    1,
            },

        ]
    )

    quality.to_csv(
        QUALITY_FILE,
        index=False,
    )

    # =========================================================================
    # SUMMARY
    # =========================================================================

    summary = pd.DataFrame(
        [
            {
                "generated_utc":
                    utc_iso(),

                "fuel_grade":
                    normalized[
                        "fuel_grade"
                    ],

                "market_reference":
                    normalized[
                        "market_reference"
                    ],

                "returned_code":
                    normalized[
                        "returned_code"
                    ],

                "price_usd_per_metric_ton":
                    normalized[
                        "price_usd_per_metric_ton"
                    ],

                "currency":
                    normalized[
                        "currency"
                    ],

                "unit":
                    normalized[
                        "unit"
                    ],

                "updated_at":
                    normalized[
                        "updated_at"
                    ],

                "observed_age_hours":
                    normalized[
                        "observed_age_hours"
                    ],

                "data_status":
                    normalized[
                        "data_status"
                    ],

                "stale":
                    normalized[
                        "stale"
                    ],

                "synthetic":
                    normalized[
                        "synthetic"
                    ],

                "project_usable":
                    normalized[
                        "project_usable"
                    ],

                "change_24h_amount":
                    normalized[
                        "change_24h_amount"
                    ],

                "change_24h_percent":
                    normalized[
                        "change_24h_percent"
                    ],

                "reference_history_rows":
                    len(
                        reference_df
                    ),

                "api_calls":
                    1,

                "status":
                    (
                        "BUNKER_PRICE_READY"
                        if normalized[
                            "project_usable"
                        ]
                        else
                        "BUNKER_PRICE_REJECTED"
                    ),
            }
        ]
    )

    summary.to_csv(
        SUMMARY_FILE,
        index=False,
    )

    # =========================================================================
    # REPORT
    # =========================================================================

    report = {
        "generated_utc":
            utc_iso(),

        "api":
            "OilPriceAPI",

        "api_calls":
            1,

        "fuel_grade":
            normalized[
                "fuel_grade"
            ],

        "market_reference":
            normalized[
                "market_reference"
            ],

        "requested_code":
            PRICE_CODE,

        "returned_code":
            normalized[
                "returned_code"
            ],

        "normalized":
            normalized,

        "quality_policy":
            {
                "max_project_age_hours":
                    MAX_ACCEPTABLE_AGE_HOURS,

                "requires_usd":
                    True,

                "requires_metric_ton":
                    True,

                "reject_synthetic":
                    True,

                "reject_stale":
                    True,

                "requires_current_api_status":
                    True,
            },

        "current_price_usable":
            normalized[
                "project_usable"
            ],

        "raw_response":
            str(
                raw_path
            ),

        "outputs":
            {
                "current":
                    str(
                        CURRENT_FILE
                    ),

                "reference":
                    str(
                        REFERENCE_FILE
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

        "important":
            [
                (
                    "The returned VLSFO value is treated "
                    "as the Singapore benchmark."
                ),

                (
                    "This script does not claim that the "
                    "price is a Gladstone, Richards Bay, "
                    "Vizag or Haldia supplier quote."
                ),

                (
                    "This script does not modify the "
                    "voyage economics engine."
                ),

                (
                    "This script does not replace the "
                    "existing bunker fallback."
                ),
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
            ensure_ascii=False,
            default=str,
        )

    # =========================================================================
    # FINAL
    # =========================================================================

    print()
    print("=" * 80)
    print(
        "STEP 50A COMPLETE"
    )
    print("=" * 80)

    print()
    print(
        "VLSFO:",
        normalized[
            "price_usd_per_metric_ton"
        ],
        "USD/MT"
    )

    print(
        "Reference:",
        normalized[
            "market_reference"
        ]
    )

    print(
        "Project usable:",
        normalized[
            "project_usable"
        ]
    )

    print(
        "API calls:",
        1
    )

    print()
    print("SAVED:")
    print(CURRENT_FILE)
    print(REFERENCE_FILE)
    print(SUMMARY_FILE)
    print(QUALITY_FILE)
    print(REPORT_FILE)
    print(raw_path)

    print()
    print(
        "NEXT: Do not modify the optimizer yet."
    )


if __name__ == "__main__":
    main()
