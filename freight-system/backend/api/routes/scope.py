"""
api/routes/scope.py — GET /scope

NEW per DOC2 Addendum v3 §A1: data-driven scope query.
Returns the live set of verified origins / dest_ports / vessel_classes from the
warehouse — this is the single source of truth the dashboard form dropdowns AND
schemas.py validation both read from.  Hardcoded lists removed.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from backend.api.schemas import ScopeResponse
from backend.warehouse import repository

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/scope", response_model=ScopeResponse)
def get_scope() -> ScopeResponse:
    """
    Return the live verified scope (origins, dest_ports, vessel_classes).
    Empty lists on cold start — not an error (DOC3 Edge Cases: cold start returns
    empty lists, dashboard renders "nothing available yet").
    Results cached in repository for SCOPE_CATALOG_CACHE_TTL_SECONDS.
    """
    try:
        origins        = repository.get_valid_origins()
        dest_ports     = repository.get_valid_dest_ports()
        vessel_classes = repository.get_valid_vessel_classes()
    except Exception as exc:
        logger.exception("Repository read failed in /scope")
        raise HTTPException(status_code=503, detail=f"Warehouse unavailable: {exc}") from exc

    return ScopeResponse(
        origins=sorted(origins),
        dest_ports=sorted(dest_ports),
        vessel_classes=sorted(vessel_classes),
    )
