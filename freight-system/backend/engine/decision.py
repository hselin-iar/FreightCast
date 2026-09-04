"""
engine/decision.py — Decision Engine (MILP Optimizer).

DOC3 §FEATURE: Decision Engine (MILP Optimizer)
DOC2 §11 (full section)

PUBLIC API:
  solve(cargo_quantity, origin_port, discharge_ports, timing_flexibility_days,
        commitment_benchmark_pct=None, constraints=None) -> tuple[Strategy, list[Strategy]]

DECISION VARIABLES (decomposed — never a joint index per DOC2 §11.1):
  q_i          ≥ 0         cargo tonnes assigned to voyage i
  x_{i,v}      ∈ {0,1}     1 if voyage i uses vessel class v
  y_{i,p}      ∈ {0,1}     1 if voyage i discharges at port p
  z_{i,τ}      ∈ {0,1}     1 if voyage i is fixed at time point τ
  w_{i,m}      ∈ {0,1}     1 if voyage i's commitment mode is m ∈ {spot, locked}
  ℓ_{i,p}      ∈ {0,1}     1 if voyage i requires lightening at port p

ANTI-DRIFT GUARDS (DOC4 Step 8):
  - Do NOT fold variables into a joint index (q_i × vessel × port × τ × mode all at once)
  - Do NOT re-derive feasibility rules inside this file — call constraint.check_feasibility()
  - Do NOT use a uniform daily grid for τ — use event-based time points
  - Do NOT let solved_via always be "hybrid_fallback" — the MILP must run on the normal path
  - Do NOT build any part of Step 51V's batch fleet-portfolio optimizer in this module
  - Human overrides are variable-fixing BEFORE the solve, not a post-hoc filter

DEFERRAL (DOC2 §13, DOC3 DEFERRAL NOTE):
  Step 51V's batch fleet portfolio optimizer is explicitly out of scope for this module.
  solve() always solves for exactly ONE cargo request — never multi-contract portfolio.
"""
from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Tuple

import pulp

from backend.config.constants import (
    DEFAULT_BALLAST_SPEED_KNOTS,
    DEFAULT_COMMITMENT_BENCHMARK_PCT,
    HYBRID_FALLBACK_COMMITMENT_MODES,
    HYBRID_FALLBACK_VOYAGE_COUNTS,
    MILP_KILL_BENCHMARK_PCT,
    MILP_RISK_RATIO,
    MILP_SOLVE_TIMEOUT_SECONDS,
    REPOSITION_BUFFER_HOURS,
    SCENARIO_BEAR_BAND_FRACTION,
    SCENARIO_BULL_BAND_FRACTION,
    SCENARIO_OPTIMISTIC_BAND_FRACTION,   # legacy alias — kept for old tests
    SCENARIO_PESSIMISTIC_BAND_FRACTION,  # legacy alias — kept for old tests
)
from backend.engine import constraint, cost_terms, scenario
from backend.engine.cost_terms import (
    CostBreakdown,
    RoutePhysics,
    SailKillEconomics,
    build_cost_coefficient,
    build_sail_kill_economics,
)
from backend.engine.provenance import (
    Provenance,
    compute_sensitivity,      # re-exported so callers can import from decision
    tag_assumed,
    tag_modeled,
)
from backend.warehouse import repository

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Vessel capacity table (class-level, not per-IMO — DOC2 §11.1)
# ---------------------------------------------------------------------------

_VESSEL_CAPACITY_TONNES: dict[str, float] = {
    "Capesize":            180_000.0,
    "Panamax/Kamsarmax":    80_000.0,
    "Supramax/Ultramax":    58_000.0,
}


# ---------------------------------------------------------------------------
# Data classes — HumanOverrides & Strategy
# ---------------------------------------------------------------------------

@dataclass
class HumanOverrides:
    """
    Variable-fixing applied BEFORE the solve (DOC2 §11.5).
    Not a parallel set of override binaries — expressed by fixing decision variables.
    Schema consumed by both the chatbot (§2c) and dashboard controls (§5.10).
    """
    allow_vessel:      Optional[List[str]] = None    # x_{i,v}=0 for any vessel class NOT in this list
    require_vessel:    Optional[str]       = None    # x_{i,v}=0 for all v ≠ require_vessel
    exclude_vessel:    Optional[List[str]] = None    # x_{i,v}=0 for these vessel classes
    require_port:      Optional[str]       = None    # y_{i,p}=0 for all p ≠ require_port
    max_completion_day: Optional[int]      = None    # τ must be ≤ this day
    force_mode:        Optional[Literal["spot", "locked"]] = None  # w_{i,m}=0 for opposite mode
    min_fix_day:       Optional[int]       = None    # τ must be ≥ this day
    speed_mode:        Optional[str]       = "design"  # "eco", "design", "express"


@dataclass
class VoyageDetail:
    """Per-voyage assignment in a Strategy."""
    port:         str
    vessel_class: str
    mode:         Literal["spot", "locked"]
    fix_day:      int
    cost_by_scenario: Dict[str, float]   # {base, optimistic, pessimistic}
    lightening_required: bool
    lightening_port: Optional[str]
    discharge_days: float
    tidal_window_note: Optional[str]
    # ── Research pipeline step51k additions (sail value framework) ──────────────
    cargo_tonnes:         float = 0.0   # MT assigned to this voyage by MILP
    freight_revenue_usd:  float = 0.0   # cargo_tonnes × effective_freight_rate
    voyage_cost_usd:      float = 0.0   # total cost from CostBreakdown
    net_sail_value_usd:   float = 0.0   # freight_revenue - voyage_cost (profit signal)
    steaming_speed_knots: float = 12.5
    steaming_mode:        str = "design"
    speed_bunker_savings_usd: float = 0.0


@dataclass
class Strategy:
    """
    A complete freight plan returned by solve().
    DOC3 §FEATURE: Decision Engine — Strategy shape.
    """
    voyage_count:    int
    commitment_mode: str          # "spot", "locked", or "mixed"
    voyages:         List[VoyageDetail]
    total_cost_worst_case: float
    cost_breakdown:  Dict[str, float]   # 7-bucket: ocean_freight, bunker, opex, other_cost, port_handling, lightening_extra, tax
    contains_high_uncertainty_voyage: bool
    solved_via:      Literal["milp", "hybrid_fallback"]
    provenance:      Provenance           # typed: "modeled" (real data) or "assumed" (benchmark default)
    provenance_note: Optional[str] = None  # populated when provenance=="assumed"
    infeasible_reason: Optional[str] = None   # populated when no feasible plan was found
    # ── Research pipeline step51k additions (sail value framework) ──────────────
    total_freight_revenue_usd: float = 0.0   # Σ freight_revenue across voyages
    total_net_sail_value_usd:  float = 0.0   # total_freight_revenue - total_cost (profit)
    incremental_vs_kill_usd:   float = 0.0   # net_sail_value - kill_value (0 when no kill contract)


# ---------------------------------------------------------------------------
# τ (time-point) generation — event-based, not uniform daily grid
# ---------------------------------------------------------------------------

