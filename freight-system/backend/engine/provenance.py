"""
Provenance & Explainability Layer  — Build Step 9
===================================================
DOC3 §FEATURE: Provenance & Explainability Layer
DOC2 §12 — "every number on the dashboard carries a small badge"

A shared type + tagging helpers used at the *point each value originates*,
not bolted on at the API or dashboard layer.  Centralising here prevents
drift where one engine's output is taggable and another's silently isn't.

Importing modules set the tag when the value is created:
    forecasting.py      → tag_modeled()  on every ForecastObject it writes
    cost_terms.py       → tag_measured() on distance-based bunker terms
                        → tag_assumed()  on tax/waiting/canal placeholder terms
    decision.py         → tag_assumed()  on commitment_benchmark-derived cost terms
    congestion.py       → tag_measured() for live AIS data
                        → tag_assumed()  for seeded-fallback congestion snapshots

compute_sensitivity() lives here and reuses decision.py's already-cached
per-scenario C_s cost terms — it does NOT trigger a second MILP solve.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional, Tuple

# ---------------------------------------------------------------------------
# Core type
# ---------------------------------------------------------------------------
Provenance = Literal["measured", "modeled", "assumed"]

# ---------------------------------------------------------------------------
# Tagging helpers (O(1) per call, no I/O)
# ---------------------------------------------------------------------------

def tag_measured() -> Provenance:
    """
    Value originates from an ingested, real-world measurement.

    Examples:
    - Distance-based bunker consumption (route_physics table, real NM)
    - Port handling rates (verified PortConstraint rows)
    - Live AIS congestion snapshot (is_live=True)
    - Historical freight rates from BDI / broker sources
    """
    return "measured"


def tag_modeled(uncertainty_flag: bool = False) -> Provenance:
    """
    Value derived from a trained model or a computation over measured inputs.

    uncertainty_flag=True means the caller has already determined the
    forecast's confidence band exceeds the high-uncertainty threshold —
    the ProvenanceBadge can render a cautionary indicator.

    Examples:
    - Every ForecastObject produced by forecasting.train_and_evaluate()
    - total_cost_worst_case (function of measured + modeled inputs;
      tagged at the coarsest level it is displayed)
    - Sensitivity perturbation outputs
    """
    return "modeled"


def tag_assumed(note: str) -> Tuple[Provenance, str]:
    """
    Value uses a placeholder constant or policy default — not yet grounded
    in measured or live data.  Returns both the tag and the caller-supplied
    note so the note travels with the value.

    Examples:
    - commitment_benchmark_pct when DEFAULT_COMMITMENT_BENCHMARK_PCT is used
    - tax / canal-dues placeholder terms (TAX_RATE_PCT)
    - waiting_cost when no port-delay signal is available
    - Congestion fallback snapshot when the AIS listener hasn't written data
    """
    if not note:
        raise ValueError("tag_assumed() requires a non-empty note string")
    return "assumed", note


# ---------------------------------------------------------------------------
# SensitivityResult — output of compute_sensitivity()
# ---------------------------------------------------------------------------

@dataclass
class SensitivityBar:
    """
    One bar in the tornado chart — how much a ±perturbation in one cost
    driver shifts total_cost_worst_case.
    """
    driver:        str      # human-readable label, e.g. "Freight Rate +5%"
    delta_cost:    float    # signed USD change vs. base; negative = saving
    direction:     Literal["upside", "downside"]
    provenance:    Provenance   # always "modeled" — derived from C_s terms


@dataclass
class SensitivityResult:
    """
    Output of compute_sensitivity() — reuses already-solved C_s terms,
    never triggers a second MILP solve.  DOC3 §FEATURE: Provenance &
    Explainability Layer; DOC2 §16.3 (tornado chart / worst-case cost).
    """
    base_total_cost:       float
    worst_case_cost:       float
    perturbation_pct:      float               # e.g. 5.0  → ±5 % shock
    bars:                  List[SensitivityBar]
    provenance:            Provenance = "modeled"
    provenance_note:       Optional[str] = None


# ---------------------------------------------------------------------------
# compute_sensitivity() — pure function over already-computed cost terms
# ---------------------------------------------------------------------------

def compute_sensitivity(
    cost_breakdown: Dict[str, float],
    cost_by_scenario: Dict[str, Dict[str, float]],   # {voyage_idx: {base, optimistic, pessimistic}}
    perturbation_pct: float = 5.0,
) -> SensitivityResult:
    """
    Build a tornado-chart sensitivity analysis from the C_s cost terms that
    decision.solve() already computed during the MILP run.

    Parameters
    ----------
    cost_breakdown : dict
        The 5-bucket breakdown from Strategy.cost_breakdown
        (keys: ocean_freight, bunker, port_handling, lightening_extra, total).
    cost_by_scenario : dict
        Per-voyage scenario cost dict, keyed by voyage index (str) →
        {"base": float, "optimistic": float, "pessimistic": float}.
        Pass an empty dict for a single-voyage Strategy to use cost_breakdown
        buckets directly.
    perturbation_pct : float
        Shock size as a percentage (default 5.0 → ±5 %).

    Returns
    -------
    SensitivityResult
        Bars ordered largest-absolute-delta first (descending).
        Does NOT re-run the MILP solver.
    """
    pct = perturbation_pct / 100.0
    base_total    = cost_breakdown.get("total", 0.0)
    freight_base  = cost_breakdown.get("ocean_freight", cost_breakdown.get("freight", 0.0))
    bunker_base   = cost_breakdown.get("bunker", 0.0)
    port_base     = cost_breakdown.get("port_handling", 0.0)
    light_base    = cost_breakdown.get("lightening_extra", 0.0)

    bars: List[SensitivityBar] = []

    # Freight rate shock
    if freight_base > 0:
        up_delta   = freight_base * pct
        down_delta = -freight_base * pct
        bars.append(SensitivityBar(
            driver=f"Freight Rate +{perturbation_pct:.0f}%",
            delta_cost=up_delta,
            direction="downside",
            provenance="modeled",
        ))
        bars.append(SensitivityBar(
            driver=f"Freight Rate -{perturbation_pct:.0f}%",
            delta_cost=down_delta,
            direction="upside",
            provenance="modeled",
        ))

    # Bunker price shock
    if bunker_base > 0:
        bars.append(SensitivityBar(
            driver=f"Bunker Price +{perturbation_pct:.0f}%",
            delta_cost=bunker_base * pct,
            direction="downside",
            provenance="modeled",
        ))
        bars.append(SensitivityBar(
            driver=f"Bunker Price -{perturbation_pct:.0f}%",
            delta_cost=-bunker_base * pct,
            direction="upside",
            provenance="modeled",
        ))

    # Port handling shock (smaller driver, included for completeness)
    if port_base > 0:
        bars.append(SensitivityBar(
            driver=f"Port Handling +{perturbation_pct:.0f}%",
            delta_cost=port_base * pct,
            direction="downside",
            provenance="modeled",
        ))

    # Scenario spread (pessimistic – optimistic from already-computed C_s)
    if cost_by_scenario:
        scen_totals: Dict[str, float] = {"base": 0.0, "optimistic": 0.0, "pessimistic": 0.0}
        for v_costs in cost_by_scenario.values():
            for scen in ("base", "optimistic", "pessimistic"):
                scen_totals[scen] += v_costs.get(scen, 0.0)

        pess_delta = scen_totals["pessimistic"] - scen_totals["base"]
        opt_delta  = scen_totals["optimistic"]  - scen_totals["base"]

        if abs(pess_delta) > 0:
            bars.append(SensitivityBar(
                driver="Rate Scenario: Pessimistic",
                delta_cost=pess_delta,
                direction="downside" if pess_delta > 0 else "upside",
                provenance="modeled",
            ))
        if abs(opt_delta) > 0:
            bars.append(SensitivityBar(
                driver="Rate Scenario: Optimistic",
                delta_cost=opt_delta,
                direction="upside" if opt_delta < 0 else "downside",
                provenance="modeled",
            ))

    # Sort by absolute delta descending (tornado ordering)
    bars.sort(key=lambda b: abs(b.delta_cost), reverse=True)

    worst_cost = base_total + max((b.delta_cost for b in bars if b.delta_cost > 0), default=0.0)

    return SensitivityResult(
        base_total_cost=base_total,
        worst_case_cost=worst_cost,
        perturbation_pct=perturbation_pct,
        bars=bars,
        provenance="modeled",
        provenance_note="Derived from already-cached C_s cost terms — no second MILP solve.",
    )
