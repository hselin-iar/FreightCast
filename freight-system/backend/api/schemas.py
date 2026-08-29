"""
api/schemas.py — Request / Response contracts for all six API routes.

DOC3 §FEATURE: API Layer
DOC2 §5.7

DESIGN PRINCIPLES (from DOC3):
  - schemas.py validates: cargo_quantity > 0, discharge_ports subset of
    repository.get_valid_dest_ports() (SCOPE_CATALOG_CACHE_TTL_SECONDS cache,
    NOT a hardcoded constant per DOC2 Addendum v3 §A1).
  - constraints object fields validated against the same live scope (e.g.
    exclude_vessel entries must be currently-valid vessel classes) — invalid
    overrides never silently produce an empty "no solution" response when the
    real cause is a typo.
  - All fields that carry provenance in the engine layer surface the tag here
    too (ForecastResponse, StrategyResponse, CostBreakdownResponse).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Shared sub-schemas
# ---------------------------------------------------------------------------

class HumanOverridesRequest(BaseModel):
    """
    Human-override constraints applied as MILP variable-fixing before the solve.
    DOC2 §11.5.  Validated against live scope by route handler before reaching
    decision.py — a bad vessel class produces a 422, not a silent empty result.
    """
    allow_vessel:       Optional[List[str]] = Field(None, description="Allow ONLY these vessel classes (e.g. ['Capesize'])")
    require_vessel:     Optional[str]       = Field(None, description="Require this single vessel class (e.g. 'Capesize')")
    exclude_vessel:     Optional[List[str]] = Field(None, description="Vessel classes to exclude")
    require_port:       Optional[str]       = Field(None, description="Force discharge to this port only")
    max_completion_day: Optional[int]       = Field(None, ge=1, description="Latest τ day allowed")
    force_mode:         Optional[Literal["spot", "locked"]] = Field(None, description="Lock commitment mode")
    min_fix_day:        Optional[int]       = Field(None, ge=0, description="Earliest τ day allowed")


class CostBreakdownResponse(BaseModel):
    """7-bucket cost breakdown per DOC2 §11.7 (extended with step50b OPEX)."""
    ocean_freight:    float
    bunker:           float
    opex:             float = 0.0          # daily_opex_usd × voyage_days
    other_cost:       float = 0.0          # port dues, canal tolls, pilotage
    port_handling:    float
    lightening_extra: float
    risk_buffer:      float
    total:            float
    provenance:       str
    provenance_note:  Optional[str] = None


class VoyageDetailResponse(BaseModel):
    """Per-voyage assignment within a Strategy."""
    port:               str
    vessel_class:       str
    mode:               Literal["spot", "locked"]
    fix_day:            int
    cost_by_scenario:   Dict[str, float]
    lightening_required: bool
    lightening_port:    Optional[str]
    discharge_days:     float
    tidal_window_note:  Optional[str]
    # step51k sail value fields
    cargo_tonnes:         float = 0.0
    freight_revenue_usd:  float = 0.0
    net_sail_value_usd:   float = 0.0


class StrategyResponse(BaseModel):
    """
    A complete freight strategy returned by /recommendation or /scenario.
    Includes provenance tags on all top-level fields per DOC3 §FEATURE Provenance.
    """
    voyage_count:                   int
    commitment_mode:                str
    voyages:                        List[VoyageDetailResponse]
    total_cost_worst_case:          float
    cost_breakdown:                 Dict[str, float]
    contains_high_uncertainty_voyage: bool
    solved_via:                     Literal["milp", "hybrid_fallback"]
    provenance:                     str
    provenance_note:                Optional[str] = None
    infeasible_reason:              Optional[str] = None
    # step51k sail value fields
    total_freight_revenue_usd:      float = 0.0
    total_net_sail_value_usd:       float = 0.0
    incremental_vs_kill_usd:        float = 0.0


# ---------------------------------------------------------------------------
# POST /recommendation
# ---------------------------------------------------------------------------

class RecommendationRequest(BaseModel):
    """
    Cargo recommendation request.  DOC3 §FEATURE: API Layer.
    discharge_ports and origin_port are validated against live scope at request time.
    """
    cargo_quantity:           float = Field(..., gt=0, description="Cargo size in metric tonnes")
    origin_port:              str   = Field(..., min_length=2, description="Origin port name")
    discharge_ports:          List[str] = Field(..., min_length=1, description="One or more discharge ports")
    timing_flexibility_days:  int   = Field(..., ge=1, le=90, description="How many days the fix date can flex")
    commitment_benchmark_pct: Optional[float] = Field(
        None, ge=50.0, le=100.0,
        description=(
            "Assumed locked-rate discount vs spot (user-set). "
            "Default: 95%. Adjust based on current market negotiations."
        ),
    )
    voyage_count:     Optional[int]  = Field(None, ge=1, le=3, description="Pin voyage count (for /scenario)")
    commitment_mode:  Optional[Literal["spot", "locked", "mixed"]] = Field(
        None, description="Pin commitment mode (for /scenario)"
    )
    constraints: Optional[HumanOverridesRequest] = Field(
        None, description="Human overrides — applied as MILP variable-fixing"
    )

    @model_validator(mode="after")
    def discharge_ports_nonempty(self) -> "RecommendationRequest":
        if not self.discharge_ports:
            raise ValueError("discharge_ports must contain at least one port")
        return self


class RecommendationResponse(BaseModel):
    recommendation:       StrategyResponse
    scenario_comparison:  List[StrategyResponse]


# ---------------------------------------------------------------------------
# POST /scenario  (pinned what-if query — same body, stricter validation)
# ---------------------------------------------------------------------------

class ScenarioRequest(RecommendationRequest):
    """
    Pinned what-if scenario — voyage_count and commitment_mode are REQUIRED.
    DOC3: /scenario always calls the same decision.solve() as /recommendation.
    """
    voyage_count:    int  = Field(..., ge=1, le=3)
    commitment_mode: Literal["spot", "locked", "mixed"] = Field(...)

    @model_validator(mode="after")
    def check_mode_override_conflict(self) -> "ScenarioRequest":
        """
        Detect commitment_mode / force_mode conflict — 422 naming the conflict,
        not silently letting one win.  DOC3 Edge Cases.
        """
        if (
            self.constraints
            and self.constraints.force_mode
            and self.commitment_mode
            and self.constraints.force_mode != self.commitment_mode
        ):
            raise ValueError(
                f"Conflict: constraints.force_mode={self.constraints.force_mode!r} "
                f"contradicts commitment_mode={self.commitment_mode!r}. "
                "Resolve by aligning them or removing one."
            )
        return self


# ---------------------------------------------------------------------------
# GET /forecast
# ---------------------------------------------------------------------------

class ForecastResponse(BaseModel):
    route:              str
    vessel_class:       str
    horizon_days:       int
    generated_at:       datetime
    point_estimate:     float
    confidence_band:    Dict[str, float]      # {"lower": float, "upper": float}
    trajectory:         List[Dict[str, Any]]  # [{date, value}, ...]
    driver_explanation: Optional[str]
    is_high_uncertainty: bool
    model_used:         str
    provenance:         str


# ---------------------------------------------------------------------------
# GET /compatible-vessels
# ---------------------------------------------------------------------------

class CompatibleVesselsResponse(BaseModel):
    discharge_port:  str
    vessel_class:    str
    is_feasible:     bool
    requires_lightening: bool
    lightening_port: Optional[str]
    inefficient_fit: bool
    discharge_days:  float
    tidal_window_note: Optional[str]
    infeasibility_reason: Optional[str]


# ---------------------------------------------------------------------------
# GET /port-status
# ---------------------------------------------------------------------------

class PortStatusResponse(BaseModel):
    port:                str
    vessel_count:        int
    avg_wait_hours:      float
    recorded_at:         Optional[datetime]
    is_live:             bool
    source_note:         Optional[str]
    bunker_price_usd:    Optional[float]
    provenance:          str   # "measured" if live AIS, "assumed" if seeded fallback


# ---------------------------------------------------------------------------
# GET /scope  (DOC2 Addendum v3 §A1 — data-driven scope, no hardcoded lists)
# ---------------------------------------------------------------------------

class ScopeResponse(BaseModel):
    origins:        List[str]
    dest_ports:     List[str]
    vessel_classes: List[str]


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    status:                 Literal["ok", "degraded", "error"]
    warehouse_reachable:    bool
    models_loaded:          bool
    last_retrain_at:        Optional[datetime]
    ais_listener_last_seen: Optional[datetime]
    message:                Optional[str] = None


# ---------------------------------------------------------------------------
# POST /chat — Chatbot (Build Step 13)
# ANTHROPIC_API_KEY is held server-side in this route only — never shipped to
# the Vercel/React build.  DOC3 §FEATURE: Chatbot.
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    """Single message in the rolling conversation window."""
    role:    Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    """
    Stateless chat request — caller ships the full conversation_history so the
    server holds zero session state (no SSE/websocket needed for MVP).

    cargo_context carries the last cargo_request the dashboard submitted, so the
    chatbot can resolve follow-up references without asking the manager to restate
    cargo/origin/destination (DOC2 §3c step 1).
    """
    message:              str             = Field(..., min_length=1, description="The latest user message")
    conversation_history: List[ChatMessage] = Field(
        default_factory=list,
        max_length=40,
        description="Rolling window of prior turns (user + assistant), oldest first",
    )
    cargo_context: Optional[RecommendationRequest] = Field(
        None,
        description=(
            "The cargo_request most recently submitted via the dashboard form. "
            "Lets the chatbot resolve follow-up constraint changes without re-asking "
            "for cargo/origin/destination. Absent on the very first message."
        ),
    )


class ChatResponse(BaseModel):
    """
    Chatbot reply.

    `reply`           — plain-language assistant message for the chat bubble.
    `tool_called`     — True when a /recommendation (or /forecast) tool call was
                        made during this turn; False for clarification or follow-ups
                        that only reused cached context.
    `updated_recommendation` — Populated when the tool call produced a *new* solve
                        (i.e. a constraint-change re-solve, DOC2 §3c step 3). The
                        frontend uses this to update the open RecommendationPage
                        with the new plan + a \"changed because you asked\" annotation.
                        None when the tool call repeated the same request unchanged.
    `constraint_note` — Human-readable description of the constraints that drove
                        the re-solve (e.g. \"no Capesize, ≤12 days\"). Displayed as
                        the \"changed because you asked\" annotation in the dashboard.
    `conversation_history` — Updated history to echo back to the client so the next
                        request can include it.
    """
    reply:                   str
    tool_called:             bool
    updated_recommendation:  Optional[RecommendationResponse] = None
    constraint_note:         Optional[str]                    = None
    conversation_history:    List[ChatMessage]
