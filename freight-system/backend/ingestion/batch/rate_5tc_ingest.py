"""
ingestion/batch/rate_5tc_ingest.py — Capesize 5TC rate ingestion.

NEW — DOC2 Addendum v3 §A2.

Source:  data/raw/rate_5tc_fixture.csv
         (clean NLP-extracted Capesize 5TC output — pre-verified offline;
          this module ingests the CLEAN output, does NOT re-run extraction)
Cadence: daily (called by scheduler.py)

Key behaviours:
  - All rows tagged provenance="measured"
  - Tier A/B field preserved as confidence — NOT collapsed
    (allows forecasting.py to weight/filter by tier without re-ingesting)
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from backend.ingestion.types import IngestResult
from backend.ingestion.validation import RATE_5TC_SCHEMA, validate

logger = logging.getLogger(__name__)

_FIXTURE_PATH = (
    Path(__file__).parent.parent.parent / "data" / "raw" / "rate_5tc_fixture.csv"
)


def run() -> IngestResult:
    """Parse, validate, and return Capesize 5TC rate data as IngestResult."""
    source_label = "rate_5tc_clarksons"

    try:
        raw_df = _fetch()
    except Exception as exc:
        logger.error("Rate 5TC fetch failed: %s", exc)
        return IngestResult(
            source=source_label,
            rows_ingested=0,
            rows_rejected=0,
            alerts=[f"Fetch error: {exc}"],
        )

    batch = validate(raw_df, RATE_5TC_SCHEMA)

    if batch.rejected:
        for r in batch.rejected:
            logger.warning(
                "Rate 5TC rejected row %d: %s", r.row_index, r.reason
            )

    # Tag every clean row as provenance="measured" — stored on the row dict,
    # not collapsed into the IngestResult; Build Step 3 will persist this field.
    for row in batch.rows:
        row.setdefault("provenance", "measured")
        # Preserve tier exactly as-is (A or B) — never collapse
        assert row.get("tier") in ("A", "B", None), (
            f"Unexpected tier value: {row.get('tier')!r}"
        )

    logger.info(
        "Rate 5TC ingest: %d clean, %d rejected",
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
        raise FileNotFoundError(f"Rate 5TC fixture not found at {_FIXTURE_PATH}")
    df = pd.read_csv(_FIXTURE_PATH)
    logger.debug("Rate 5TC: loaded %d rows from %s", len(df), _FIXTURE_PATH)
    return df
