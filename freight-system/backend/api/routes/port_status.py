"""
api/routes/port_status.py — GET /port-status

Thin pass-through to congestion.get_congestion_snapshot().
DOC3 §FEATURE: API Layer.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from backend.api.schemas import PortStatusResponse
from backend.engine import congestion

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/port-status", response_model=PortStatusResponse)
def get_port_status(
    port: str = Query(..., description="Port name, e.g. 'Paradip, India'"),
) -> PortStatusResponse:
    """
    Return the latest congestion snapshot for a port.
    Degrades gracefully if the AIS listener hasn't run — returns is_live=False
    with a seeded-fallback snapshot, never a 500.
    congestion.get_congestion_snapshot() handles the staleness/fallback path.
    """
    try:
        snap = congestion.get_congestion_snapshot(port=port)
    except Exception as exc:
        logger.exception("congestion.get_congestion_snapshot() raised an error")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    # Handle both CongestionSnapshot dataclass and dict
    is_live = getattr(snap, "is_live", snap.get("is_live", False) if isinstance(snap, dict) else False)
    port_name = getattr(snap, "port", snap.get("port", port) if isinstance(snap, dict) else port)
    vessel_count = getattr(snap, "vessel_count", snap.get("vessel_count", 0) if isinstance(snap, dict) else 0)
    avg_wait_hours = getattr(snap, "avg_wait_hours", snap.get("avg_wait_hours", 0.0) if isinstance(snap, dict) else 0.0)
    recorded_at = getattr(snap, "recorded_at", snap.get("recorded_at") if isinstance(snap, dict) else None)
    source_note = getattr(snap, "source_note", snap.get("source_note") if isinstance(snap, dict) else None)
    bunker_price = getattr(snap, "bunker_price_usd", snap.get("bunker_price_usd") if isinstance(snap, dict) else None)

    # Determine provenance: measured if live AIS, assumed if seeded fallback
    prov = "measured" if is_live else "assumed"

    return PortStatusResponse(
        port=port_name,
        vessel_count=vessel_count,
        avg_wait_hours=avg_wait_hours,
        recorded_at=recorded_at,
        is_live=is_live,
        source_note=source_note,
        bunker_price_usd=bunker_price,
        provenance=prov,
    )
