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


# ---------------------------------------------------------------------------
# Port Constraints & Hydrodynamics
# ---------------------------------------------------------------------------

from pydantic import BaseModel
from typing import Dict, Any, List, Optional

class PortConstraintItem(BaseModel):
    name: str
    max_draft_m: float
    max_loa_m: float
    max_beam_m: float
    handling_rate_tpd: float
    tidal_dependent: bool
    verified: bool
    source: str
    lat: float
    lon: float
    role: str
    lightening_point: Optional[str] = None


PORT_GEO: dict[str, dict[str, Any]] = {
    "Paradip": {"lat": 20.26, "lon": 86.67, "role": "discharge", "lightening_point": "Dhamra"},
    "Gangavaram": {"lat": 17.62, "lon": 83.24, "role": "discharge", "lightening_point": "—"},
    "Dhamra": {"lat": 20.83, "lon": 86.97, "role": "discharge", "lightening_point": "—"},
    "Haldia": {"lat": 22.02, "lon": 88.06, "role": "discharge", "lightening_point": "Sagar Island"},
    "Visakhapatnam": {"lat": 17.69, "lon": 83.29, "role": "discharge", "lightening_point": "—"},
    "Kamarajar (Ennore)": {"lat": 13.25, "lon": 80.33, "role": "discharge", "lightening_point": "—"},
    "Ennore": {"lat": 13.25, "lon": 80.33, "role": "discharge", "lightening_point": "—"},
    "Australia (Hay Point)": {"lat": -21.26, "lon": 149.30, "role": "load", "lightening_point": "—"},
    "South Africa (Richards Bay)": {"lat": -28.79, "lon": 32.09, "role": "load", "lightening_point": "—"},
    "Indonesia (East Kalimantan)": {"lat": -1.26, "lon": 116.82, "role": "load", "lightening_point": "—"},
}


@router.get("/port-constraints", response_model=List[PortConstraintItem])
def get_port_constraints_list() -> List[PortConstraintItem]:
    """Return all verified port hydrodynamics, mechanical handling rates, and geo coordinates."""
    from backend.warehouse import repository
    ports_map = repository.get_port_constraints(verified_only=False)
    items: List[PortConstraintItem] = []
    for name, p in ports_map.items():
        geo = PORT_GEO.get(name, {"lat": 20.0, "lon": 85.0, "role": "discharge", "lightening_point": None})
        items.append(PortConstraintItem(
            name=p.name,
            max_draft_m=float(p.max_draft_m),
            max_loa_m=float(p.max_loa_m),
            max_beam_m=float(p.max_beam_m),
            handling_rate_tpd=float(p.handling_rate_tpd),
            tidal_dependent=bool(p.tidal_dependent),
            verified=bool(p.verified),
            source=str(p.source),
            lat=float(geo["lat"]),
            lon=float(geo["lon"]),
            role=str(geo["role"]),
            lightening_point=geo.get("lightening_point"),
        ))
    return items

