"""
engine/congestion.py — port congestion read path.

CARRIED OVER SHAPE (DOC3 §0.1): CongestionSnapshot shape and fallback behaviour
are unchanged from the prior build. Extended in this version to read from the
warehouse (via repository.py in Build Step 3) instead of calling aisstream.io
directly per-request.

Build Step 2: reads from ais_listener's in-memory store.
Build Step 3: swap _read_from_listener() for repository.get_latest_congestion_snapshot().

DOC3 §FEATURE: AIS Listener & Congestion Module → congestion.py (read path)
DOC2 §9: "AIS feed can drop" — never a 500.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.config.constants import AIS_CONGESTION_CACHE_TTL_SECONDS

logger = logging.getLogger(__name__)

# Staleness multiplier: if the latest snapshot is older than this many TTL
# periods, treat the listener as presumed down and label accordingly.
_STALENESS_MULTIPLIER = 5   # 5 × TTL_SECONDS = "listener is down"


# ---------------------------------------------------------------------------
# Public type — CARRIED OVER SHAPE (DOC3 §0.1, unchanged)
# ---------------------------------------------------------------------------

@dataclass
class CongestionSnapshot:
    """
    Port congestion state at a point in time.

    Shape is unchanged from the prior build (DOC3 §0.1 — Migration Delta §2).
    Every caller (decision.py, /port-status, dashboard) reads this exact shape.

    is_live=True  → from an active AIS stream within the staleness threshold.
    is_live=False → stale or cold-start; source_note explains why.
    """
    port: str
    vessel_count: int
    avg_wait_hours: float
    is_live: bool
    source_note: str
    recorded_at: datetime | None = None


# ---------------------------------------------------------------------------
# Seeded fallback values (cold-start / total AIS outage)
# ---------------------------------------------------------------------------

_SEEDED_FALLBACKS: dict[str, dict[str, Any]] = {
    "Paradip":    {"vessel_count": 3, "avg_wait_hours": 12.0},
    "Gangavaram": {"vessel_count": 2, "avg_wait_hours": 8.0},
    "Dhamra":     {"vessel_count": 1, "avg_wait_hours": 6.0},
}

_DEFAULT_FALLBACK = {"vessel_count": 0, "avg_wait_hours": 0.0}


# ---------------------------------------------------------------------------
# Core read function
# ---------------------------------------------------------------------------

def get_congestion_snapshot(port: str) -> CongestionSnapshot:
    """
    Return the latest congestion snapshot for port.

    Staleness logic (DOC3 §FEATURE: AIS Listener, DOC2 §9):
      - Fresh (within TTL × multiplier): is_live=True, source_note="live AIS stream"
      - Stale (older than threshold): is_live=True on the snapshot object, but
        source_note explicitly says "stale — AIS feed may be down" so callers
        know not to present it as a current measurement.
      - No data at all (cold start): falls back to seeded placeholder with
        is_live=False, source_note="seeded fallback — no AIS data available".

    Never raises — a 500 from AIS data absence would violate DOC2 §9.
    """
    now = datetime.now(timezone.utc)
    staleness_threshold = timedelta(seconds=AIS_CONGESTION_CACHE_TTL_SECONDS * _STALENESS_MULTIPLIER)

    raw = _read_snapshot(port)

    if raw is None:
        # Cold start — no data ever written for this port
        fallback = _SEEDED_FALLBACKS.get(port, _DEFAULT_FALLBACK)
        logger.info(
            "Congestion: no data for '%s' — returning seeded fallback.", port
        )
        return CongestionSnapshot(
            port=port,
            vessel_count=fallback["vessel_count"],
            avg_wait_hours=fallback["avg_wait_hours"],
            is_live=False,
            source_note="seeded fallback — no AIS data available for this port yet",
            recorded_at=None,
        )

    recorded_at = raw.get("recorded_at")
    if recorded_at and isinstance(recorded_at, datetime):
        # Ensure timezone-aware for comparison
        if recorded_at.tzinfo is None:
            recorded_at = recorded_at.replace(tzinfo=timezone.utc)
        age = now - recorded_at
        is_stale = age > staleness_threshold
    else:
        is_stale = False  # no timestamp → assume fresh (listener just wrote it)

    if is_stale:
        source_note = (
            f"stale — AIS feed may be down "
            f"(last update {recorded_at.isoformat() if recorded_at else 'unknown'})"
        )
        logger.warning("Congestion: stale data for '%s': %s", port, source_note)
    else:
        source_note = raw.get("source_note", "live AIS stream")

    return CongestionSnapshot(
        port=port,
        vessel_count=int(raw.get("vessel_count", 0)),
        avg_wait_hours=float(raw.get("avg_wait_hours", 0.0)),
        is_live=not is_stale,
        source_note=source_note,
        recorded_at=recorded_at,
    )


# ---------------------------------------------------------------------------
# Storage backend — Build Step 2: reads from ais_listener's in-memory store.
# Build Step 3: replace with repository.get_latest_congestion_snapshot(port).
# ---------------------------------------------------------------------------

def _read_snapshot(port: str) -> dict[str, Any] | None:
    """
    Read the latest raw snapshot for port.

    Primary: repository.get_latest_congestion_snapshot(port) — warehouse row.
    Fallback: ais_listener's in-memory store (if warehouse not yet available).
    """
    # Primary: warehouse (Build Step 3+)
    try:
        from backend.warehouse import repository
        result = repository.get_latest_congestion_snapshot(port)
        if result is not None:
            return result
    except Exception as exc:
        logger.debug(
            "Congestion: warehouse read failed for '%s', falling back to in-memory: %s",
            port, exc,
        )

    # Fallback: ais_listener in-memory store (Step 2 compat / warehouse cold start)
    try:
        from backend.ingestion.ais_listener import get_latest_congestion_snapshot
        return get_latest_congestion_snapshot(port)
    except Exception as exc:
        logger.warning(
            "Congestion: could not read from any store for '%s': %s", port, exc,
        )
        return None