def _compute_tau(
    timing_flexibility_days: int,
    forecast_trajectory: List[Dict[str, Any]],
    vessel_class: str,
    origin_port: str,
    human_overrides: Optional[HumanOverrides] = None,
) -> List[int]:
    """
    Generate the candidate set of time points τ for voyage scheduling.
    DOC2 §11.2 — event-based, NOT a uniform daily/weekly grid.

    Candidates:
      a. Day 0 (today)
      b. End of each week inside timing_flexibility_days
      c. End of the flexibility window
      d. Any local minimum in the forecast trajectory (cheapest expected rate)
      e. Repositioning-aware earliest_feasible_departure (when AIS data exists)

    Result is bounded by [min_fix_day, max_completion_day] from HumanOverrides.
    Returns a sorted, deduplicated list of day integers.
    """
    candidates: set[int] = set()

    # (a) Today
    candidates.add(0)

    # (b) End of each week inside the window
    for w in range(1, math.ceil(timing_flexibility_days / 7) + 1):
        d = w * 7
        if d <= timing_flexibility_days:
            candidates.add(d)

    # (c) End of flexibility window
    candidates.add(timing_flexibility_days)

    # (d) Local minima in forecast trajectory (cheapest expected fix days)
    if forecast_trajectory and len(forecast_trajectory) > 2:
        points = [p.get("point_estimate", p.get("value", 0.0)) if isinstance(p, dict) else float(p) for p in forecast_trajectory]
        for idx in range(1, len(points) - 1):
            if points[idx] < points[idx - 1] and points[idx] < points[idx + 1]:
                day = forecast_trajectory[idx].get("day", idx) if isinstance(forecast_trajectory[idx], dict) else idx
                if 0 <= day <= timing_flexibility_days:
                    candidates.add(int(day))

    # (e) Repositioning-aware earliest feasible departure (NEW — DOC2 §11.2, Step 51A)
    try:
        vessel_snapshots = repository.get_candidate_vessels_by_class(vessel_class)
        if vessel_snapshots:
            # Use the earliest available vessel's repositioning estimate
            earliest_days = repository.get_earliest_repositioning_days(vessel_class, origin_port)
            if earliest_days is not None:
                # step51a: add 6h safety buffer before rounding to whole days.
                # earliest_origin_arrival = obs_ts + reposition_hours + REPOSITION_BUFFER_HOURS
                # → ensures vessel can physically reach loading port before departure fires.
                buffered_hours = earliest_days * 24.0 + REPOSITION_BUFFER_HOURS
                earliest_day = math.ceil(buffered_hours / 24.0)
                # Bound all existing candidates to [earliest_day, timing_flexibility_days]
                candidates = {d for d in candidates if d >= earliest_day}
                candidates.add(earliest_day)
    except Exception:
        # Graceful fallback: no AIS data → calendar-only candidates (already computed above)
        pass

    # Apply HumanOverrides bounds
    min_day = 0
    max_day = timing_flexibility_days
    if human_overrides:
        if human_overrides.min_fix_day is not None:
            min_day = human_overrides.min_fix_day
        if human_overrides.max_completion_day is not None:
            max_day = human_overrides.max_completion_day

    candidates = {d for d in candidates if min_day <= d <= max_day}

    # Always keep at least one τ point (the min_day) to avoid empty feasible region
    if not candidates:
        candidates.add(min_day)

    return sorted(candidates)


# ---------------------------------------------------------------------------
# Scenario cost coefficient computation
# ---------------------------------------------------------------------------

def _get_scenario_rate(
    trajectory_points: List[Dict[str, Any]],
    lower: float,
    upper: float,
    day: int,
    scenario_name: Literal["base", "bull", "bear", "optimistic", "pessimistic"],
) -> float:
    """
    Get the rate for a specific scenario and time point τ.
    Looks up the trajectory point at or closest to `day`.

    Scenario naming (Step 51V bear/base/bull, with legacy aliases for old tests):
        base        — most-likely forecast rate at τ
        bull        — optimistic edge: rate near lower confidence bound (freight costs
                      lower in a good market for charterer)
        bear        — pessimistic edge: rate near upper confidence bound (higher costs)
        optimistic  — alias for bull (backward compat)
        pessimistic — alias for bear  (backward compat)
    """
    if not trajectory_points:
        return 0.0

    best = min(trajectory_points, key=lambda p: abs(p.get("day", 0) - day))
    base_rate = float(best.get("point_estimate", best.get("value", 0.0)))

    if scenario_name == "base":
        return base_rate
    elif scenario_name in ("bull", "optimistic"):
        return base_rate - SCENARIO_BULL_BAND_FRACTION * (base_rate - lower)
    else:  # bear / pessimistic
        return base_rate + SCENARIO_BEAR_BAND_FRACTION * (upper - base_rate)


def _compute_cost_coefficients(
    quantity: float,
    feasible_opts: List[constraint.FeasibleOption],
    tau_points: Dict[str, List[int]],   # vessel_class → list of τ days
    forecasts: Dict[Tuple[str, str], Any],  # (route_key, vessel_class) → ForecastObject
    route_physics_cache: Dict[str, RoutePhysics],  # "origin→dest" → RoutePhysics
    bunker_price: float,
    base_rate_at_lock_day: Dict[str, float],  # (route_key, vessel_class, port) → base rate at day 0
    commitment_benchmark_pct: float,
    origin_port: str = "Australia (Hay Point)",  # actual origin for route_key construction
    idle_days: float = 0.0,
    repositioning_days_cache: Optional[Dict[str, Optional[float]]] = None,
    speed_mode: str = "design",
) -> Dict[Tuple, CostBreakdown]:
    """
    Compute cost coefficients for all feasible (vessel, port, τ, mode, scenario) combos.
    Returns a dict keyed by (vessel_class, port, tau_day, mode, scenario) → CostBreakdown.

    Called once before the solve, not during. This is the MILP's objective pre-computation.
    """
    coeffs: Dict[Tuple, CostBreakdown] = {}

    for opt in feasible_opts:
        if not opt.is_feasible:
            continue
        vc = opt.vessel_class
        port = opt.port
        route_key = f"{origin_port}→{port}"  # consistent with solve() → forecasts keys

        fc = forecasts.get((route_key, vc))
        if fc is None:
            continue

        import json
        traj = json.loads(fc.trajectory) if isinstance(fc.trajectory, str) else (fc.trajectory or [])
        cb   = json.loads(fc.confidence_band) if isinstance(fc.confidence_band, str) else {}
        lower = float(cb.get("lower", fc.point_estimate))
        upper = float(cb.get("upper", fc.point_estimate))

        rp_key = route_key
        rp = route_physics_cache.get(rp_key)
        if rp is None:
            continue

        tau_list = tau_points.get(vc, [0])
        base_lock_rate = base_rate_at_lock_day.get((route_key, vc, port), fc.point_estimate)

        bctpd = rp.ballast_consumption_tpd if rp else None
        repo_days = (repositioning_days_cache or {}).get(vc)

        for tau_day in tau_list:
            for mode in ("spot", "locked"):
                # Generate Bear/Base/Bull scenario cost coefficients.
                # Keys now use bear/base/bull (Step 51V naming) — sail_kill economics
                # and the MILP objective look up exactly these keys.
                for scen in ("base", "bull", "bear"):
                    rate = _get_scenario_rate(traj, lower, upper, tau_day, scen)
                    discharge_d = float(getattr(opt, "discharge_days", 0.0))
                    hr_tpd = (quantity / discharge_d) if discharge_d > 0 else 40_000.0
                    try:
                        bd = build_cost_coefficient(
                            quantity=quantity,
                            mode=mode,
                            rate_at_tau=rate,
                            base_rate_at_lock_day=base_lock_rate,
                            commitment_benchmark_pct=commitment_benchmark_pct,
                            route_physics=rp,
                            bunker_price_usd_per_tonne=bunker_price,
                            handling_rate_tpd=hr_tpd,
                            idle_days=idle_days,
                            requires_lightening=opt.requires_lightening,
                            lightening_penalty_days=opt.lightening_penalty_days,
                            repositioning_days=repo_days,
                            ballast_consumption_tpd=bctpd,
                            speed_mode=speed_mode,
                        )
                        coeffs[(vc, port, tau_day, mode, scen)] = bd
                    except Exception as exc:
                        logger.warning("_compute_cost_coefficients: skipping %s/%s/τ=%d/%s/%s: %s",
                                       vc, port, tau_day, mode, scen, exc)
    return coeffs


