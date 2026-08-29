"""
ingestion/validation.py — four mandatory checks for every raw ingestion batch.

DOC3 §FEATURE: Data Ingestion Layer → validation.validate()
DOC2 §18.1

Implements:
  1. Schema / type check    — reject rows with wrong dtypes or missing required columns
  2. Freshness check        — alert if latest point > 2 days old on a daily feed
  3. Gap-fill               — forward-fill weekend/holiday gaps in daily series
  4. Plausibility check     — reject rows with values outside sane bounds

Returns ValidatedBatch — nothing is silently dropped without a logged reason.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

import pandas as pd

from backend.ingestion.types import IngestResult, RejectedRow, ValidatedBatch

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schema descriptor
# ---------------------------------------------------------------------------

@dataclass
class ColumnSpec:
    """Declares expected dtype and optional plausibility bounds for one column."""
    dtype: type            # int | float | str | date/datetime
    required: bool = True
    min_val: float | None = None   # plausibility lower bound (numeric columns only)
    max_val: float | None = None   # plausibility upper bound


@dataclass
class IngestSchema:
    """
    Full schema descriptor for one ingestion source.

    columns         — column specs keyed by column name
    date_column     — name of the column holding the observation date (used for
                      freshness + gap-fill checks); None to skip those checks
    is_daily        — True if the series is expected to have daily cadence
    freshness_days  — alert threshold: alert if max(date_column) < today - freshness_days
    """
    columns: dict[str, ColumnSpec]
    date_column: str | None = None
    is_daily: bool = True
    freshness_days: int = 2


# ---------------------------------------------------------------------------
# Pre-built schemas (imported by batch modules)
# ---------------------------------------------------------------------------

BDI_SCHEMA = IngestSchema(
    columns={
        "date":      ColumnSpec(dtype=date),
        "bdi_value": ColumnSpec(dtype=float, min_val=0.0, max_val=30_000.0),
        "source":    ColumnSpec(dtype=str),
    },
    date_column="date",
    is_daily=True,
    freshness_days=2,
)

BUNKER_SCHEMA = IngestSchema(
    columns={
        "date":      ColumnSpec(dtype=date),
        "price_usd": ColumnSpec(dtype=float, min_val=50.0, max_val=2_500.0),
        "fuel_code": ColumnSpec(dtype=str),
    },
    date_column="date",
    is_daily=True,
    freshness_days=2,
)

PORT_CONSTRAINT_SCHEMA = IngestSchema(
    columns={
        "port_name":          ColumnSpec(dtype=str),
        "max_draft_m":        ColumnSpec(dtype=float, min_val=5.0,   max_val=30.0),
        "max_loa_m":          ColumnSpec(dtype=float, min_val=50.0,  max_val=500.0),
        "max_beam_m":         ColumnSpec(dtype=float, min_val=10.0,  max_val=100.0),
        "handling_rate_tpd":  ColumnSpec(dtype=float, min_val=100.0, max_val=200_000.0),
        "tidal_dependent":    ColumnSpec(dtype=str),   # "true"/"false" string in CSV
    },
    date_column=None,    # port constraints are not a time series
    is_daily=False,
    freshness_days=90,
)

FLEET_DEMAND_SCHEMA = IngestSchema(
    columns={
        "vessel_class":    ColumnSpec(dtype=str),
        "capacity_tonnes": ColumnSpec(dtype=float, min_val=1_000.0,   max_val=500_000.0),
        "draft_m":         ColumnSpec(dtype=float, min_val=3.0,       max_val=30.0),
        "loa_m":           ColumnSpec(dtype=float, min_val=50.0,      max_val=500.0),
        "beam_m":          ColumnSpec(dtype=float, min_val=10.0,      max_val=100.0),
        "date":            ColumnSpec(dtype=date),
        "demand_index":    ColumnSpec(dtype=float, min_val=0.0,       max_val=1_000.0),
    },
    date_column="date",
    is_daily=False,
    freshness_days=90,
)

RATE_5TC_SCHEMA = IngestSchema(
    columns={
        "date":        ColumnSpec(dtype=date),
        "route":       ColumnSpec(dtype=str),
        "vessel_class":ColumnSpec(dtype=str),
        "rate":        ColumnSpec(dtype=float, min_val=0.0, max_val=200_000.0),
        "tier":        ColumnSpec(dtype=str),    # "A" or "B"
        "source":      ColumnSpec(dtype=str),
    },
    date_column="date",
    is_daily=True,
    freshness_days=7,
)

MACRO_FEATURES_SCHEMA = IngestSchema(
    columns={
        "source": ColumnSpec(dtype=str),
        "date":   ColumnSpec(dtype=date),
        "value":  ColumnSpec(dtype=float, min_val=-10_000.0, max_val=500_000.0),
    },
    date_column="date",
    is_daily=True,
    freshness_days=7,
)

OPERATIONAL_EVIDENCE_SCHEMA = IngestSchema(
    columns={
        "route":        ColumnSpec(dtype=str),
        "vessel_class": ColumnSpec(dtype=str),
        "observed_at":  ColumnSpec(dtype=date),
        "note":         ColumnSpec(dtype=str),
    },
    date_column="observed_at",
    is_daily=False,
    freshness_days=30,
)


# ---------------------------------------------------------------------------
# Core validation function
# ---------------------------------------------------------------------------

def validate(raw_df: pd.DataFrame, schema: IngestSchema) -> ValidatedBatch:
    """
    Run the four mandatory checks against raw_df and return a ValidatedBatch.

    1. Schema / type check  → rows with wrong dtypes or missing required cols → rejected
    2. Freshness check      → latest date older than threshold → alert (row kept)
    3. Gap-fill             → forward-fill weekday gaps in daily series → alert
    4. Plausibility check   → values outside min/max bounds → rejected

    Nothing is silently dropped — every rejected row has a logged reason.
    """
    batch = ValidatedBatch()

    if raw_df.empty:
        batch.alerts.append("Input dataframe is empty — nothing to validate.")
        logger.warning("validate() called with empty dataframe.")
        return batch

    df = raw_df.copy()

    # ------------------------------------------------------------------ #
    # 1. Schema / type check
    # ------------------------------------------------------------------ #
    required_cols = {
        col for col, spec in schema.columns.items() if spec.required
    }
    missing_cols = required_cols - set(df.columns)
    if missing_cols:
        msg = f"Missing required columns: {sorted(missing_cols)}"
        logger.error(msg)
        # Reject ALL rows — schema is fundamentally wrong
        for idx, row in df.iterrows():
            batch.rejected.append(RejectedRow(
                row_index=int(idx),
                raw_data=row.to_dict(),
                reason=msg,
            ))
        return batch

    # Per-row dtype coercion — reject rows that can't be coerced
    valid_indices: list[int] = []
    for idx, row in df.iterrows():
        row_errors: list[str] = []
        for col, spec in schema.columns.items():
            if col not in df.columns:
                continue
            val = row[col]
            if pd.isna(val):
                if spec.required:
                    row_errors.append(f"Column '{col}' is required but missing/NaN")
                continue
            # Coerce to declared dtype
            try:
                if spec.dtype in (date, datetime):
                    pd.to_datetime(val)   # just check parsability here; date col parsed later
                elif spec.dtype == float:
                    float(val)
                elif spec.dtype == int:
                    int(val)
                elif spec.dtype == str:
                    str(val)
            except (ValueError, TypeError) as exc:
                row_errors.append(f"Column '{col}' dtype coercion failed: {exc}")

        if row_errors:
            reason = "; ".join(row_errors)
            logger.warning("Row %d rejected (schema): %s", idx, reason)
            batch.rejected.append(RejectedRow(
                row_index=int(idx),
                raw_data=row.to_dict(),
                reason=reason,
            ))
        else:
            valid_indices.append(int(idx))

    df = df.loc[valid_indices].copy()
    if df.empty:
        return batch

    # ------------------------------------------------------------------ #
    # 2. Freshness check (daily feeds only)
    # ------------------------------------------------------------------ #
    if schema.date_column and schema.date_column in df.columns:
        df[schema.date_column] = pd.to_datetime(df[schema.date_column]).dt.date
        latest_date = df[schema.date_column].max()
        cutoff = date.today() - timedelta(days=schema.freshness_days)
        if latest_date < cutoff:
            msg = (
                f"Freshness alert: latest '{schema.date_column}' is {latest_date}, "
                f"older than {schema.freshness_days}-day threshold (cutoff: {cutoff})"
            )
            logger.warning(msg)
            batch.alerts.append(msg)

    # ------------------------------------------------------------------ #
    # 3. Gap-fill (daily series only, single row per date)
    # ------------------------------------------------------------------ #
    if schema.is_daily and schema.date_column and schema.date_column in df.columns:
        date_col = schema.date_column
        numeric_cols = [
            col for col, spec in schema.columns.items()
            if spec.dtype == float and col in df.columns
        ]
        if numeric_cols and not df.empty:
            df[date_col] = pd.to_datetime(df[date_col])
            df = df.sort_values(date_col)

            # Gap-fill only makes sense for single-value-per-date series.
            # Feeds like rate_5tc (one row per route×date) or macro_features
            # (one row per source×date) have non-unique date indices — reindex
            # would raise ValueError. Skip gap-fill for those; they have their
            # own grouping logic.
            if df[date_col].is_unique:
                full_idx = pd.bdate_range(
                    start=df[date_col].min(),
                    end=df[date_col].max(),
                )
                df = df.set_index(date_col).reindex(full_idx)
                n_gaps = df[numeric_cols].isna().any(axis=1).sum()
                if n_gaps > 0:
                    df[numeric_cols] = df[numeric_cols].ffill()
                    gap_msg = f"Gap-fill: forward-filled {n_gaps} missing business-day row(s)."
                    logger.info(gap_msg)
                    batch.alerts.append(gap_msg)

                df = df.reset_index().rename(columns={"index": date_col})
                df[date_col] = df[date_col].dt.date

                # Re-fill non-numeric columns from the last known value
                non_numeric = [
                    col for col in df.columns
                    if col != date_col and col not in numeric_cols
                ]
                df[non_numeric] = df[non_numeric].ffill()
            else:
                # Non-unique date index (multi-row-per-date feed) — convert
                # date column back to date objects for plausibility step
                df[date_col] = df[date_col].dt.date

    # ------------------------------------------------------------------ #
    # 4. Plausibility check
    # ------------------------------------------------------------------ #
    plausibility_valid: list[int] = []
    for idx, row in df.iterrows():
        row_errors: list[str] = []
        for col, spec in schema.columns.items():
            if col not in df.columns or spec.dtype != float:
                continue
            val = row.get(col)
            if val is None or (isinstance(val, float) and pd.isna(val)):
                continue
            try:
                fval = float(val)
            except (ValueError, TypeError):
                continue
            if spec.min_val is not None and fval < spec.min_val:
                row_errors.append(
                    f"Column '{col}' value {fval} < min {spec.min_val}"
                )
            if spec.max_val is not None and fval > spec.max_val:
                row_errors.append(
                    f"Column '{col}' value {fval} > max {spec.max_val}"
                )
        if row_errors:
            reason = "; ".join(row_errors)
            logger.warning("Row %s rejected (plausibility): %s", idx, reason)
            batch.rejected.append(RejectedRow(
                row_index=int(idx) if isinstance(idx, (int, float)) else -1,
                raw_data=row.to_dict(),
                reason=reason,
            ))
        else:
            plausibility_valid.append(idx)

    df = df.loc[plausibility_valid].copy() if plausibility_valid else df.iloc[0:0].copy()

    # ------------------------------------------------------------------ #
    # Finalise
    # ------------------------------------------------------------------ #
    batch.rows = df.to_dict(orient="records")
    return batch
