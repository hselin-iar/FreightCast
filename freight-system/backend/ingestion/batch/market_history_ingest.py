"""
ingestion/batch/market_history_ingest.py — Historical market feature ingestion.

Sources (all from freight_optimization/data/raw/market/):
  brent_historical.csv    → ExogenousFeature sources: "brent", "brent_return_1d", "brent_change_7d"
  wti_historical.csv      → ExogenousFeature sources: "wti", "wti_return_1d", "wti_change_7d"
  iron_ore_historical.csv → ExogenousFeature sources: "iron_ore", "iron_ore_change_1m",
                                                       "iron_ore_change_3m", "iron_ore_ma_3m"

Target: ExogenousFeature table via repository.upsert_exogenous_feature()
Cadence: called by scheduler.py on RETRAIN_SCHEDULE_CRON (weekly).
         Also callable once-off from bootstrap commands.

Design notes:
  - Each derived column (return_1d, change_7d, etc.) is stored under its own `source` key.
    This matches the existing _load_exogenous_features() pattern which pulls by source name,
    so _fit_xgboost can retrieve exactly the features it needs without in-model joins.
  - NaN rows (e.g. first row of return_1d series) are dropped silently — not rejected.
  - All rows tagged provenance="measured".
  - Resolves the freight_optimization root relative to this file so it works in any CWD.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List

import pandas as pd

from backend.ingestion.types import IngestResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).parent.parent.parent.parent.parent  # FrieghtCast/
_MARKET_DIR = _REPO_ROOT / "freight_optimization" / "data" / "raw" / "market"

_SOURCES: dict[str, list[tuple[str, str]]] = {
    # csv_filename: list of (column_in_csv, source_key_in_db)
    "brent_historical.csv": [
        ("price",      "brent"),
        ("return_1d",  "brent_return_1d"),
        ("change_7d",  "brent_change_7d"),
    ],
    "wti_historical.csv": [
        ("price",      "wti"),
        ("return_1d",  "wti_return_1d"),
        ("change_7d",  "wti_change_7d"),
    ],
    "iron_ore_historical.csv": [
        ("iron_ore_price",       "iron_ore"),
        ("iron_ore_change_1m",   "iron_ore_change_1m"),
        ("iron_ore_change_3m",   "iron_ore_change_3m"),
        ("iron_ore_ma_3m",       "iron_ore_ma_3m"),
    ],
}

# Module-level cache for get_rows() (same pattern as capesize_5tc_history_ingest)
_last_clean_rows: List[dict] = []


def run() -> IngestResult:
    """
    Parse and return historical market feature data as IngestResult.

    Rows are NOT written here — the caller (scheduler.py or bootstrap script) writes
    them via repository.upsert_exogenous_feature(market_history_ingest.get_rows()).
    """
    source_label = "market_history_multi"
    total_written = 0
    total_rejected = 0
    alerts: list[str] = []
    all_rows: list[dict] = []

    for csv_name, col_map in _SOURCES.items():
        path = _MARKET_DIR / csv_name
        if not path.exists():
            msg = f"Market history CSV not found (skipped): {path}"
            logger.warning(msg)
            alerts.append(msg)
            continue

        try:
            df = pd.read_csv(path, parse_dates=["date"])
        except Exception as exc:
            msg = f"Failed to read {csv_name}: {exc}"
            logger.error(msg)
            alerts.append(msg)
            continue

        df = df.sort_values("date").reset_index(drop=True)

        for col, source_key in col_map:
            if col not in df.columns:
                alerts.append(f"{csv_name}: column '{col}' not found — skipped.")
                continue

            sub = df[["date", col]].dropna(subset=[col]).copy()
            for _, row in sub.iterrows():
                all_rows.append({
                    "source": source_key,
                    "date": row["date"].isoformat(),
                    "value": float(row[col]),
                    "unit": "varies",
                    "provenance": "measured",
                })
            total_written += len(sub)
            logger.debug(
                "market_history_ingest: %s / %s → %d rows", csv_name, source_key, len(sub)
            )

    global _last_clean_rows
    _last_clean_rows = all_rows

    logger.info(
        "Market history ingest: %d rows across %d source keys",
        total_written, len(all_rows),
    )
    return IngestResult(
        source=source_label,
        rows_ingested=total_written,
        rows_rejected=total_rejected,
        alerts=alerts,
    )


def get_rows() -> List[dict]:
    """
    Return all validated rows from the most recent run() call.
    Pass to repository.upsert_exogenous_feature() in bootstrap/scheduler.

    Returns [] if run() has not been called yet in this process.
    """
    return list(_last_clean_rows)