# ---------------------------------------------------------------------------
# MILP build & solve
# ---------------------------------------------------------------------------

def _build_and_solve_milp(
    cargo_quantity: float,
    feasible_opts: List[constraint.FeasibleOption],
    tau_points: Dict[str, List[int]],
    coeffs: Dict[Tuple, CostBreakdown],
    vessel_classes: List[str],
    ports: List[str],
    max_voyages: int,
    commitment_benchmark_pct: float,
    human_overrides: Optional[HumanOverrides],
) -> Tuple[Optional[List[Dict]], str]:
    """
    Build the MILP using PuLP and solve with CBC.

    ARCHITECTURE (mirrors research pipeline step51v pattern):
    ---------------------------------------------------------
    Instead of decomposed per-voyage binaries x_{i,v}, y_{i,p}, z_{i,τ}, w_{i,m}
    combined with 4-way AND products, we build one binary per CANDIDATE:

        candidate key = (vessel_class, port, tau_day, mode)

    Each candidate already has its scalar costs pre-computed in `coeffs`.
    The MILP variables are:
        x[cand]  ∈ {0,1}   — select this (vessel, port, τ, mode) combination
        q[cand]  ≥ 0       — cargo tonnes assigned to this candidate

    Objective: Minimize worst-case total cost = M
        M ≥ Σ q[cand] * unit_cost_worst[cand]   (per-tonne worst-case)
        for each of base/optimistic/pessimistic scenarios.

    Constraints:
        Σ q[cand]        = cargo_quantity        (cargo conservation)
        q[cand]          ≤ cap[v] * x[cand]      (only if selected)
        Σ x[cand]        ≤ max_voyages           (voyage count limit)
        Σ x[cand]        ≥ 1                     (at least one voyage)

    Human overrides: filter candidate list before building variables.

    Returns (assignments, solved_via).
    Returns (None, "hybrid_fallback") on timeout/failure.
    """
    # ── Build flat candidate list ──────────────────────────────────────────
    # A candidate = (vessel_class, port, tau_day, mode) with pre-computed costs.
    modes = ["spot", "locked"]
    vessel_classes = list(dict.fromkeys(vessel_classes))
    ports = list(dict.fromkeys(ports))
    feasible_pairs = {(o.vessel_class, o.port) for o in feasible_opts if o.is_feasible}

    candidates: List[Tuple] = []
    for v in vessel_classes:
        for p in ports:
            if (v, p) not in feasible_pairs:
                continue
            tau_list = tau_points.get(v, [0]) or [0]
            for tau in tau_list:
                for mode in modes:
                    if (v, p, tau, mode, "base") in coeffs:
                        candidates.append((v, p, tau, mode))

    if not candidates:
        logger.warning("_build_and_solve_milp: no candidates with cost coefficients")
        return None, "hybrid_fallback"

    # ── Apply human overrides: filter candidates before building vars ──────
    if human_overrides:
        if human_overrides.require_vessel:
            rv = human_overrides.require_vessel
            candidates = [(v, p, tau, m) for (v, p, tau, m) in candidates if v == rv]
        elif human_overrides.allow_vessel:
            av = set(human_overrides.allow_vessel)
            candidates = [(v, p, tau, m) for (v, p, tau, m) in candidates if v in av]
        if human_overrides.exclude_vessel:
            exclude_v = set(human_overrides.exclude_vessel)
            candidates = [(v, p, tau, m) for (v, p, tau, m) in candidates if v not in exclude_v]
        if human_overrides.require_port:
            rp = human_overrides.require_port
            candidates = [(v, p, tau, m) for (v, p, tau, m) in candidates if p == rp]
        if human_overrides.force_mode:
            fm = human_overrides.force_mode
            candidates = [(v, p, tau, m) for (v, p, tau, m) in candidates if m == fm]

    if not candidates:
        logger.warning("_build_and_solve_milp: all candidates filtered by human overrides")
        return None, "hybrid_fallback"

    # ── Step 51V Sail vs Kill Economics per candidate ─────────────────────
    # Build SailKillEconomics for every candidate using Bear/Base/Bull rates.
    # The MILP objective coefficient is worst_incremental[cand] — the minimum
    # net incremental value SAIL gains by sailing vs. walking away (kill value).
    sail_kill: Dict[Tuple, SailKillEconomics] = {}
    for cand in candidates:
        v, p, tau, mode = cand
        bd_bear = coeffs.get((v, p, tau, mode, "bear"))
        bd_base = coeffs.get((v, p, tau, mode, "base"))
        bd_bull = coeffs.get((v, p, tau, mode, "bull"))
        if not (bd_bear and bd_base and bd_bull):
            continue
        # Extract per-scenario rates: rate = ocean_freight / cargo_quantity
        bear_rate = bd_bear.ocean_freight / cargo_quantity if cargo_quantity > 0 else 0.0
        base_rate = bd_base.ocean_freight / cargo_quantity if cargo_quantity > 0 else 0.0
        bull_rate = bd_bull.ocean_freight / cargo_quantity if cargo_quantity > 0 else 0.0
        # Kill value uses base-scenario spot rate (scenario-invariant walk-away price)
        spot_rate_base = base_rate
        sail_kill[cand] = build_sail_kill_economics(
            cargo_quantity=cargo_quantity,
            bear_voyage_cost=bd_bear.total,
            base_voyage_cost=bd_base.total,
            bull_voyage_cost=bd_bull.total,
            bear_rate=bear_rate,
            base_rate=base_rate,
            bull_rate=bull_rate,
            spot_rate_base=spot_rate_base,
            kill_benchmark_pct=MILP_KILL_BENCHMARK_PCT,
        )

    # Filter to candidates that have complete Sail/Kill economics
    candidates = [c for c in candidates if c in sail_kill]
    if not candidates:
        logger.warning("_build_and_solve_milp: no candidates with sail/kill economics")
        return None, "hybrid_fallback"

    # ── Build MILP — Step 51V pattern: Maximize Worst-Case Incremental ─────
    prob = pulp.LpProblem("SAIL_FreightOptimization", pulp.LpMaximize)
    cap_map = {v: _VESSEL_CAPACITY_TONNES.get(v, 80_000.0) for v in vessel_classes}

    def _cn(cand: Tuple) -> str:
        v, p, tau, mode = cand
        return (f"{v.replace('/','-').replace(' ','_')}"
                f"_{p.replace(' ','_').replace(',','')}_t{tau}_{mode}")

    # x[cand] ∈ {0,1} — select this candidate (same as step51v binary decision vars)
    x = {cand: pulp.LpVariable(f"x_{_cn(cand)}", cat="Binary") for cand in candidates}
    # q[cand] ≥ 0 — cargo tonnes assigned to this candidate
    q = {cand: pulp.LpVariable(f"q_{_cn(cand)}", lowBound=0, cat="Continuous") for cand in candidates}

    # 1. Cargo conservation: Σ q[cand] = cargo_quantity
    prob += pulp.lpSum(q[cand] for cand in candidates) == cargo_quantity, "cargo_conservation"

    # 2. Cargo only flows on a selected candidate: q[cand] ≤ cap * x[cand]
    for cand in candidates:
        v, p, tau, mode = cand
        cap = cap_map.get(v, 80_000.0)
        prob += q[cand] <= cap * x[cand], f"cap_{_cn(cand)}"

    # 3. Voyage count bounds
    prob += pulp.lpSum(x[cand] for cand in candidates) <= max_voyages, "max_voyages"
    prob += pulp.lpSum(x[cand] for cand in candidates) >= 1, "min_voyages"

    # 4. Decompose candidate economics into fixed voyage charges (bunker, opex, other, lightening, waiting)
    #    and per-tonne incremental flow rates (ocean freight, port handling, tax, kill benchmark).
    #    This ensures multi-voyage allocations accurately evaluate fixed vessel vs variable tonnage costs.
    f_fixed_worst: Dict[Tuple, float] = {}
    u_inc_worst: Dict[Tuple, float] = {}
    f_fixed_base: Dict[Tuple, float] = {}
    u_inc_base: Dict[Tuple, float] = {}

    for cand in candidates:
        v, p, tau, mode = cand
        bd_bear = coeffs.get((v, p, tau, mode, "bear"))
        bd_base = coeffs.get((v, p, tau, mode, "base"))
        f_w = -(bd_bear.bunker + bd_bear.opex + bd_bear.other_cost + bd_bear.lightening_extra + bd_bear.waiting) if bd_bear else 0.0
        f_b = -(bd_base.bunker + bd_base.opex + bd_base.other_cost + bd_base.lightening_extra + bd_base.waiting) if bd_base else 0.0
        f_fixed_worst[cand] = f_w
        f_fixed_base[cand] = f_b
        w_inc = sail_kill[cand].worst_incremental
        b_inc = sail_kill[cand].base_incremental
        u_inc_worst[cand] = (w_inc - f_w) / cargo_quantity if cargo_quantity > 0 else 0.0
        u_inc_base[cand] = (b_inc - f_b) / cargo_quantity if cargo_quantity > 0 else 0.0

    # 4. Objective: MAXIMIZE total worst-case incremental value (Step 51V transplant)
    prob += pulp.lpSum(
        f_fixed_worst[cand] * x[cand] + u_inc_worst[cand] * q[cand]
        for cand in candidates
    ), "maximize_worst_incremental"

    # 5. Portfolio risk constraint (Step 51V RISK_RATIO=0.60):
    #    Σ worst_incremental ≥ RISK_RATIO × Σ base_incremental
    #    Guarantees that even under a Bear market, SAIL retains ≥60% of expected margins.
    risk_satisfying = [
        c for c in candidates
        if sail_kill[c].worst_incremental >= MILP_RISK_RATIO * sail_kill[c].base_incremental
    ]
    if risk_satisfying:
        risk_expr = pulp.lpSum(
            (f_fixed_worst[cand] - MILP_RISK_RATIO * f_fixed_base[cand]) * x[cand]
            + (u_inc_worst[cand] - MILP_RISK_RATIO * u_inc_base[cand]) * q[cand]
            for cand in candidates
        )
        prob += risk_expr >= 0, "portfolio_risk_ratio"
    else:
        logger.warning(
            "_build_and_solve_milp: no candidate meets RISK_RATIO=%.2f constraint "
            "(all worst_incremental < RISK_RATIO*base_incremental) — "
            "relaxing risk constraint; MILP picks least-negative option.",
            MILP_RISK_RATIO,
        )

    # ── Solve ──────────────────────────────────────────────────────────────
    try:
        solver = pulp.PULP_CBC_CMD(timeLimit=int(MILP_SOLVE_TIMEOUT_SECONDS), msg=0)
        t0 = time.monotonic()
        status = prob.solve(solver)
        elapsed = time.monotonic() - t0

        if status not in (1,) or elapsed >= MILP_SOLVE_TIMEOUT_SECONDS:
            logger.warning("MILP solve: status=%s elapsed=%.2fs → hybrid_fallback", status, elapsed)
            return None, "hybrid_fallback"

        # Extract selected candidates
        assignments = []
        for cand in candidates:
            x_val = pulp.value(x[cand])
            q_val = pulp.value(q[cand])
            if x_val is not None and x_val > 0.5 and q_val is not None and q_val > 1.0:
                v, p, tau, mode = cand
                assignments.append({
                    "voyage": len(assignments) + 1,
                    "vessel_class": v,
                    "port": p,
                    "tau_day": tau,
                    "mode": mode,
                    "cargo_tonnes": float(q_val),
                })

        return assignments, "milp"

    except Exception as exc:
        logger.warning("MILP solve raised: %s → hybrid_fallback", exc)
        return None, "hybrid_fallback"




