"""
ingestion/batch/macro_features_ingest.py — macro/exogenous feature ingestion.

NEW — DOC2 Addendum v3 §A2.

Sources: EXOGENOUS_FEATURE_SOURCES (Brent, WTI, Iron Ore, BDRY, GSCPI)
Fixture: data/raw/macro_features_fixture.csv
Cadence: daily (called by scheduler.py)

Rows keyed by (source, date) — stored in a dedicated exogenous_features table
(separate from RateHistory since these are model inputs, not freight rates themselves).
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from backend.config.constants import EXOGENOUS_FEATURE_SOURCES
from backend.ingestion.types import IngestResult
from backend.ingestion.validation import MACRO_FEATURES_SCHEMA, validate

logger = logging.getLogger(__name__)

_FIXTURE_PATH = (
    Path(__file__).parent.parent.parent / "data" / "raw" / "macro_features_fixture.csv"
)


def run() -> IngestResult:
    """Parse, validate, and return macro feature data as IngestResult."""
    source_label = "macro_features_multi"

    try:
        raw_df = _fetch()
    except Exception as exc:
        logger.error("Macro features fetch failed: %s", exc)
        return IngestResult(
            source=source_label,
            rows_ingested=0,
            rows_rejected=0,
            alerts=[f"Fetch error: {exc}"],
        )

    # Filter to only the declared EXOGENOUS_FEATURE_SOURCES
    known_sources = set(EXOGENOUS_FEATURE_SOURCES)
    unknown = set(raw_df["source"].unique()) - known_sources if "source" in raw_df.columns else set()
    if unknown:
        msg = f"Unknown macro feature sources in fixture (ignored): {sorted(unknown)}"
        logger.warning(msg)
        raw_df = raw_df[raw_df["source"].isin(known_sources)].copy()

    batch = validate(raw_df, MACRO_FEATURES_SCHEMA)

    if batch.rejected:
        for r in batch.rejected:
            logger.warning(
                "Macro features rejected row %d: %s", r.row_index, r.reason
            )

    alerts = batch.alerts[:]
    if unknown:
        alerts.append(f"Unknown sources skipped: {sorted(unknown)}")

    logger.info(
        "Macro features ingest: %d clean, %d rejected",
        len(batch.rows), len(batch.rejected),
    )
    return IngestResult(
        source=source_label,
        rows_ingested=len(batch.rows),
        rows_rejected=len(batch.rejected),
        alerts=alerts,
    )


def _fetch() -> pd.DataFrame:
    if not _FIXTURE_PATH.exists():
        raise FileNotFoundError(f"Macro features fixture not found at {_FIXTURE_PATH}")
    df = pd.read_csv(_FIXTURE_PATH)
    logger.debug("Macro features: loaded %d rows from %s", len(df), _FIXTURE_PATH)
    return df
