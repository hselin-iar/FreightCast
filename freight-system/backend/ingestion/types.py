"""
ingestion/types.py — shared data contracts for the ingestion layer.

All batch modules and validation.py import from here.
Never imported by engine/, api/, or warehouse/ — ingestion-layer only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RejectedRow:
    """A single row that failed validation, with a logged reason."""
    row_index: int
    raw_data: dict[str, Any]
    reason: str


@dataclass
class ValidatedBatch:
    """
    Output of validation.validate().

    rows     — list of clean dicts ready for downstream processing.
    rejected — every rejected row with a logged reason; never silently dropped.
    alerts   — non-fatal warnings (e.g. stale data, gap-fills applied).
    """
    rows: list[dict[str, Any]] = field(default_factory=list)
    rejected: list[RejectedRow] = field(default_factory=list)
    alerts: list[str] = field(default_factory=list)


@dataclass
class IngestResult:
    """
    Public contract returned by every batch/*.py run() entrypoint.
    Consumed by scheduler.py and (in Step 3) wired to repository writes.
    """
    source: str
    rows_ingested: int
    rows_rejected: int
    alerts: list[str] = field(default_factory=list)
    # pending_verification: rows flagged for human sign-off before going active.
    # Used by port_constraint_ingest.py — empty for all other modules.
    pending_verification: list[dict[str, Any]] = field(default_factory=list)

    def __repr__(self) -> str:
        pv = f", pending_verification={len(self.pending_verification)}" if self.pending_verification else ""
        alerts = f", alerts={self.alerts}" if self.alerts else ""
        return (
            f"IngestResult(source={self.source!r}, "
            f"rows_ingested={self.rows_ingested}, "
            f"rows_rejected={self.rows_rejected}"
            f"{pv}{alerts})"
        )