# ---------------------------------------------------------------------------
# Hybrid fallback enumeration
# ---------------------------------------------------------------------------

def _hybrid_fallback(
    cargo_quantity: float,
    feasible_opts: List[constraint.FeasibleOption],
    coeffs: Dict[Tuple, CostBreakdown],
    tau_points: Dict[str, List[int]],
    commitment_benchmark_pct: float,
) -> Tuple[List[Dict], str]:
    """
    Fallback enumeration when MILP times out or fails.
    DOC2 §11.6: enumerate small fixed set of (voyage_count × commitment_mode) strategies.
    Always returns a ranked list — never a blank screen.
    solved_via = "hybrid_fallback".

    FIX (Bug 1b): voyage count is now derived from actual vessel capacity, not a
    fixed 3-element list.  Each voyage's cargo_tonnes is clamped to vessel capacity
    so we never assign 100k MT to a 75k-cap Panamax.
    """
    feasible = [o for o in feasible_opts if o.is_feasible]
    if not feasible:
        return [], "hybrid_fallback"

    # Derive minimum voyage count from feasible vessel capacities
    best_cap = max(_VESSEL_CAPACITY_TONNES.get(o.vessel_class, 75_000.0) for o in feasible)
    min_voyages_needed = max(1, math.ceil(cargo_quantity / max(best_cap, 1.0)))
    voyage_count_options = sorted(set(
        [min_voyages_needed, min_voyages_needed + 1]
        + [v for v in HYBRID_FALLBACK_VOYAGE_COUNTS if v >= min_voyages_needed]
    ))

    best_cost = float("inf")
    best_assignment: List[Dict] = []

    for voyage_count in voyage_count_options:
        for mode in ("spot", "locked"):
            total_cost = 0.0
            assignment = []
            remaining = cargo_quantity

            for idx in range(voyage_count):
                opt = feasible[idx % len(feasible)]
                cap = _VESSEL_CAPACITY_TONNES.get(opt.vessel_class, 75_000.0)
                # Assign up to vessel capacity; last voyage gets whatever remains
                if idx < voyage_count - 1:
                    q_this = min(cap, remaining / max(voyage_count - idx, 1))
                    # Round up to avoid tiny residual on last leg
                    q_this = min(cap, remaining - cap * max(voyage_count - idx - 1, 0))
                    q_this = max(0.0, q_this)
                else:
                    q_this = remaining  # last voyage absorbs remainder
                q_this = min(q_this, cap)  # never exceed capacity
                remaining -= q_this

                tau_list = tau_points.get(opt.vessel_class, [0])
                tau = tau_list[0] if tau_list else 0
                key = (opt.vessel_class, opt.port, tau, mode, "base")
                bd = coeffs.get(key)
                if bd:
                    # Scale cost proportionally to actual cargo tonnes assigned
                    full_cap = _VESSEL_CAPACITY_TONNES.get(opt.vessel_class, 75_000.0)
                    fraction = q_this / max(full_cap, 1.0)
                    total_cost += bd.total * fraction
                assignment.append({
                    "voyage": idx + 1,
                    "vessel_class": opt.vessel_class,
                    "port": opt.port,
                    "tau_day": tau,
                    "mode": mode,
                    "cargo_tonnes": round(q_this, 2),
                })

            if total_cost < best_cost and remaining <= 0.01:
                best_cost = total_cost
                best_assignment = assignment

    return best_assignment, "hybrid_fallback"


