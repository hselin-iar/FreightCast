"""
ingestion/batch/bdi_ingest.py — Baltic Dry Index ingestion.

Source: data/raw/bdi_fixture.csv (fixture)
        In production: Investing.com CSV export / OilPriceAPI
Cadence: daily (called by scheduler.py)

DOC3 §FEATURE: Data Ingestion Layer
DOC2 §5.1, §6.1
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import pandas as pd

from backend.ingestion.types import IngestResult
from backend.ingestion.validation import BDI_SCHEMA, validate

logger = logging.getLogger(__name__)

# Path to fixture CSV — resolved relative to this file's package root
_FIXTURE_PATH = Path(__file__).parent.parent.parent / "data" / "raw" / "bdi_fixture.csv"


def run() -> IngestResult:
    """
    Parse and validate the BDI source.

    Returns IngestResult with rows_ingested / rows_rejected counts.
    Does NOT write to the warehouse — that's wired in Build Step 3.
    """
    source_label = "bdi_investing_csv"

    try:
        raw_df = _fetch()
    except Exception as exc:
        logger.error("BDI fetch failed: %s", exc)
        return IngestResult(
            source=source_label,
            rows_ingested=0,
            rows_rejected=0,
            alerts=[f"Fetch error: {exc}"],
        )

    batch = validate(raw_df, BDI_SCHEMA)

    if batch.rejected:
        for r in batch.rejected:
            logger.warning("BDI rejected row %d: %s", r.row_index, r.reason)

    logger.info(
        "BDI ingest: %d clean, %d rejected, %d alerts",
        len(batch.rows), len(batch.rejected), len(batch.alerts),
    )
    return IngestResult(
        source=source_label,
        rows_ingested=len(batch.rows),
        rows_rejected=len(batch.rejected),
        alerts=batch.alerts,
    )


def _fetch() -> pd.DataFrame:
    """
    Fetch raw BDI data.
    Uses the fixture CSV for now; swap for a live source in production.
    """
    if not _FIXTURE_PATH.exists():
        raise FileNotFoundError(f"BDI fixture not found at {_FIXTURE_PATH}")
    df = pd.read_csv(_FIXTURE_PATH)
    logger.debug("BDI: loaded %d rows from %s", len(df), _FIXTURE_PATH)
    return df
