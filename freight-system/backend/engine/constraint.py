"""
engine/constraint.py — Constraint / Feasibility Engine.

DOC3 §FEATURE: Constraint / Feasibility Engine (CARRIED OVER)
DOC2 §8

RULES (deterministic, pure functions — no statistics):
  1. Draft rule      — vessel laden draft ≤ port max_draft_m  (hard block)
  2. LOA rule        — vessel LOA ≤ port max_loa_m            (hard block)
  3. Beam rule       — vessel beam ≤ port max_beam_m          (hard block)
  4. Parcel-fit      — quantity << capacity → feasible but flagged "inefficient fit" (soft, not blocking)
  5. Handling rate   — port handling_rate_tpd → discharge_days estimate  (no pass/fail, feeds cost model)
  6. Tidal window    — tide-dependent ports: narrow arrival times, not a hard block; tidal_window_note
                       passed to Decision Engine's τ selection (DOC2 §8 Rule 6)
  7. Lightening      — draft > port limit → check lightening_ports lookup; feasible-with-lightening
                       or infeasible if no eligible deeper port on the route
  8. Vessel-size hint — larger classes proposed first among those clearing Rules 1–3 (ordering only)

ARCHITECTURE:
  - Pure functions over typed PortConstraint / VesselSpec inputs → FeasibleOption output.
  - Zero code changes needed as scope grows — operates on whatever verified rows the caller passes in.
  - NEVER imports from api/, ingestion/, or warehouse/ directly — callers pass data in.
  - tidal_window_note is now consumed by decision.py's τ selection (Step 6 onward), not just displayed.

ANTI-DRIFT GUARD (DOC4 Step 5):
  This is the most stable module in the codebase. Do NOT add soft-constraint scoring,
  probabilistic rules, or anything not in DOC2 §8. The 8 rules are final.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lightening port lookup (DOC2 §8 Rule 7)
# Ports that are geographically along the way and can serve as a lightening
# call before a shallower destination. Only ports actually on the route —
# not detours. Keyed by destination port name.
# Grows as the scope catalog grows (§A1) — no code change needed for new ports.
# ---------------------------------------------------------------------------

#: Maps a destination port (too shallow) → list of deeper-draft ports
#: that are route-compatible for a lightening call.
LIGHTENING_PORTS: dict[str, list[str]] = {
    "Paradip":    ["Gangavaram", "Dhamra"],       # deeper draft anchorages en route
    "Haldia":     ["Gangavaram", "Dhamra", "Paradip"],
    "Gangavaram": [],                              # already deep-draft; no lightening needed
    "Dhamra":     ["Gangavaram"],
    "Vizag":      [],                              # deep port; no lightening needed
}

#: Estimated cost and time penalty per lightening call
LIGHTENING_PENALTY_DAYS: float = 2.5        # extra port-call days (assumed; tagged provenance)
LIGHTENING_PENALTY_COST_USD: float = 75_000.0  # per-call flat estimate (assumed; tagged provenance)

#: Parcel-fit threshold: quantity < PARCEL_FIT_FRACTION × vessel_capacity → flag "inefficient fit"
PARCEL_FIT_FRACTION: float = 0.40

# ---------------------------------------------------------------------------
# Output data class
# ---------------------------------------------------------------------------

@dataclass
class FeasibleOption:
    """
    One entry in feasible_options[].

    Produced by check_feasibility() for each (vessel_class, port) pair that
    clears the constraint rules. Consumed by the Decision Engine (cost_terms,
    decision.py).

    DOC3 ONE addition: tidal_window_note is now also consumed by decision.py's
    τ selection, not just displayed in the UI.
    """
    vessel_class: str
    port: str

    # Feasibility verdict
    is_feasible: bool
    infeasible_reason: Optional[str] = None     # populated only when is_feasible=False

    # Rule 4: parcel-fit flag (soft — feasible but flagged)
    is_inefficient_fit: bool = False

    # Rule 5: discharge-duration estimate in days (feeds cost model, not pass/fail)
    discharge_days: float = 0.0

    # Rule 6: tidal note — passed to Decision Engine's τ selection (DOC2 §8 Rule 6)
    tidal_window_note: Optional[str] = None     # None when port is not tide-dependent

    # Rule 7: lightening details
    requires_lightening: bool = False
    lightening_port: Optional[str] = None       # the intermediate deeper-draft port
    lightening_penalty_days: float = 0.0
    lightening_penalty_cost_usd: float = 0.0

    # Rule 8: size-rank ordering hint (lower = larger/preferred)
    size_rank: int = 0


# ---------------------------------------------------------------------------
# Vessel capacity reference (DOC3: class-level, not per-IMO)
# Used only by Rule 4 (parcel-fit) — actual draft/LOA/beam come from VesselSpec.
# ---------------------------------------------------------------------------

# Approximate typical capacity in tonnes per vessel class (DOC3 §0 scope).
# These are ORDER-OF-MAGNITUDE estimates used only for the parcel-fit soft flag.
_VESSEL_CAPACITY_TONNES: dict[str, float] = {
    "Capesize":            180_000.0,
    "Panamax/Kamsarmax":    80_000.0,
    "Supramax/Ultramax":    58_000.0,
}

# Size-rank ordering for Rule 8 (lower = larger = proposed first)
_VESSEL_SIZE_RANK: dict[str, int] = {
    "Capesize":            1,
    "Panamax/Kamsarmax":   2,
    "Supramax/Ultramax":   3,
}


# ---------------------------------------------------------------------------
# Rule implementations (pure functions — no I/O, no warehouse calls)
# ---------------------------------------------------------------------------

def _rule1_draft(vessel_draft_m: float, port_max_draft_m: float) -> bool:
    """Rule 1: vessel laden draft ≤ port max permissible draft. Hard block."""
    return vessel_draft_m <= port_max_draft_m


def _rule2_loa(vessel_loa_m: float, port_max_loa_m: float) -> bool:
    """Rule 2: vessel LOA ≤ berth max admissible LOA. Hard block."""
    return vessel_loa_m <= port_max_loa_m


def _rule3_beam(vessel_beam_m: float, port_max_beam_m: float) -> bool:
    """Rule 3: vessel beam ≤ berth max admissible beam. Hard block."""
    return vessel_beam_m <= port_max_beam_m


def _rule4_parcel_fit(
    cargo_quantity: float,
    vessel_class: str,
) -> bool:
    """
    Rule 4: Is the cargo quantity much smaller than the vessel's capacity?
    Returns True if it IS an inefficient fit (i.e., quantity << capacity).
    Not a hard block — the option remains feasible but gets flagged.
    """
    typical_capacity = _VESSEL_CAPACITY_TONNES.get(vessel_class, 180_000.0)
    return cargo_quantity < PARCEL_FIT_FRACTION * typical_capacity


def _rule5_handling_rate(
    cargo_quantity: float,
    port_handling_rate_tpd: float,
) -> float:
    """
    Rule 5: Estimate discharge duration in days.
    Not a pass/fail — used by cost model downstream.
    Returns 0.0 if handling_rate_tpd is 0 (avoids division by zero).
    """
    if port_handling_rate_tpd <= 0.0:
        return 0.0
    return cargo_quantity / port_handling_rate_tpd


def _rule6_tidal_window(
    port_name: str,
    is_tidal_dependent: bool,
) -> Optional[str]:
    """
    Rule 6: If the port is tide-dependent, produce a tidal_window_note.
    Not a hard block — narrows viable arrival times, passed to Decision Engine's
    τ selection (DOC2 §8 Rule 6: "rather than resolved here").
    Returns None for non-tidal ports.
    """
    if not is_tidal_dependent:
        return None
    return (
        f"{port_name} is tide-dependent: vessel arrival timing must align with "
        f"high-water window. Decision Engine will restrict τ candidates accordingly."
    )


def _rule7_lightening(
    vessel_draft_m: float,
    port_max_draft_m: float,
    port_name: str,
) -> tuple[bool, Optional[str]]:
    """
    Rule 7: If vessel draft exceeds port limit, look for a compatible lightening port.
    Returns (requires_lightening: bool, lightening_port: str | None).
      - (True, port_name)  → feasible with lightening at that port
      - (True, None)       → infeasible (no lightening port available on this route)
      - (False, None)      → draft is fine, no lightening needed

    The lightening port lookup only contains ports actually along the route —
    not detours (DOC2 §8 Rule 7).
    """
    if vessel_draft_m <= port_max_draft_m:
        return False, None  # draft is fine

    eligible = LIGHTENING_PORTS.get(port_name, [])
    if eligible:
        return True, eligible[0]    # propose the first route-compatible option
    else:
        return True, None           # requires lightening but no eligible port → infeasible


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def check_feasibility(
    cargo_quantity: float,
    discharge_ports: List[str],
    port_constraints: dict[str, dict],     # port_name → {max_draft_m, max_loa_m, max_beam_m, handling_rate_tpd, tidal_dependent}
    vessel_specs: dict[str, dict],          # vessel_class → {draft_m, loa_m, beam_m}
) -> List[FeasibleOption]:
    """
    Run all 8 constraint rules for each (vessel_class × port) pair.

    Returns feasible_options[] sorted per Rule 8 (larger vessels first within
    each port). Infeasible options are included in the list with is_feasible=False
    and an infeasible_reason — the Decision Engine uses these to exclude
    (vessel, port) pairs from the MILP's feasibility constraints.

    Arguments:
      cargo_quantity:   Total cargo tonnes (from API request).
      discharge_ports:  Target ports requested (from API request).
      port_constraints: Verified PortConstraint rows from repository, keyed by port name.
      vessel_specs:     VesselSpec rows from repository, keyed by vessel class.

    Pure function — no I/O. Callers are responsible for providing verified data.
    """
    options: list[FeasibleOption] = []

    for port_name in discharge_ports:
        pc = port_constraints.get(port_name)
        if pc is None:
            logger.warning("check_feasibility: no PortConstraint row for '%s' — skipping.", port_name)
            continue

        port_max_draft   = float(pc.get("max_draft_m", 0.0))
        port_max_loa     = float(pc.get("max_loa_m", 0.0))
        port_max_beam    = float(pc.get("max_beam_m", 0.0))
        handling_rate    = float(pc.get("handling_rate_tpd", 0.0))
        tidal_raw        = pc.get("tidal_dependent", False)
        # Accept bool, "true"/"false" string (as stored from CSV ingest)
        if isinstance(tidal_raw, str):
            is_tidal = tidal_raw.strip().lower() == "true"
        else:
            is_tidal = bool(tidal_raw)

        port_options: list[FeasibleOption] = []

        for vessel_class, vs in vessel_specs.items():
            vessel_draft = float(vs.get("draft_m", 0.0))
            vessel_loa   = float(vs.get("loa_m", 0.0))
            vessel_beam  = float(vs.get("beam_m", 0.0))

            # — Rule 1: Draft —
            draft_ok = _rule1_draft(vessel_draft, port_max_draft)

            # — Rule 7: Lightening (checked before blocking on draft) —
            requires_lightening, lightening_port = _rule7_lightening(
                vessel_draft, port_max_draft, port_name
            )

            # Hard-block conditions
            loa_ok  = _rule2_loa(vessel_loa, port_max_loa)
            beam_ok = _rule3_beam(vessel_beam, port_max_beam)

            # Determine feasibility
            if not loa_ok:
                opt = FeasibleOption(
                    vessel_class=vessel_class, port=port_name,
                    is_feasible=False,
                    infeasible_reason=f"LOA {vessel_loa}m exceeds port limit {port_max_loa}m",
                    size_rank=_VESSEL_SIZE_RANK.get(vessel_class, 99),
                )
            elif not beam_ok:
                opt = FeasibleOption(
                    vessel_class=vessel_class, port=port_name,
                    is_feasible=False,
                    infeasible_reason=f"Beam {vessel_beam}m exceeds port limit {port_max_beam}m",
                    size_rank=_VESSEL_SIZE_RANK.get(vessel_class, 99),
                )
            elif not draft_ok and requires_lightening and lightening_port is None:
                # Draft fails AND no lightening port available
                opt = FeasibleOption(
                    vessel_class=vessel_class, port=port_name,
                    is_feasible=False,
                    infeasible_reason=(
                        f"Draft {vessel_draft}m exceeds port limit {port_max_draft}m "
                        f"and no lightening port is available on this route."
                    ),
                    size_rank=_VESSEL_SIZE_RANK.get(vessel_class, 99),
                )
            else:
                # Feasible (possibly with lightening)
                # — Rule 4: Parcel-fit (soft flag) —
                inefficient = _rule4_parcel_fit(cargo_quantity, vessel_class)

                # — Rule 5: Handling-rate discharge estimate —
                discharge_days = _rule5_handling_rate(cargo_quantity, handling_rate)

                # — Rule 6: Tidal window note —
                tidal_note = _rule6_tidal_window(port_name, is_tidal)

                opt = FeasibleOption(
                    vessel_class=vessel_class,
                    port=port_name,
                    is_feasible=True,
                    is_inefficient_fit=inefficient,
                    discharge_days=round(discharge_days, 2),
                    tidal_window_note=tidal_note,
                    requires_lightening=requires_lightening,
                    lightening_port=lightening_port,
                    lightening_penalty_days=LIGHTENING_PENALTY_DAYS if requires_lightening else 0.0,
                    lightening_penalty_cost_usd=LIGHTENING_PENALTY_COST_USD if requires_lightening else 0.0,
                    size_rank=_VESSEL_SIZE_RANK.get(vessel_class, 99),
                )

            port_options.append(opt)

        # — Rule 8: Sort larger vessels first within each port (ordering hint only) —
        port_options.sort(key=lambda o: o.size_rank)
        options.extend(port_options)

    return options
