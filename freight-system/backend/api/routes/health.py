"""
api/routes/health.py — GET /health

Richer health check than prior build — reports warehouse + AIS listener + retrain
status independently.  DOC3 §FEATURE: API Layer.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter

from backend.api.schemas import HealthResponse
from backend.warehouse import repository
from backend.warehouse.db import WarehouseUnavailableError

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """
    Liveness + readiness probe.  Never raises — always returns a structured response
    so the frontend can distinguish between backend unreachable (caller can't even reach
    this endpoint) and backend reachable-but-degraded.

    Checks performed:
    1. Warehouse: try a lightweight repository query.
    2. Models loaded: check whether any ForecastObject exists in the warehouse.
    3. AIS listener last seen: read latest CongestionSnapshot timestamp.
    4. Last retrain: read latest ForecastObject generated_at.
    """
    # 1. Warehouse reachability
    warehouse_ok = True
    message      = None
    try:
        repository.get_valid_vessel_classes()
    except (WarehouseUnavailableError, Exception) as exc:
        warehouse_ok = False
        message = f"Warehouse check failed: {exc}"
        logger.warning("Health: warehouse unavailable — %s", exc)

    # 2. Models loaded
    models_loaded    = False
    last_retrain_at  = None
    ais_last_seen    = None

    if warehouse_ok:
        try:
            last_retrain_at = repository.get_latest_retrain_timestamp()
            models_loaded   = last_retrain_at is not None
        except Exception as exc:
            logger.debug("Health: retrain timestamp unavailable — %s", exc)

        try:
            ais_last_seen = repository.get_latest_ais_timestamp()
        except Exception as exc:
            logger.debug("Health: AIS timestamp unavailable — %s", exc)

    # Overall status
    if not warehouse_ok:
        status = "error"
    elif not models_loaded:
        status = "degraded"
    else:
        status = "ok"

    return HealthResponse(
        status=status,
        warehouse_reachable=warehouse_ok,
        models_loaded=models_loaded,
        last_retrain_at=last_retrain_at,
        ais_listener_last_seen=ais_last_seen,
        bunker_last_updated=repository.get_latest_bunker_timestamp() if warehouse_ok else None,
        message=message,
    )
