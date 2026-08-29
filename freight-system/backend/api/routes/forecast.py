"""
api/routes/forecast.py — GET /forecast

Thin pass-through to forecasting.get_forecast().
DOC3 §FEATURE: API Layer.
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException, Query

from backend.api.schemas import ForecastResponse
from backend.engine import forecasting
from backend.engine.forecasting import ForecastUnavailableError

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/forecast", response_model=ForecastResponse)
def get_forecast(
    route: str = Query(..., description="Route string, e.g. 'Hay Point, Australia→Paradip, India'"),
    vessel_class: str = Query(..., description="Vessel class, e.g. 'Panamax'"),
    horizon_days: int = Query(..., ge=1, le=90, description="Forecast horizon in days"),
) -> ForecastResponse:
    """
    Return the latest gated ForecastObject for a (route, vessel_class, horizon_days) triple.
    Raises 404 if no gated forecast has been trained yet for this pair.
    ConditionsMonitor runs inside get_forecast() at read time — may serve damped_trend.
    """
    try:
        fc = forecasting.get_forecast(
            route=route,
            vessel_class=vessel_class,
            horizon_days=horizon_days,
        )
    except ForecastUnavailableError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("forecasting.get_forecast() raised an unexpected error")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    # Deserialise JSON fields stored as text in the ORM model
    confidence_band = fc.confidence_band_dict() if hasattr(fc, "confidence_band_dict") else {}
    trajectory      = fc.trajectory_list()      if hasattr(fc, "trajectory_list")      else []

    return ForecastResponse(
        route=fc.route,
        vessel_class=fc.vessel_class,
        horizon_days=fc.horizon_days,
        generated_at=fc.generated_at,
        point_estimate=fc.point_estimate,
        confidence_band=confidence_band,
        trajectory=trajectory,
        driver_explanation=fc.driver_explanation,
        is_high_uncertainty=fc.is_high_uncertainty,
        model_used=fc.model_used,
        provenance=getattr(fc, "provenance", "modeled"),
    )
