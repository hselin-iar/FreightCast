"""
api/routes/compatible_vessels.py — GET /compatible-vessels

Thin pass-through to constraint.check_feasibility().
CARRIED OVER call, unchanged from prior build per DOC3.
"""
from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, HTTPException, Query

from backend.api.schemas import CompatibleVesselsResponse
from backend.engine import constraint
from backend.warehouse import repository

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/compatible-vessels", response_model=List[CompatibleVesselsResponse])
def get_compatible_vessels(
    cargo_quantity: float = Query(..., gt=0, description="Cargo size in metric tonnes"),
    discharge_ports: List[str] = Query(..., description="One or more discharge port names"),
) -> List[CompatibleVesselsResponse]:
    """
    Return feasibility results for every (port, vessel_class) combination
    that the warehouse currently has verified constraints for.
    Uses constraint.check_feasibility() — never re-derives draft/LOA/beam rules here.
    """
    try:
        port_constraints = repository.get_port_constraints()
        vessel_specs     = repository.get_vessel_specs()
    except Exception as exc:
        logger.exception("Repository read failed in /compatible-vessels")
        raise HTTPException(status_code=503, detail=f"Warehouse unavailable: {exc}") from exc

    feasible_opts = constraint.check_feasibility(
        cargo_quantity=cargo_quantity,
        discharge_ports=discharge_ports,
        port_constraints=port_constraints,
        vessel_specs=vessel_specs,
    )

    return [
        CompatibleVesselsResponse(
            discharge_port=opt.port,
            vessel_class=opt.vessel_class,
            is_feasible=opt.is_feasible,
            requires_lightening=opt.requires_lightening,
            lightening_port=opt.lightening_port,
            inefficient_fit=opt.inefficient_fit,
            discharge_days=opt.discharge_days,
            tidal_window_note=opt.tidal_window_note,
            infeasibility_reason=opt.infeasibility_reason,
        )
        for opt in feasible_opts
    ]
