"""
api/routes/scenario.py — POST /scenario

Pinned what-if query — voyage_count and commitment_mode REQUIRED.
Same underlying decision.solve() call as /recommendation.
DOC3 §FEATURE: API Layer.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from backend.api.routes.recommendation import (
    _build_overrides,
    _serialise_strategy,
    _validate_scope,
)
from backend.api.schemas import RecommendationResponse, ScenarioRequest
from backend.engine import decision

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/scenario", response_model=RecommendationResponse)
def get_scenario(req: ScenarioRequest) -> RecommendationResponse:
    """
    Pinned what-if scenario — same engine call as /recommendation,
    but voyage_count and commitment_mode are required (user is pinning both).
    Schema-level conflict validation (force_mode vs commitment_mode) is in
    ScenarioRequest.check_mode_override_conflict().
    """
    _validate_scope(req)
    overrides = _build_overrides(req.constraints)

    try:
        best, comparisons = decision.solve(
            cargo_quantity=req.cargo_quantity,
            origin_port=req.origin_port,
            discharge_ports=req.discharge_ports,
            timing_flexibility_days=req.timing_flexibility_days,
            commitment_benchmark_pct=req.commitment_benchmark_pct,
            constraints=overrides,
        )
    except Exception as exc:
        logger.exception("decision.solve() raised an unexpected error in /scenario")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return RecommendationResponse(
        recommendation=_serialise_strategy(best),
        scenario_comparison=[_serialise_strategy(s) for s in comparisons],
    )
