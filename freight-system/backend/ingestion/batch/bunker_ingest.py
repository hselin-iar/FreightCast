"""
ingestion/batch/bunker_ingest.py — VLSFO bunker price ingestion.

Primary source: OilPriceAPI live endpoint (OILPRICEAPI_VLSFO_URL)
Fallback:       data/raw/bunker_singapore.csv
Cadence:        daily (called by scheduler.py)

DOC3 §FEATURE: Data Ingestion Layer → bunker_ingest.py
DOC2 §5 v3 Final, handoff Step 50A
"""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from backend.config.constants import OILPRICEAPI_VLSFO_URL
from backend.ingestion.types import IngestResult
from backend.ingestion.validation import BUNKER_SCHEMA, validate

logger = logging.getLogger(__name__)

_FALLBACK_PATH = (
    Path(__file__).parent.parent.parent / "data" / "raw" / "bunker_singapore.csv"
)

# OilPriceAPI requires an API key header — read from env; empty key → skip live attempt
_API_KEY = __import__("os").environ.get("OILPRICEAPI_API_KEY", "")


def run() -> IngestResult:
    """
    Fetch, validate, and return bunker price data.

    Tries the live OilPriceAPI endpoint first; falls back to the CSV fixture.
    Fallback rows are tagged provenance="assumed"/stale in the alert list —
    never silently treated as fresh measured prices.
    """
    source_label = "oilpriceapi_vlsfo"
    is_fallback = False

    try:
        raw_df = _fetch_live()
        logger.info("Bunker: fetched live from OilPriceAPI.")
    except Exception as exc:
        logger.warning("Bunker live fetch failed (%s) — using fallback CSV.", exc)
        try:
            raw_df = _fetch_fallback()
        except Exception as fallback_exc:
            logger.error("Bunker fallback also failed: %s", fallback_exc)
            return IngestResult(
                source=source_label,
                rows_ingested=0,
                rows_rejected=0,
                alerts=[f"Live fetch error: {exc}", f"Fallback error: {fallback_exc}"],
            )
        is_fallback = True

    batch = validate(raw_df, BUNKER_SCHEMA)

    if batch.rejected:
        for r in batch.rejected:
            logger.warning("Bunker rejected row %d: %s", r.row_index, r.reason)

    alerts = batch.alerts[:]
    if is_fallback:
        stale_msg = (
            "provenance=assumed: bunker price sourced from fallback CSV — "
            "live OilPriceAPI endpoint was unreachable. Tag as stale/assumed."
        )
        alerts.append(stale_msg)
        logger.warning(stale_msg)

    logger.info(
        "Bunker ingest: %d clean, %d rejected, is_fallback=%s",
        len(batch.rows), len(batch.rejected), is_fallback,
    )
    return IngestResult(
        source=source_label,
        rows_ingested=len(batch.rows),
        rows_rejected=len(batch.rejected),
        alerts=alerts,
    )


def _fetch_live() -> pd.DataFrame:
    """
    Call OilPriceAPI and return a single-row DataFrame for today's price.
    Raises on any HTTP/parse error — caller falls back to CSV.
    """
    if not _API_KEY:
        raise RuntimeError("OILPRICEAPI_API_KEY not set — skipping live fetch.")

    import httpx  # lazy import — not available in all envs during early dev

    response = httpx.get(
        OILPRICEAPI_VLSFO_URL,
        headers={"Authorization": f"Token {_API_KEY}"},
        timeout=10.0,
    )
    response.raise_for_status()
    data: dict[str, Any] = response.json()

    price = float(data["data"]["price"])
    row = {
        "date": date.today().isoformat(),
        "price_usd": price,
        "fuel_code": "VLSFO_USD",
    }
    return pd.DataFrame([row])


def _fetch_fallback() -> pd.DataFrame:
    if not _FALLBACK_PATH.exists():
        raise FileNotFoundError(f"Bunker fallback CSV not found at {_FALLBACK_PATH}")
    df = pd.read_csv(_FALLBACK_PATH)
    logger.debug("Bunker: loaded %d rows from fallback %s", len(df), _FALLBACK_PATH)
    return df