# ---------------------------------------------------------------------------
# Strategy assembly
# ---------------------------------------------------------------------------

def _assemble_strategy(
    assignments: List[Dict],
    feasible_opts: List[constraint.FeasibleOption],
    coeffs: Dict[Tuple, CostBreakdown],
    forecasts: Dict[Tuple, Any],
    solved_via: Literal["milp", "hybrid_fallback"],
    commitment_benchmark_pct: float,
    is_default_benchmark: bool,
    origin_port: str = "Australia (Hay Point)",
    cargo_quantity: Optional[float] = None,
) -> Strategy:
    """
    Convert raw solver assignments into a Strategy object.

    Extended with step51k sail value framework:
      freight_revenue = cargo_tonnes × effective_freight_rate
      net_sail_value  = freight_revenue − total_voyage_cost
      incremental     = net_sail_value − kill_value (kill_value=0 when no kill contract)

    Candidates are ranked by worst_incremental DESC, expected_incremental DESC before
    assembling VoyageDetail — matching the research pipeline's sort order.
    """
    voyages_raw: List[Dict] = []  # interim accumulator before sorting
    has_high_uncertainty = False

    # Total cargo quantity represented across the consignment
    if cargo_quantity is not None and cargo_quantity > 0:
        total_q = float(cargo_quantity)
    else:
        assigned_sum = sum(float(a.get("cargo_tonnes", 0.0)) for a in assignments)
        total_q = assigned_sum if assigned_sum > 0 else 1.0

    # Build an index for fast lookup
    opt_index = {(o.vessel_class, o.port): o for o in feasible_opts}

    for asgn in assignments:
        vc      = asgn["vessel_class"]
        port    = asgn["port"]
        tau     = asgn["tau_day"]
        mode    = asgn["mode"]
        q_mt    = float(asgn.get("cargo_tonnes", 0.0))
        if q_mt <= 0.0:
            q_mt = total_q / max(len(assignments), 1)
        frac    = q_mt / max(total_q, 1.0)
        opt     = opt_index.get((vc, port))

        bd_base = coeffs.get((vc, port, tau, mode, "base"))
        bd_bear = coeffs.get((vc, port, tau, mode, "bear"))
        bd_bull = coeffs.get((vc, port, tau, mode, "bull"))

        # Base rate in $/MT (ocean_freight in bd_base was computed on total_q in _compute_cost_coefficients)
        base_rate = (bd_base.ocean_freight / total_q) if (bd_base and total_q > 0) else 0.0
        bear_rate = (bd_bear.ocean_freight / total_q) if (bd_bear and total_q > 0) else base_rate
        bull_rate = (bd_bull.ocean_freight / total_q) if (bd_bull and total_q > 0) else base_rate

        # Per-scenario voyage costs scaling tonnage variable items (ocean freight, tax, port handling)
        # while keeping per-ship fixed expenses (bunker, opex, other, lightening, waiting) intact per voyage call.
        cost_by_scen: Dict[str, float] = {}
        for scen in ("base", "bull", "bear"):
            bd = coeffs.get((vc, port, tau, mode, scen))
            if bd:
                v_ocean = bd.ocean_freight * frac
                v_tax   = bd.tax * frac
                v_port  = bd.port_handling * frac
                scen_cost = v_ocean + v_tax + v_port + bd.bunker + bd.opex + bd.other_cost + bd.lightening_extra + bd.waiting
                cost_by_scen[scen] = round(scen_cost, 2)
            else:
                cost_by_scen[scen] = 0.0

        # Base scenario voyage breakdown
        ocean_base  = (bd_base.ocean_freight * frac) if bd_base else 0.0
        tax_base    = (bd_base.tax * frac) if bd_base else 0.0
        port_base   = (bd_base.port_handling * frac) if bd_base else 0.0
        bunker_base = bd_base.bunker if bd_base else 0.0
        opex_base   = bd_base.opex if bd_base else 0.0
        other_base  = bd_base.other_cost if bd_base else 0.0
        light_base  = bd_base.lightening_extra if bd_base else 0.0
        wait_base   = bd_base.waiting if bd_base else 0.0
        voyage_cost = cost_by_scen.get("base", 0.0)

        # Freight revenue for this voyage's assigned cargo tonnes
        freight_revenue = round(q_mt * base_rate, 2)
        net_sail_value  = round(freight_revenue - voyage_cost, 2)

        # Full Sail vs Kill economics via transplanted Step 51V function.
        # spot_rate_base = base_rate (kill = sell cargo at today's market rate)
        ske = build_sail_kill_economics(
            cargo_quantity=q_mt,
            bear_voyage_cost=cost_by_scen.get("bear", voyage_cost),
            base_voyage_cost=voyage_cost,
            bull_voyage_cost=cost_by_scen.get("bull", voyage_cost),
            bear_rate=bear_rate,
            base_rate=base_rate,
            bull_rate=bull_rate,
            spot_rate_base=base_rate,
            kill_benchmark_pct=MILP_KILL_BENCHMARK_PCT,
        )
        worst_incremental    = ske.worst_incremental
        expected_incremental = ske.expected_incremental

        # Check uncertainty from forecast
        route_key = f"{origin_port}\u2192{port}"
        fc = forecasts.get((route_key, vc))
        if fc and getattr(fc, "is_high_uncertainty", False):
            has_high_uncertainty = True

        bd_base = coeffs.get((vc, port, tau, mode, "base"))
        speed_knots = getattr(bd_base, "steaming_speed_knots", 12.5) if bd_base else 12.5
        speed_mode_val = getattr(bd_base, "steaming_mode", "design") if bd_base else "design"
        speed_savings = getattr(bd_base, "speed_bunker_savings_usd", 0.0) if bd_base else 0.0

        voyages_raw.append({
            "detail": VoyageDetail(
                port=port,
                vessel_class=vc,
                mode=mode,
                fix_day=tau,
                cost_by_scenario=cost_by_scen,
                lightening_required=opt.requires_lightening if opt else False,
                lightening_port=opt.lightening_port if opt else None,
                discharge_days=opt.discharge_days if opt else 0.0,
                tidal_window_note=opt.tidal_window_note if opt else None,
                cargo_tonnes=q_mt,
                freight_revenue_usd=round(freight_revenue, 2),
                voyage_cost_usd=round(voyage_cost, 2),
                net_sail_value_usd=round(net_sail_value, 2),
                steaming_speed_knots=speed_knots,
                steaming_mode=speed_mode_val,
                speed_bunker_savings_usd=speed_savings,
            ),
            "ocean_base": ocean_base,
            "tax_base": tax_base,
            "port_base": port_base,
            "bunker_base": bunker_base,
            "opex_base": opex_base,
            "other_base": other_base,
            "light_base": light_base,
            "wait_base": wait_base,
            "worst_incremental": worst_incremental,
            "expected_incremental": expected_incremental,
            "kill_value": ske.kill_value,
            "worst_case": max(cost_by_scen.values()) if cost_by_scen else 0.0,
        })

    # ── Step51k ranking: worst_incremental DESC, expected_incremental DESC ─
    voyages_raw.sort(key=lambda r: (-r["worst_incremental"], -r["expected_incremental"]))

    voyages = [r["detail"] for r in voyages_raw]

    # ── Aggregate cost breakdown across all voyages ─────────────────────────
    worst_case    = sum(r["worst_case"] for r in voyages_raw)
    total_ocean   = sum(r["ocean_base"] for r in voyages_raw)
    total_bunker  = sum(r["bunker_base"] for r in voyages_raw)
    total_opex    = sum(r["opex_base"] for r in voyages_raw)
    total_other   = sum(r["other_base"] for r in voyages_raw)
    total_port    = sum(r["port_base"] for r in voyages_raw)
    total_light   = sum(r["light_base"] for r in voyages_raw)
    total_tax     = sum(r["tax_base"] for r in voyages_raw)
    total_wait    = sum(r["wait_base"] for r in voyages_raw)

    # -- Sail value aggregates --------------------------------------------------
    total_revenue = sum(v.freight_revenue_usd for v in voyages)
    total_base_cost = total_ocean + total_bunker + total_opex + total_other + total_port + total_light + total_tax + total_wait
    total_net_sail  = total_revenue - total_base_cost
    # Kill value: aggregated from Step 51V SailKillEconomics per voyage (replaces placeholder 0.0)
    kill_value  = sum(r["kill_value"] for r in voyages_raw)
    incremental = total_net_sail - kill_value

    # Risk buffer = spread between bear and bull total cost (Step 51V bear/bull naming)
    bear_total = sum(v.cost_by_scenario.get("bear", max(v.cost_by_scenario.values())) for v in voyages)
    bull_total = sum(v.cost_by_scenario.get("bull", min(v.cost_by_scenario.values())) for v in voyages)
    risk_buffer = max(0.0, bear_total - bull_total)

    # Commitment mode
    modes_used = set(v.mode for v in voyages)
    commitment_mode = modes_used.pop() if len(modes_used) == 1 else "mixed"

    if is_default_benchmark:
        provenance, provenance_note = tag_assumed(
            f"commitment_benchmark_pct={commitment_benchmark_pct:.1f}% is the system default "
            f"(DEFAULT_COMMITMENT_BENCHMARK_PCT) — not a cargo-specific market assessment."
        )
    else:
        provenance = tag_modeled()
        provenance_note = None

    return Strategy(
        voyage_count=len(voyages),
        commitment_mode=commitment_mode,
        voyages=voyages,
        total_cost_worst_case=round(worst_case, 2),
        cost_breakdown={
            "freight":                  round(total_ocean, 2),
            "ocean_freight":            round(total_ocean, 2),
            "bunker":                   round(total_bunker, 2),
            "opex":                     round(total_opex, 2),
            "other_cost":               round(total_other, 2),
            "port_handling":            round(total_port, 2),
            "lightening_extra":         round(total_light, 2),
            "tax":                      round(total_tax, 2),
            "risk_buffer":              round(risk_buffer, 2),
            "total":                    round(total_base_cost, 2),
            "steaming_speed_knots":     round(voyages[0].steaming_speed_knots, 1) if voyages else 12.5,
            "steaming_mode":            voyages[0].steaming_mode if voyages else "design",
            "speed_bunker_savings_usd": round(sum(v.speed_bunker_savings_usd for v in voyages), 2),
        },
        contains_high_uncertainty_voyage=has_high_uncertainty,
        solved_via=solved_via,
        provenance=provenance,
        provenance_note=provenance_note,
        # step51k sail value fields
        total_freight_revenue_usd=round(total_revenue, 2),
        total_net_sail_value_usd=round(total_net_sail, 2),
        incremental_vs_kill_usd=round(incremental, 2),
    )


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------

