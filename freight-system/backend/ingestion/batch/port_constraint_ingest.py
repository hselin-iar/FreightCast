"""
ingestion/batch/port_constraint_ingest.py — port constraint ingestion.

Source:  data/raw/port_constraints_fixture.csv
         (In production: pdfplumber/camelot extraction from port authority PDFs)
Cadence: monthly (called by scheduler.py)

HARD REQUIREMENT (DOC3 §FEATURE: Data Ingestion Layer, DOC2 §18.1):
  Any NEW or CHANGED port constraint value is written to `pending_verification`
  in the IngestResult, NOT directly to any active table.
  A human sign-off step (outside this module) flips it to active.
  This is safety-critical, not optional MVP polish.

This module also drives port-scope growth (DOC2 Addendum v3 §A1): adding a new
port means adding a verified row here — no constants.py changes required.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd

from backend.ingestion.types import IngestResult
from backend.ingestion.validation import PORT_CONSTRAINT_SCHEMA, validate

logger = logging.getLogger(__name__)

_FIXTURE_PATH = (
    Path(__file__).parent.parent.parent / "data" / "raw" / "port_constraints_fixture.csv"
)


def run() -> IngestResult:
    """
    Parse and validate port constraint data.

    All valid rows go into pending_verification — not directly active.
    The warehouse (Step 3) consumes pending_verification from IngestResult.
    """
    source_label = "port_constraint_pdf"

    try:
        raw_df = _fetch()
    except Exception as exc:
        logger.error("Port constraint fetch failed: %s", exc)
        return IngestResult(
            source=source_label,
            rows_ingested=0,
            rows_rejected=0,
            alerts=[f"Fetch error: {exc}"],
        )

    batch = validate(raw_df, PORT_CONSTRAINT_SCHEMA)

    if batch.rejected:
        for r in batch.rejected:
            logger.warning(
                "Port constraint rejected row %d (%s): %s",
                r.row_index,
                r.raw_data.get("port_name", "?"),
                r.reason,
            )

    # DOC3 hard requirement: all valid rows → pending_verification, not active.
    pending: list[dict[str, Any]] = []
    for row in batch.rows:
        pending_row = dict(row)
        pending_row["_pending_reason"] = "awaiting human verification (safety-critical)"
        pending.append(pending_row)
        logger.info(
            "Port constraint row for '%s' placed in pending_verification.",
            row.get("port_name", "?"),
        )

    alerts = batch.alerts[:]
    if pending:
        alerts.append(
            f"{len(pending)} port constraint row(s) placed in pending_verification "
            "— human sign-off required before going active."
        )

    logger.info(
        "Port constraint ingest: %d pending_verification, %d rejected",
        len(pending), len(batch.rejected),
    )
    return IngestResult(
        source=source_label,
        rows_ingested=0,       # nothing is "ingested" to an active table yet
        rows_rejected=len(batch.rejected),
        alerts=alerts,
        pending_verification=pending,
    )


def _fetch() -> pd.DataFrame:
    """
    Fetch port constraint data.
    Fixture CSV for now; production replaces this with pdfplumber/camelot extraction.
    """
    if not _FIXTURE_PATH.exists():
        raise FileNotFoundError(f"Port constraints fixture not found at {_FIXTURE_PATH}")
    df = pd.read_csv(_FIXTURE_PATH)
    logger.debug("Port constraints: loaded %d rows from %s", len(df), _FIXTURE_PATH)
    return df
