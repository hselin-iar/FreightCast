"""
engine/cost_terms.py — Cost Terms Module.

DOC3 §FEATURE: Cost Terms Module (REINVENTED)
DOC2 §5.6 / §10 / §11.7

STATUS: REINVENTED — not carried over from prior build. See DOC3 for why.

This module computes the MILP's objective cost coefficient for every candidate
(voyage, vessel, port, τ, mode, scenario) combination. It produces ONLY arithmetic
— no I/O, no warehouse queries, no model calls. All inputs arrive via caller
(decision.py), who resolves data from the warehouse before calling here.

ARCHITECTURE:
  build_cost_coefficient() is the one function decision.py calls.
  The seven sub-functions (spot_freight_cost, locked_freight_cost, bunker_cost,
  port_handling_cost, waiting_cost, tax_cost, lightening_penalty_cost,
  repositioning_cost) are individually unit-testable and individually tagged with
  their provenance quality.

CRITICAL CORRECTNESS INVARIANT (DOC3 explicit, DOC4 flagged high-risk):
  locked_freight_cost uses `base_rate_at_lock_day` — the BASE scenario rate at
  the chosen lock day — regardless of which scenario s the caller is computing C_s for.
  A locked voyage's cost is IDENTICAL across Base/Optimistic/Pessimistic evaluations.
  Violating this would make locked voyages look artificially risk-sensitive in the
  robustness readout. decision.py is responsible for passing the same base_rate_at_lock_day
  to all three scenario evaluations; this function enforces nothing about that, which is
  exactly why the critical test plan (DOC3 §TESTING PLAN) asserts it explicitly.

PROVENANCE TAGS (DOC2 §5.10 honesty standard):
  "measured"  — freight rate from forecasting pipeline; bunker price from live feed
  "modeled"   — bunker consumption computed from real physics (distance x consumption)
  "assumed"   — tax/waiting/port-day-rate/lightening placeholders (UNVERIFIED constants)

ANTI-DRIFT GUARD (DOC4 Step 7):
  Do NOT add a 6th cost bucket — repositioning folds into the "bunker" bucket.
  Do NOT fold tax/waiting into the freight bucket.
  Do NOT compute discharge_days here — reuse Rule 5 output (discharge_days from FeasibleOption).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal, Optional

from backend.engine.provenance import Provenance, tag_assumed, tag_measured, tag_modeled

from backend.config.constants import (
    DEFAULT_BALLAST_SPEED_KNOTS,
    PORT_HANDLING_DAY_RATE_USD,
    WAITING_COST_PER_DAY_USD,
    TAX_RATE_PCT,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# RoutePhysics — typed data carrier
# Populated by repository.get_route_physics(origin, destination).
# Defined here (not in models.py) because cost_terms.py is its only consumer
# at this build step; decision.py will import it from here for Step 8.
# ---------------------------------------------------------------------------

@dataclass
class RoutePhysics:
    """
    Real physics data for an (origin, destination) route pair.
    Sourced from the warehouse route_physics table (tagged provenance="measured").
    DOC2 Addendum v3 §A2.
    
    Extended with step50b research pipeline fields:
      daily_opex_usd      — crew, maintenance, insurance per day (per-class benchmark)
      other_voyage_cost_usd — port dues, canal tolls, pilotage (per-route total)
    """
    origin:                   str
    destination:              str
    distance_nm:              float   # nautical miles, measured
    laden_consumption_tpd:    float   # tonnes/day, laden leg
    ballast_consumption_tpd:  float   # tonnes/day, ballast return leg
    speed_knots:              float = DEFAULT_BALLAST_SPEED_KNOTS  # default if not stored per-route
    # ── step50b research pipeline additions ────────────────────────────────
    daily_opex_usd:           float = 8_500.0   # USD/day — Capesize benchmark default
    other_voyage_cost_usd:    float = 0.0        # port dues + canal tolls + pilotage


# ---------------------------------------------------------------------------
# CostBreakdown — output of build_cost_coefficient()
# Five buckets per DOC2 §11.7 — shape stays fixed regardless of repositioning.
# ---------------------------------------------------------------------------

@dataclass
class CostBreakdown:
    """
    7-bucket cost breakdown per (voyage, vessel, port, τ, mode, scenario).
    Exactly what the dashboard's stacked bar and WhyNotComparator render.
    DOC2 §11.7.

    New in this version (step50b parity):
      opex       — daily vessel operating cost × voyage days ("modeled" provenance)
      other_cost — port dues, canal tolls, pilotage ("assumed" until route data available)

    repositioning_cost folds into `bunker` (still bunker fuel, different leg).
    tax and waiting are kept separate with their own "assumed" provenance tag.

    provenance: overall tag for the highest-uncertainty term in this breakdown.
    """
    ocean_freight:    float    # spot_freight_cost or locked_freight_cost
    bunker:           float    # bunker_cost (laden+ballast) + repositioning_cost
    opex:             float    # daily_opex_usd × voyage_days  (step50b)
    other_cost:       float    # port dues + canal tolls + pilotage  (step50b)
    port_handling:    float    # port_handling_cost
    lightening_extra: float    # lightening_penalty_cost (0.0 when no lightening)
    tax:              float    # tax_cost
    waiting:          float    # waiting_cost (0.0 when no idle days — consistent zero)
    total:            float    # sum of all buckets
    provenance:       Provenance                # "assumed" if placeholder constants dominate
    provenance_note:  Optional[str] = None     # populated when provenance=="assumed"


# ---------------------------------------------------------------------------
# Sub-functions (pure arithmetic — no I/O)
# ---------------------------------------------------------------------------

def spot_freight_cost(quantity: float, rate: float) -> float:
    """
    Rule: quantity × rate.
    `rate` is the scenario path's point estimate at the specific τ being evaluated —
    resolved by decision.py before calling this. Pure one-liner for testability.

    Provenance of result: "modeled" (rate comes from forecasting pipeline).
    """
    return quantity * rate


def locked_freight_cost(
    quantity: float,
    base_rate_at_lock_day: float,
    commitment_benchmark_pct: float,
) -> float:
    """
    Rule: quantity × base_rate_at_lock_day × (1 - commitment_benchmark_pct / 100)

    CRITICAL: `base_rate_at_lock_day` MUST be the BASE scenario's rate at the lock day,
    regardless of which scenario s the caller is evaluating C_s for. A locked voyage's
    cost is IDENTICAL across all three scenario evaluations — that is what "locked" means.

    commitment_benchmark_pct = 0 → degenerates to quantity × base_rate_at_lock_day exactly.
    No error, no NaN.

    Provenance: "modeled" (base rate comes from forecasting pipeline).
    """
    discount_factor = 1.0 - commitment_benchmark_pct / 100.0
    return quantity * base_rate_at_lock_day * discount_factor


def bunker_cost(
    route_physics: RoutePhysics,
    laden: bool,
    bunker_price_usd_per_tonne: float,
) -> float:
    """
    Distance-based physics — not a flat placeholder.

    Rule:
      consumption_tpd = laden_consumption_tpd if laden else ballast_consumption_tpd
      voyage_days     = distance_nm / speed_knots / 24
      cost            = consumption_tpd × voyage_days × bunker_price_usd_per_tonne

    speed_knots uses route_physics.speed_knots (defaults to DEFAULT_BALLAST_SPEED_KNOTS
    when not stored per-route).

    Raises ValueError if distance_nm <= 0 — that is a data error, not a business outcome.
    Provenance: "modeled" (real physics over real distance).
    """
    if route_physics.distance_nm <= 0:
        raise ValueError(
            f"bunker_cost: RoutePhysics for {route_physics.origin!r} → "
            f"{route_physics.destination!r} has invalid distance_nm="
            f"{route_physics.distance_nm}. This is a data error."
        )
    consumption_tpd = (
        route_physics.laden_consumption_tpd
        if laden
        else route_physics.ballast_consumption_tpd
    )
    voyage_days = route_physics.distance_nm / route_physics.speed_knots / 24.0
    return consumption_tpd * voyage_days * bunker_price_usd_per_tonne


def port_handling_cost(quantity: float, handling_rate_tpd: float) -> float:
    """
    Rule: (quantity / handling_rate_tpd) × PORT_HANDLING_DAY_RATE_USD

    Reuses the same discharge-duration logic as constraint.py's Rule 5 — do NOT
    recompute discharge days independently. Caller may pass FeasibleOption.discharge_days
    directly as (quantity / handling_rate_tpd) pre-computed, or pass both separately.

    handling_rate_tpd = 0 → returns 0.0 (same guard as Rule 5).
    Provenance: "assumed" (PORT_HANDLING_DAY_RATE_USD is a placeholder constant).
    """
    if handling_rate_tpd <= 0.0:
        return 0.0
    discharge_days = quantity / handling_rate_tpd
    return discharge_days * PORT_HANDLING_DAY_RATE_USD


def waiting_cost(idle_days: float) -> float:
    """
    Rule: idle_days × WAITING_COST_PER_DAY_USD

    idle_days = 0 → returns exactly 0.0 (consistent zero, shows as $0 line in breakdown,
    not a missing value). Never returns None.

    Provenance: "assumed" (WAITING_COST_PER_DAY_USD is a placeholder constant).
    """
    return idle_days * WAITING_COST_PER_DAY_USD


def tax_cost(freight_or_quantity: float, effective_freight_rate: Optional[float] = None) -> float:
    """
    Rule: freight_cost × (TAX_RATE_PCT / 100)

    Supports both:
      - 1 arg:  tax_cost(freight_cost)
      - 2 args: tax_cost(quantity, effective_freight_rate)

    FIX (Bug 4): When called from build_cost_coefficient with 1 arg (freight_cost),
    tax is computed on the EFFECTIVE freight cost (post-discount for locked voyages,
    full cost for spot voyages). This ensures tax / ocean_freight == TAX_RATE_PCT / 100
    in the cost breakdown.

    Provenance: "assumed" (TAX_RATE_PCT is an UNVERIFIED placeholder per DOC2 §12).
    """
    if effective_freight_rate is not None:
        freight_cost = freight_or_quantity * effective_freight_rate
    else:
        freight_cost = freight_or_quantity
    return freight_cost * (TAX_RATE_PCT / 100.0)


def lightening_penalty_cost(
    requires_lightening: bool,
    lightening_penalty_days: float,
) -> float:
    """
    Rule: lightening_penalty_days × PORT_HANDLING_DAY_RATE_USD
    (lightening call priced as extra port days, same day-rate as ordinary port handling)

    Returns 0.0 when requires_lightening is False — "not applicable ≠ free" edge case:
    the 0.0 still appears in the breakdown so it's visibly accounted for.

    Provenance: "assumed" (PORT_HANDLING_DAY_RATE_USD is a placeholder).
    """
    if not requires_lightening:
        return 0.0
    return lightening_penalty_days * PORT_HANDLING_DAY_RATE_USD


def repositioning_cost(
    ballast_consumption_tpd: Optional[float],
    repositioning_days: Optional[float],
    bunker_price_usd_per_tonne: float,
) -> float:
    """
    Ballast fuel cost during repositioning leg.
    DOC2 §11.2/§11.4, v3 Final.

    Rule: ballast_consumption_tpd × repositioning_days × bunker_price_usd_per_tonne

    If EITHER input is None (no real AIS position data grounds this class/route —
    fallback mode), returns exactly 0.0 — NOT an error. This is the expected common
    path for vessel classes outside current MyShipTracking coverage.

    Distinct from the RoutePhysics case (bunker_cost ValueError) — that is a data
    bug; this is a designed graceful fallback.

    Provenance: "assumed" when returning 0.0 (fallback); "modeled" when computed.
    """
    if ballast_consumption_tpd is None or repositioning_days is None:
        return 0.0
    return ballast_consumption_tpd * repositioning_days * bunker_price_usd_per_tonne


def opex_cost(route_physics: RoutePhysics) -> float:
    """
    Daily vessel operating expense × total voyage days (laden leg only).
    Research pipeline: step50b → daily_opex_usd × total_voyage_days.

    voyage_days = distance_nm / speed_knots / 24 (same as bunker_cost's denominator)
    Includes port days as a proxy (loaded leg + typical port time).
    Ballast return leg OPEX is NOT included — consistent with step50b which charges
    opex only for the contracted voyage, not the reposition.

    Provenance: "modeled" — per-class benchmark rates sourced from step50b dataset.
    Returns 0.0 if daily_opex_usd is not set (graceful fallback for old rows).
    """
    if not route_physics.daily_opex_usd or route_physics.distance_nm <= 0:
        return 0.0
    voyage_days = route_physics.distance_nm / route_physics.speed_knots / 24.0
    return route_physics.daily_opex_usd * voyage_days


def other_voyage_cost(route_physics: RoutePhysics) -> float:
    """
    Fixed other voyage costs: port dues, canal tolls, pilotage.
    Sourced from route_physics.other_voyage_cost_usd (per-route total).
    Research pipeline: step50b → other_voyage_cost_usd.

    Provenance: "assumed" until real port-tariff data replaces the placeholder.
    Returns 0.0 when field is None/0 (graceful fallback).
    """
    return float(route_physics.other_voyage_cost_usd or 0.0)


# ---------------------------------------------------------------------------
# build_cost_coefficient — the orchestrator
# Called once per (voyage, vessel, port, τ, mode, scenario) by decision.py
# ---------------------------------------------------------------------------

def build_cost_coefficient(
    quantity:                    float,
    mode:                        Literal["spot", "locked"],
    rate_at_tau:                 float,
    base_rate_at_lock_day:       float,
    commitment_benchmark_pct:    float,
    route_physics:               RoutePhysics,
    bunker_price_usd_per_tonne:  float,
    handling_rate_tpd:           float,
    idle_days:                   float,
    requires_lightening:         bool,
    lightening_penalty_days:     float,
    repositioning_days:          Optional[float] = None,
    ballast_consumption_tpd:     Optional[float] = None,
) -> CostBreakdown:
    """
    Orchestrate all sub-functions into a single CostBreakdown per
    (voyage, vessel, port, τ, mode, scenario).

    This is the function decision.py calls when constructing the MILP's
    objective coefficients. Called once per candidate combination before the solve.

    7-bucket layout (extended from 5 to include step50b OPEX parity):
      1. ocean_freight   — spot or locked (see CRITICAL INVARIANT above for locked)
      2. bunker          — laden + ballast physics + repositioning (same fuel, folded in)
      3. opex            — daily_opex_usd × voyage_days (step50b addition)
      4. other_cost      — port dues, canal tolls, pilotage (step50b addition)
      5. port_handling   — discharge days × day-rate
      6. lightening_extra — extra port call if lightening required (0.0 otherwise)
      7. tax             — separate bucket, stays "assumed", never folded into freight
      (waiting is a separate tracked term, not a named "bucket" per DOC2 §11.7 but
       included in breakdown for transparency; total includes it)

    Provenance: OPEX is now "modeled" (per-class benchmarks from research pipeline).
    Tax/waiting/port-day-rate remain "assumed" (placeholder constants).
    """
    # 1. Ocean freight
    if mode == "spot":
        freight = spot_freight_cost(quantity, rate_at_tau)
    else:  # "locked"
        # CRITICAL: always pass base_rate_at_lock_day — never rate_at_tau for locked mode
        freight = locked_freight_cost(quantity, base_rate_at_lock_day, commitment_benchmark_pct)

    # 2. Bunker — laden leg (from origin to discharge port)
    laden_bunker = bunker_cost(route_physics, laden=True, bunker_price_usd_per_tonne=bunker_price_usd_per_tonne)
    # Ballast return leg
    ballast_bunker = bunker_cost(route_physics, laden=False, bunker_price_usd_per_tonne=bunker_price_usd_per_tonne)
    # Repositioning (folds into bunker bucket — still bunker fuel)
    repo_cost = repositioning_cost(
        ballast_consumption_tpd=ballast_consumption_tpd,
        repositioning_days=repositioning_days,
        bunker_price_usd_per_tonne=bunker_price_usd_per_tonne,
    )
    bunker_total = laden_bunker + ballast_bunker + repo_cost

    # 3. OPEX — daily operating cost × voyage days (step50b research pipeline addition)
    opex = opex_cost(route_physics)

    # 4. Other voyage costs — port dues, canal tolls, pilotage (step50b addition)
    other = other_voyage_cost(route_physics)

    # 5. Port handling
    port_cost = port_handling_cost(quantity, handling_rate_tpd)

    # 6. Lightening extra
    lightening_cost = lightening_penalty_cost(requires_lightening, lightening_penalty_days)

    # 7. Tax — computed on EFFECTIVE freight cost (post-discount) for consistency
    #    tax / ocean_freight == TAX_RATE_PCT / 100 exactly in the breakdown
    tax = tax_cost(freight)

    # Waiting (transparency line — included in total)
    waiting = waiting_cost(idle_days)

    total = freight + bunker_total + opex + other + port_cost + lightening_cost + tax + waiting

    # Provenance: "assumed" — tax/waiting/port-day-rate use placeholder constants.
    # OPEX is now "modeled" (per-class benchmarks), but tax remains "assumed" so
    # overall provenance stays "assumed" until all placeholder constants are resolved.
    prov, prov_note = tag_assumed(
        "TAX_RATE_PCT and PORT_HANDLING_DAY_RATE_USD are placeholder constants "
        "pending real port-tariff data; bunker/freight/opex terms are measured/modeled."
    )

    return CostBreakdown(
        ocean_freight=round(freight, 2),
        bunker=round(bunker_total, 2),
        opex=round(opex, 2),
        other_cost=round(other, 2),
        port_handling=round(port_cost, 2),
        lightening_extra=round(lightening_cost, 2),
        tax=round(tax, 2),
        waiting=round(waiting, 2),
        total=round(total, 2),
        provenance=prov,
        provenance_note=prov_note,
    )


# ---------------------------------------------------------------------------
# SailKillEconomics — Step 51V Incremental Sail vs Kill Framework
# ---------------------------------------------------------------------------

@dataclass
class SailKillEconomics:
    """
    Per-candidate (vessel, port, τ, mode) economic summary using the Step 51V
    Bear / Base / Bull framework from freight_optimization/code/step51v_final_production_milp.py.

    The MILP objective maximises worst_incremental across selected candidates.
    The risk constraint guarantees worst_incremental ≥ RISK_RATIO × base_incremental.

    ARCHITECTURE:
        sail_value[scen]    = freight_revenue[scen]  - voyage_cost[scen]
        kill_value          = cargo_qty × spot_rate_base × kill_benchmark_pct
        incremental[scen]   = sail_value[scen] - kill_value

    kill_value uses BASE scenario spot rate — the rate SAIL would achieve by
    immediately re-selling the cargo slot on the spot market. It is scenario-
    invariant: the kill alternative is always evaluated at the current market
    price, not the Bear or Bull projection.
    """

    # ── Per-scenario freight revenues (cargo_qty × contract_rate[scen]) ──────
    bear_freight_revenue: float   # bear = pessimistic scenario rate
    base_freight_revenue: float   # base = most-likely scenario rate
    bull_freight_revenue: float   # bull = optimistic scenario rate

    # ── Per-scenario total voyage costs ──────────────────────────────────────
    bear_voyage_cost: float
    base_voyage_cost: float
    bull_voyage_cost: float

    # ── Net sail value per scenario (revenue - cost) ──────────────────────────
    bear_sail: float
    base_sail: float
    bull_sail: float

    # ── Kill-value baseline ───────────────────────────────────────────────────
    # What SAIL earns by NOT sailing — selling the cargo on the spot market.
    kill_value: float

    # ── Incremental per scenario (sail - kill) ────────────────────────────────
    bear_incremental: float    # usually the binding constraint
    base_incremental: float
    bull_incremental: float

    # ── MILP aggregates ───────────────────────────────────────────────────────
    worst_incremental:    float   # min(bear, base, bull) — MILP objective coefficient
    expected_incremental: float   # 0.25*bear + 0.50*base + 0.25*bull — weighted avg


def build_sail_kill_economics(
    cargo_quantity: float,
    bear_voyage_cost: float,
    base_voyage_cost: float,
    bull_voyage_cost: float,
    bear_rate: float,
    base_rate: float,
    bull_rate: float,
    spot_rate_base: float,
    kill_benchmark_pct: float = 1.0,
) -> SailKillEconomics:
    """
    Compute Sail vs Kill incremental economics for one candidate.

    Transplanted from freight_optimization step51v / step51k methodology.
    This is a pure arithmetic function — no I/O, no warehouse calls.

    Args:
        cargo_quantity:       tonnes to be shipped
        bear/base/bull_voyage_cost: total voyage cost from build_cost_coefficient()
                              for each scenario
        bear/base/bull_rate:  forecasted freight rate ($/MT) for each scenario
        spot_rate_base:       current base-scenario spot rate ($/MT) used for kill value
        kill_benchmark_pct:   fraction of spot_rate_base used as kill floor
                              (1.0 = SAIL gives up full spot-market income by sailing)

    Returns:
        SailKillEconomics with all fields populated.
    """
    # Freight revenues per scenario
    bear_rev = cargo_quantity * bear_rate
    base_rev = cargo_quantity * base_rate
    bull_rev = cargo_quantity * bull_rate

    # Net sail values per scenario
    bear_sail = bear_rev - bear_voyage_cost
    base_sail = base_rev - base_voyage_cost
    bull_sail = bull_rev - bull_voyage_cost

    # Kill value: what SAIL earns by walking away (always base scenario spot rate)
    kill_val = cargo_quantity * spot_rate_base * kill_benchmark_pct

    # Incrementals
    bear_inc = bear_sail - kill_val
    base_inc = base_sail - kill_val
    bull_inc = bull_sail - kill_val

    # MILP objective coefficient: minimize downside — worst = minimum across scenarios
    worst_inc = min(bear_inc, base_inc, bull_inc)

    # Expected: weighted mean (bear=25%, base=50%, bull=25%) — matches step51v weighting
    expected_inc = 0.25 * bear_inc + 0.50 * base_inc + 0.25 * bull_inc

    return SailKillEconomics(
        bear_freight_revenue=round(bear_rev, 2),
        base_freight_revenue=round(base_rev, 2),
        bull_freight_revenue=round(bull_rev, 2),
        bear_voyage_cost=round(bear_voyage_cost, 2),
        base_voyage_cost=round(base_voyage_cost, 2),
        bull_voyage_cost=round(bull_voyage_cost, 2),
        bear_sail=round(bear_sail, 2),
        base_sail=round(base_sail, 2),
        bull_sail=round(bull_sail, 2),
        kill_value=round(kill_val, 2),
        bear_incremental=round(bear_inc, 2),
        base_incremental=round(base_inc, 2),
        bull_incremental=round(bull_inc, 2),
        worst_incremental=round(worst_inc, 2),
        expected_incremental=round(expected_inc, 2),
    )