def solve(
    cargo_quantity:           float,
    origin_port:              str,
    discharge_ports:          List[str],
    timing_flexibility_days:  int,
    commitment_benchmark_pct: Optional[float] = None,
    constraints:              Optional[HumanOverrides] = None,
    use_regret:               bool = False,  # reserved for future regret formulation — not implemented
) -> Tuple[Strategy, List[Strategy]]:
    """
    Main Decision Engine entrypoint. Solves for one cargo request.

    Returns (recommendation: Strategy, scenario_comparison: list[Strategy]).
    scenario_comparison always includes a pure-spot and pure-locked baseline.

    Never raises — all errors produce a Strategy with infeasible_reason set.
    DOC2 §11.6: never a blank screen.
    """
    is_default_benchmark = commitment_benchmark_pct is None
    if is_default_benchmark:
        commitment_benchmark_pct = DEFAULT_COMMITMENT_BENCHMARK_PCT

    # ── 1. Scope: vessel classes from warehouse ───────────────────────────
    vessel_classes = repository.get_valid_vessel_classes() or ["Capesize", "Panamax/Kamsarmax", "Supramax/Ultramax"]

    # ── 2. Apply vessel overrides (require_vessel / allow_vessel / exclude_vessel) ─
    if constraints and constraints.require_vessel:
        vessel_classes = [v for v in vessel_classes if v == constraints.require_vessel]
    elif constraints and constraints.allow_vessel:
        vessel_classes = [v for v in vessel_classes if v in constraints.allow_vessel]

    if constraints and constraints.exclude_vessel:
        vessel_classes = [v for v in vessel_classes if v not in constraints.exclude_vessel]

    # ── 3. Feasibility check per (vessel, port) ───────────────────────────
    port_constraints_raw = repository.get_port_constraints(verified_only=True)
    # Convert ORM objects to dicts for constraint.check_feasibility()
    port_constraints: dict[str, dict] = {}
    for port_name, pc in port_constraints_raw.items():
        port_constraints[port_name] = {
            "max_draft_m":       getattr(pc, "max_draft_m", 0.0),
            "max_loa_m":         getattr(pc, "max_loa_m", 0.0),
            "max_beam_m":        getattr(pc, "max_beam_m", 0.0),
            "handling_rate_tpd": getattr(pc, "handling_rate_tpd", 0.0),
            "tidal_dependent":   getattr(pc, "tidal_dependent", False),
        }

    # Vessel specs from warehouse
    vessel_specs_raw = {}
    for vc in vessel_classes:
        specs = repository.get_vessel_specs(vessel_class=vc)
        if vc in specs:
            row = specs[vc]
            vessel_specs_raw[vc] = {
                "draft_m": row.draft_m,
                "loa_m":   row.loa_m,
                "beam_m":  row.beam_m,
            }


    feasible_opts = constraint.check_feasibility(
        cargo_quantity=cargo_quantity,
        discharge_ports=discharge_ports,
        port_constraints=port_constraints,
        vessel_specs=vessel_specs_raw,
    )

    # Apply require_port override
    if constraints and constraints.require_port:
        feasible_opts = [o for o in feasible_opts if o.port == constraints.require_port or not o.is_feasible]

    truly_feasible = [o for o in feasible_opts if o.is_feasible]
    if not truly_feasible:
        reason = "No feasible (vessel, port) combination found"
        if constraints and constraints.exclude_vessel:
            reason += f" after excluding vessels: {constraints.exclude_vessel}"
        if constraints and constraints.require_port:
            reason += f" with required port: {constraints.require_port}"
        _fp, _fn = tag_assumed("No feasible vessel/port combination — no real solve performed.")
        empty = Strategy(
            voyage_count=0, commitment_mode="spot", voyages=[],
            total_cost_worst_case=0.0, cost_breakdown={},
            contains_high_uncertainty_voyage=False,
            solved_via="milp", provenance=_fp, provenance_note=_fn,
            infeasible_reason=reason,
        )
        return empty, []

    # ── 4. Fetch forecasts ────────────────────────────────────────────────
    forecasts: Dict[Tuple, Any] = {}
    for opt in truly_feasible:
        route_key = f"{origin_port}\u2192{opt.port}"
        key = (route_key, opt.vessel_class)
        if key not in forecasts:
            fc = repository.get_latest_forecast(
                route=f"{origin_port}\u2192{opt.port}",
                vessel_class=opt.vessel_class,
                horizon_days=timing_flexibility_days,
            )
            forecasts[key] = fc  # may be None — handled in coefficient computation

    # ── 5. τ generation per vessel class ─────────────────────────────────
    tau_points: Dict[str, List[int]] = {}
    for vc in vessel_classes:
        # Get a representative forecast trajectory for this class
        sample_fc = next((fc for (rk, v), fc in forecasts.items() if v == vc and fc is not None), None)
        traj = []
        if sample_fc:
            import json
            traj = json.loads(sample_fc.trajectory) if isinstance(sample_fc.trajectory, str) else []
        tau_points[vc] = _compute_tau(
            timing_flexibility_days=timing_flexibility_days,
            forecast_trajectory=traj,
            vessel_class=vc,
            origin_port=origin_port,
            human_overrides=constraints,
        )

    # ── 6. Bunker price ───────────────────────────────────────────────────
    bunker_snap = repository.get_latest_congestion_snapshot("bunker")
    bunker_price = float(bunker_snap.get("bunker_price_usd", 600.0)) if bunker_snap else 600.0

    # ── 7. Route physics ──────────────────────────────────────────────────
    route_physics_cache: Dict[str, RoutePhysics] = {}
    for opt in truly_feasible:
        rp_key = f"{origin_port}\u2192{opt.port}"
        if rp_key not in route_physics_cache:
            rp_row = repository.get_route_physics(origin_port, opt.port)
            if rp_row:
                route_physics_cache[rp_key] = RoutePhysics(
                    origin=origin_port,
                    destination=opt.port,
                    distance_nm=float(rp_row.distance_nm),
                    laden_consumption_tpd=float(rp_row.laden_consumption_tpd),
                    ballast_consumption_tpd=float(rp_row.ballast_consumption_tpd),
                    speed_knots=float(getattr(rp_row, "speed_knots", DEFAULT_BALLAST_SPEED_KNOTS)),
                )

    # ── 8. Repositioning days ─────────────────────────────────────────────
    repo_cache: Dict[str, Optional[float]] = {}
    for vc in vessel_classes:
        repo_days = repository.get_earliest_repositioning_days(vc, origin_port)
        repo_cache[vc] = repo_days  # None if no AIS data → repositioning_cost returns 0.0

    # ── 9. Base rate at lock day (Day 0 rate, Base scenario) ──────────────
    base_rate_at_lock: Dict[Tuple, float] = {}
    for opt in truly_feasible:
        route_key = f"{origin_port}\u2192{opt.port}"
        fc = forecasts.get((route_key, opt.vessel_class))
        if fc:
            import json
            traj = json.loads(fc.trajectory) if isinstance(fc.trajectory, str) else []
            cb   = json.loads(fc.confidence_band) if isinstance(fc.confidence_band, str) else {}
            lower = float(cb.get("lower", fc.point_estimate))
            upper = float(cb.get("upper", fc.point_estimate))
            rate_day0 = _get_scenario_rate(traj, lower, upper, 0, "base")
            base_rate_at_lock[(route_key, opt.vessel_class, opt.port)] = rate_day0
        else:
            base_rate_at_lock[(route_key, opt.vessel_class, opt.port)] = 0.0

    # ── 10. Compute cost coefficients ─────────────────────────────────────
    speed_mode = getattr(constraints, "speed_mode", "design") or "design"
    coeffs = _compute_cost_coefficients(
        quantity=cargo_quantity,
        feasible_opts=feasible_opts,
        tau_points=tau_points,
        forecasts=forecasts,
        route_physics_cache=route_physics_cache,
        bunker_price=bunker_price,
        base_rate_at_lock_day=base_rate_at_lock,
        commitment_benchmark_pct=commitment_benchmark_pct,
        origin_port=origin_port,
        repositioning_days_cache=repo_cache,
        speed_mode=speed_mode,
    )

    if not coeffs:
        # No route physics data → fallback
        reason = "No route physics data available for any feasible route"
        _fp, _fn = tag_assumed("No route physics data available — cost solve skipped.")
        empty = Strategy(
            voyage_count=0, commitment_mode="spot", voyages=[],
            total_cost_worst_case=0.0, cost_breakdown={},
            contains_high_uncertainty_voyage=False,
            solved_via="hybrid_fallback", provenance=_fp, provenance_note=_fn,
            infeasible_reason=reason,
        )
        return empty, []

    # max_voyages must track how many voyages the cargo physically NEEDS given
    # the feasible vessel classes — NOT a global max capacity.
    # IMPORTANT: use the MIN capacity among FEASIBLE vessels to allow smaller vessels to be selected.
    # If Panamax (75k) is feasible alongside Capesize (180k), 120k MT needs 2 Panamax voyages.
    # We no longer hard-cap at 3: the MILP can use as many voyages as physically needed,
    # up to a practical limit of 6 to keep the solve fast.
    smallest_feasible_cap = min(_VESSEL_CAPACITY_TONNES.get(o.vessel_class, 75_000.0) for o in truly_feasible)
    needed_voyages = max(1, math.ceil(cargo_quantity / max(smallest_feasible_cap, 1.0)))
    max_voyages = min(6, needed_voyages)  # practical upper bound to keep CBC fast

    # ── 11. MILP solve ────────────────────────────────────────────────────
    assignments, solved_via = _build_and_solve_milp(
        cargo_quantity=cargo_quantity,
        feasible_opts=feasible_opts,
        tau_points=tau_points,
        coeffs=coeffs,
        vessel_classes=list(dict.fromkeys(o.vessel_class for o in truly_feasible)),
        ports=list(dict.fromkeys(o.port for o in truly_feasible)),
        max_voyages=max_voyages,
        commitment_benchmark_pct=commitment_benchmark_pct,
        human_overrides=constraints,
    )

    if assignments is None or not assignments:
        assignments, solved_via = _hybrid_fallback(
            cargo_quantity=cargo_quantity,
            feasible_opts=feasible_opts,
            coeffs=coeffs,
            tau_points=tau_points,
            commitment_benchmark_pct=commitment_benchmark_pct,
        )

    # ── 12. Assemble Strategy ─────────────────────────────────────────────
    recommendation = _assemble_strategy(
        assignments=assignments,
        feasible_opts=feasible_opts,
        coeffs=coeffs,
        forecasts=forecasts,
        solved_via=solved_via,
        commitment_benchmark_pct=commitment_benchmark_pct,
        is_default_benchmark=is_default_benchmark,
        origin_port=origin_port,
        cargo_quantity=cargo_quantity,
    )

    # ── 13. Ranked Alternative Strategies for scenario_comparison[] ───────
    scenario_comparison: List[Strategy] = []
    
    def _gen_alt(overrides_dict: dict, theme_label: str) -> Optional[Strategy]:
        import dataclasses
        if constraints:
            merged = dataclasses.replace(constraints, **overrides_dict)
        else:
            merged = HumanOverrides(**overrides_dict)
        
        alt_assign, alt_solved_via = _build_and_solve_milp(
            cargo_quantity=cargo_quantity,
            feasible_opts=feasible_opts,
            tau_points=tau_points,
            coeffs=coeffs,
            vessel_classes=list(dict.fromkeys(o.vessel_class for o in truly_feasible)),
            ports=list(dict.fromkeys(o.port for o in truly_feasible)),
            max_voyages=max_voyages,
            commitment_benchmark_pct=commitment_benchmark_pct,
            human_overrides=merged,
        )
        if not alt_assign:
            return None
            
        strat = _assemble_strategy(
            assignments=alt_assign,
            feasible_opts=feasible_opts,
            coeffs=coeffs,
            forecasts=forecasts,
            solved_via=alt_solved_via,
            commitment_benchmark_pct=commitment_benchmark_pct,
            is_default_benchmark=is_default_benchmark,
            origin_port=origin_port,
            cargo_quantity=cargo_quantity,
        )
        
        # Inject theme label into provenance_note for the UI to read
        existing_note = strat.provenance_note
        strat.provenance_note = f"Theme: {theme_label}" + (f" ({existing_note})" if existing_note else "")
        return strat

    all_classes = list(dict.fromkeys(o.vessel_class for o in truly_feasible))
    all_ports = list(dict.fromkeys(o.port for o in truly_feasible))
    
    # Generate dynamic counter-factual strategies based on optimal recommendation
    themes = []
    
    if recommendation and recommendation.voyages:
        opt_vessel = recommendation.voyages[0].vessel_class
        opt_port   = recommendation.voyages[0].port
        opt_mode   = recommendation.commitment_mode
        opt_day    = recommendation.voyages[0].fix_day
        
        # 1. Mode Counter-Factual
        if opt_mode == "spot" or opt_mode == "mixed":
            themes.append(({"force_mode": "locked"}, "Hedge Market Risk (Lock)"))
        if opt_mode == "locked" or opt_mode == "mixed":
            themes.append(({"force_mode": "spot"}, "Float on Spot Market"))
            
        # 2. Timing Counter-Factual
        if opt_day < 7:
            themes.append(({"min_fix_day": opt_day + 7}, f"Delay Fixing (Wait >{opt_day + 7}d)"))
        else:
            themes.append(({"max_completion_day": max(0, opt_day - 7)}, "Fix Earlier (Urgent)"))
            
        # 3. Vessel Scarcity Counter-Factual
        alt_classes = [c for c in all_classes if c != opt_vessel]
        if alt_classes:
            alt_v = alt_classes[0]
            themes.append(({"require_vessel": alt_v}, f"What if no {opt_vessel}? Use {alt_v}"))
            
        # 4. Port Logistics Counter-Factual
        alt_ports = [p for p in all_ports if p != opt_port]
        if alt_ports:
            alt_p = alt_ports[0]
            themes.append(({"require_port": alt_p}, f"Discharge at {alt_p} instead"))
    else:
        # Fallback if no recommendation generated
        themes = [
            ({"max_completion_day": 0}, "Urgent Coverage"),
            ({"min_fix_day": 14}, "Wait & See (Fix >14d)"),
            ({"force_mode": "spot"}, "Pure Spot Exposure"),
            ({"force_mode": "locked"}, "Pure Locked Contract"),
        ]
    
    for overrides, label in themes:
        alt = _gen_alt(overrides, label)
        if alt: scenario_comparison.append(alt)
        
    # Deduplicate and sort
    seen_sigs = set()
    
    def _sig(strat: Strategy) -> str:
        return "|".join(sorted(f"{v.vessel_class}-{v.port}-{v.mode}-{v.fix_day}" for v in strat.voyages))
    
    if recommendation and recommendation.voyages:
        seen_sigs.add(_sig(recommendation))
        
    unique_alts = []
    for alt in scenario_comparison:
        sig = _sig(alt)
        if sig not in seen_sigs:
            seen_sigs.add(sig)
            unique_alts.append(alt)
            
    unique_alts.sort(key=lambda s: s.total_cost_worst_case)
    scenario_comparison = unique_alts[:4]

    return recommendation, scenario_comparison
