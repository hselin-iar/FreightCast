"""
ingestion/batch/capesize_5tc_history_ingest.py — Real Capesize 5TC rate history ingestion.

Sources (in priority order):
  1. freight_optimization/data/raw/freight/drycargo_5tc_c5.csv          (164 rows, 2019-04-01 → 2026-08-24)
  2. freight_optimization/data/raw/freight/drycargo_5tc_verified_candidates.csv  (fallback)

Target:  RateHistory  (route="C5", vessel_class="Capesize")
Cadence: called by scheduler.py on RETRAIN_SCHEDULE_CRON (weekly).
         Also callable once-off from management commands to bootstrap the warehouse.

Key behaviours:
  - Prefers the longest real series over the 25-row fixture (rate_5tc_fixture.csv covers
    only 2026-07-27→2026-08-28, too short for XGBoost to qualify at the new 80-obs gate).
  - Uses the SAME route key ("C5") the rest of the system expects.
  - All rows tagged provenance="measured", tier="A".
  - Validates through the existing RATE_5TC_SCHEMA (plausibility bounds 0–200_000).
  - Resolves the freight_optimization root relative to this file's position in the repo,
    so it works in any working directory.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List

import pandas as pd

from backend.ingestion.types import IngestResult
from backend.ingestion.validation import RATE_5TC_SCHEMA, validate

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths — relative to this file so they work regardless of CWD
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).parent.parent.parent.parent.parent  # FrieghtCast/
_PRIMARY_PATH = (
    _REPO_ROOT / "freight_optimization" / "data" / "raw" / "freight" / "drycargo_5tc_c5.csv"
)
_FALLBACK_PATH = (
    _REPO_ROOT
    / "freight_optimization"
    / "data"
    / "raw"
    / "freight"
    / "drycargo_5tc_verified_candidates.csv"
)

ROUTE = "C5"
VESSEL_CLASS = "Capesize"

# Module-level cache of last clean rows — populated by run(), read by get_rows()
_last_clean_rows: List[dict] = []


def run() -> IngestResult:
    """
    Parse, validate, and return real Capesize 5TC rate history as IngestResult.

    Called by scheduler.py and once-off bootstrap commands.
    Returns an IngestResult whose .rows are ready for repository.upsert_rate_history().
    """
    source_label = "capesize_5tc_real_history"

    try:
        raw_df, source_path = _fetch()
    except FileNotFoundError as exc:
        logger.error("Capesize 5TC history: neither primary nor fallback CSV found: %s", exc)
        return IngestResult(
            source=source_label,
            rows_ingested=0,
            rows_rejected=0,
            alerts=[f"Source CSV not found: {exc}"],
        )
    except Exception as exc:
        logger.error("Capesize 5TC history fetch failed: %s", exc)
        return IngestResult(
            source=source_label,
            rows_ingested=0,
            rows_rejected=0,
            alerts=[f"Fetch error: {exc}"],
        )

    # Normalise to the shape RATE_5TC_SCHEMA expects:
    # date, route, vessel_class, rate, tier, source
    normalised = _normalise(raw_df, source_path)

    batch = validate(normalised, RATE_5TC_SCHEMA)

    if batch.rejected:
        for r in batch.rejected:
            logger.warning(
                "Capesize 5TC history rejected row %d: %s", r.row_index, r.reason
            )

    for row in batch.rows:
        row.setdefault("provenance", "measured")

    logger.info(
        "Capesize 5TC history ingest: %d clean, %d rejected (source: %s)",
        len(batch.rows), len(batch.rejected), source_path.name,
    )

    # Persist to module-level cache for bootstrap callers (get_rows()).
    # IngestResult intentionally has no rows field — that contract is fixed.
    global _last_clean_rows
    _last_clean_rows = batch.rows

    return IngestResult(
        source=source_label,
        rows_ingested=len(batch.rows),
        rows_rejected=len(batch.rejected),
        alerts=batch.alerts,
    )


def get_rows() -> List[dict]:
    """
    Return the validated rows from the most recent run() call.
    Used by bootstrap scripts and tests that need to write directly to the
    warehouse without going through scheduler.py.

    Returns [] if run() has not been called yet in this process.
    """
    return list(_last_clean_rows)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _fetch() -> tuple[pd.DataFrame, Path]:
    """
    Load the best available CSV.  Primary → fallback.
    Returns (DataFrame, resolved_path).
    Raises FileNotFoundError if neither is present.
    """
    for path in (_PRIMARY_PATH, _FALLBACK_PATH):
        if path.exists():
            df = pd.read_csv(path, parse_dates=True)
            logger.info("Capesize 5TC history: loaded %d rows from %s", len(df), path)
            return df, path

    raise FileNotFoundError(
        f"Neither primary ({_PRIMARY_PATH}) nor fallback ({_FALLBACK_PATH}) CSV found."
    )


def _normalise(df: pd.DataFrame, source_path: Path) -> pd.DataFrame:
    """
    Map raw CSV columns onto RATE_5TC_SCHEMA column names.

    drycargo_5tc_c5.csv columns:
        report_date, capesize_5tc_usd_per_day, c5_usd_per_mt, source

    drycargo_5tc_verified_candidates.csv columns:
        report_date, capesize_5tc_usd_per_day, source, status, source_context

    Both have 'report_date' and 'capesize_5tc_usd_per_day'.
    """
    out = pd.DataFrame()

    # Date
    date_col = "report_date" if "report_date" in df.columns else df.columns[0]
    out["date"] = pd.to_datetime(df[date_col]).dt.date

    # Rate
    rate_col = (
        "capesize_5tc_usd_per_day"
        if "capesize_5tc_usd_per_day" in df.columns
        else "target_5tc"
    )
    out["rate"] = pd.to_numeric(df[rate_col], errors="coerce")

    # Drop rows where rate is missing
    out = out.dropna(subset=["rate"]).reset_index(drop=True)

    # Fixed fields
    out["route"] = ROUTE
    out["vessel_class"] = VESSEL_CLASS
    out["tier"] = "A"
    out["source"] = f"real_history:{source_path.name}"

    return out
