"""
ingestion/batch/fleet_demand_ingest.py — fleet & demand data ingestion.

Source:  data/raw/fleet_demand_fixture.csv
Cadence: monthly / quarterly (called by scheduler.py)

DOC3 §FEATURE: Data Ingestion Layer
DOC2 §5.1, §6.1
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from backend.ingestion.types import IngestResult
from backend.ingestion.validation import FLEET_DEMAND_SCHEMA, validate

logger = logging.getLogger(__name__)

_FIXTURE_PATH = (
    Path(__file__).parent.parent.parent / "data" / "raw" / "fleet_demand_fixture.csv"
)


def run() -> IngestResult:
    """Parse, validate, and return fleet/demand data as IngestResult."""
    source_label = "fleet_demand_orderbook"

    try:
        raw_df = _fetch()
    except Exception as exc:
        logger.error("Fleet demand fetch failed: %s", exc)
        return IngestResult(
            source=source_label,
            rows_ingested=0,
            rows_rejected=0,
            alerts=[f"Fetch error: {exc}"],
        )

    batch = validate(raw_df, FLEET_DEMAND_SCHEMA)

    if batch.rejected:
        for r in batch.rejected:
            logger.warning(
                "Fleet demand rejected row %d: %s", r.row_index, r.reason
            )

    logger.info(
        "Fleet demand ingest: %d clean, %d rejected",
        len(batch.rows), len(batch.rejected),
    )
    return IngestResult(
        source=source_label,
        rows_ingested=len(batch.rows),
        rows_rejected=len(batch.rejected),
        alerts=batch.alerts,
    )


def _fetch() -> pd.DataFrame:
    if not _FIXTURE_PATH.exists():
        raise FileNotFoundError(f"Fleet demand fixture not found at {_FIXTURE_PATH}")
    df = pd.read_csv(_FIXTURE_PATH)
    logger.debug("Fleet demand: loaded %d rows from %s", len(df), _FIXTURE_PATH)
    return df
