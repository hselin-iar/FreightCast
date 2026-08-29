"""
api/routes/recommendation.py — POST /recommendation

Thin pass-through: parse → validate scope → call decision.solve() → shape response.
No business logic in this handler per DOC3 §FEATURE: API Layer.
"""
from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, HTTPException

from backend.api.schemas import (
    HumanOverridesRequest,
    RecommendationRequest,
    RecommendationResponse,
    StrategyResponse,
    VoyageDetailResponse,
)
from backend.engine import decision
from backend.engine.decision import HumanOverrides, Strategy
from backend.warehouse import repository

router = APIRouter()
logger = logging.getLogger(__name__)


def _normalize_vessel_name(raw: str, valid_vessels: List[str]) -> Optional[str]:
    """Match a vessel class alias (e.g. 'Cape Max', 'Panamax') to canonical scope."""
    raw_clean = raw.strip()
    matched = next((v for v in valid_vessels if v.lower() == raw_clean.lower()), None)
    if matched:
        return matched
    low = raw_clean.lower().replace(" ", "").replace("-", "").replace("/", "")
    if "cape" in low:
        return next((v for v in valid_vessels if "capesize" in v.lower()), None)
    elif "panamax" in low or "kamsarmax" in low:
        return next((v for v in valid_vessels if "panamax" in v.lower() or "kamsarmax" in v.lower()), None)
    elif "supra" in low or "ultra" in low or "super" in low:
        return next((v for v in valid_vessels if "supramax" in v.lower() or "ultramax" in v.lower()), None)
    return None


def _validate_scope(req: RecommendationRequest) -> None:
    """
    Validate request fields against the live warehouse scope.
    Normalizes aliases and omits non-scope exclusions gracefully.
    """
    valid_origins  = repository.get_valid_origins()
    valid_ports    = repository.get_valid_dest_ports()
    valid_vessels  = repository.get_valid_vessel_classes() or ["Capesize", "Panamax/Kamsarmax", "Supramax/Ultramax"]

    if valid_origins and req.origin_port not in valid_origins:
        matched_o = next((o for o in valid_origins if o.lower() in req.origin_port.lower() or req.origin_port.lower() in o.lower()), None)
        if matched_o:
            req.origin_port = matched_o
        else:
            raise HTTPException(
                status_code=422,
                detail=f"origin_port {req.origin_port!r} not in verified scope. "
                       f"Valid origins: {sorted(valid_origins)}",
            )

    normalized_ports = []
    for p in req.discharge_ports:
        matched_p = next((vp for vp in valid_ports if vp.lower() in p.lower() or p.lower() in vp.lower()), None)
        if matched_p:
            normalized_ports.append(matched_p)
        elif valid_ports and p not in valid_ports:
            raise HTTPException(
                status_code=422,
                detail=f"discharge_port {p!r} not in verified scope. "
                       f"Valid ports: {sorted(valid_ports)}",
            )
        else:
            normalized_ports.append(p)
    req.discharge_ports = normalized_ports

    if req.constraints:
        # 1. Normalize require_vessel
        if req.constraints.require_vessel:
            rv = _normalize_vessel_name(req.constraints.require_vessel, valid_vessels)
            if rv:
                req.constraints.require_vessel = rv
            else:
                raise HTTPException(
                    status_code=422,
                    detail=f"constraints.require_vessel {req.constraints.require_vessel!r} not in verified scope. "
                           f"Valid vessel classes: {sorted(valid_vessels)}",
                )

        # 2. Normalize allow_vessel
        if req.constraints.allow_vessel:
            norm_allow = []
            for av in req.constraints.allow_vessel:
                m = _normalize_vessel_name(av, valid_vessels)
                if m:
                    norm_allow.append(m)
            req.constraints.allow_vessel = list(dict.fromkeys(norm_allow)) or None

        # 3. Normalize exclude_vessel (raise 422 if an unknown class name is passed)
        if req.constraints.exclude_vessel:
            norm_exclude = []
            bad_vessels = []
            for ev in req.constraints.exclude_vessel:
                m = _normalize_vessel_name(ev, valid_vessels)
                if m:
                    norm_exclude.append(m)
                else:
                    bad_vessels.append(ev)
            if bad_vessels and valid_vessels:
                raise HTTPException(
                    status_code=422,
                    detail=f"constraints.exclude_vessel {bad_vessels} not in verified scope. "
                           f"Valid vessel classes: {sorted(valid_vessels)}",
                )
            req.constraints.exclude_vessel = list(dict.fromkeys(norm_exclude)) or None

        # 4. Normalize require_port
        if req.constraints.require_port and valid_ports:
            matched_rp = next((vp for vp in valid_ports if vp.lower() == req.constraints.require_port.lower() or vp.lower() in req.constraints.require_port.lower()), None)
            if matched_rp:
                req.constraints.require_port = matched_rp
            elif req.constraints.require_port not in valid_ports:
                raise HTTPException(
                    status_code=422,
                    detail=f"constraints.require_port {req.constraints.require_port!r} "
                           f"not in verified scope. Valid ports: {sorted(valid_ports)}",
                )


def _build_overrides(c: HumanOverridesRequest | None) -> HumanOverrides | None:
    if c is None:
        return None
    return HumanOverrides(
        allow_vessel=c.allow_vessel,
        require_vessel=c.require_vessel,
        exclude_vessel=c.exclude_vessel,
        require_port=c.require_port,
        max_completion_day=c.max_completion_day,
        force_mode=c.force_mode,
        min_fix_day=c.min_fix_day,
    )


def _serialise_strategy(s: Strategy) -> StrategyResponse:
    voyages = [
        VoyageDetailResponse(
            port=v.port,
            vessel_class=v.vessel_class,
            mode=v.mode,
            fix_day=v.fix_day,
            cost_by_scenario=v.cost_by_scenario,
            lightening_required=v.lightening_required,
            lightening_port=v.lightening_port,
            discharge_days=v.discharge_days,
            tidal_window_note=v.tidal_window_note,
            cargo_tonnes=v.cargo_tonnes,
            freight_revenue_usd=v.freight_revenue_usd,
            net_sail_value_usd=v.net_sail_value_usd,
        )
        for v in s.voyages
    ]
    return StrategyResponse(
        voyage_count=s.voyage_count,
        commitment_mode=s.commitment_mode,
        voyages=voyages,
        total_cost_worst_case=s.total_cost_worst_case,
        cost_breakdown=s.cost_breakdown,
        contains_high_uncertainty_voyage=s.contains_high_uncertainty_voyage,
        solved_via=s.solved_via,
        provenance=s.provenance,
        provenance_note=s.provenance_note,
        infeasible_reason=s.infeasible_reason,
        total_freight_revenue_usd=s.total_freight_revenue_usd,
        total_net_sail_value_usd=s.total_net_sail_value_usd,
        incremental_vs_kill_usd=s.incremental_vs_kill_usd,
    )


@router.post("/recommendation", response_model=RecommendationResponse)
def get_recommendation(req: RecommendationRequest) -> RecommendationResponse:
    """
    Main chartering recommendation endpoint.
    Calls decision.solve() after scope validation; returns ranked Strategy +
    scenario_comparison list.  Latency is solver-bound (up to
    MILP_SOLVE_TIMEOUT_SECONDS) — frontend must show a loading state.
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
        logger.exception("decision.solve() raised an unexpected error")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return RecommendationResponse(
        recommendation=_serialise_strategy(best),
        scenario_comparison=[_serialise_strategy(s) for s in comparisons],
    )
