"""
ingestion/batch/operational_evidence_ingest.py — ShipOffer broker data ingestion.

NEW — DOC2 Addendum v3 §A3.

Source:  data/raw/operational_evidence_fixture.csv (ShipOffer broker fixture/position reports)
Cadence: daily / on-demand (called by scheduler.py)

Key constraint:
  This module ONLY ingests and validates.
  Confidence score computation lives in engine/evidence.py (Build Step 9.5).
  Do not compute scores here.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from backend.ingestion.types import IngestResult
from backend.ingestion.validation import OPERATIONAL_EVIDENCE_SCHEMA, validate

logger = logging.getLogger(__name__)

_FIXTURE_PATH = (
    Path(__file__).parent.parent.parent
    / "data" / "raw" / "operational_evidence_fixture.csv"
)


def run() -> IngestResult:
    """Parse, validate, and return operational evidence data as IngestResult."""
    source_label = "shipoffer_broker_data"

    try:
        raw_df = _fetch()
    except Exception as exc:
        logger.error("Operational evidence fetch failed: %s", exc)
        return IngestResult(
            source=source_label,
            rows_ingested=0,
            rows_rejected=0,
            alerts=[f"Fetch error: {exc}"],
        )

    batch = validate(raw_df, OPERATIONAL_EVIDENCE_SCHEMA)

    if batch.rejected:
        for r in batch.rejected:
            logger.warning(
                "Operational evidence rejected row %d: %s", r.row_index, r.reason
            )

    logger.info(
        "Operational evidence ingest: %d clean, %d rejected",
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
        raise FileNotFoundError(
            f"Operational evidence fixture not found at {_FIXTURE_PATH}"
        )
    df = pd.read_csv(_FIXTURE_PATH)
    logger.debug(
        "Operational evidence: loaded %d rows from %s", len(df), _FIXTURE_PATH
    )
    return df
