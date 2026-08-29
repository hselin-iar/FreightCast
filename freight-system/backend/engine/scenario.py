"""
engine/scenario.py — Scenario Generator.

DOC3 §FEATURE: Scenario Generator
DOC2 §5.6 Step A (§9 unchanged)

PUBLIC API:
  generate_scenarios(forecast: ForecastObject) -> ScenarioPaths

Produces three labelled trajectories from a ForecastObject:
  - Base:        forecast.trajectory as-is
  - Optimistic:  each point shifted toward the FAVORABLE edge of confidence_band
  - Pessimistic: each point shifted toward the UNFAVORABLE edge of confidence_band

DIRECTIONALITY (DOC3 explicit requirement):
  "Favorable"/"unfavorable" direction depends on whether this is a COST the
  requester pays. For freight rates: LOWER is favorable (lower cost to the buyer).
  This is expressed as the named constant FAVORABLE_DIRECTION = "lower".

  Making this a named constant (not an inferred sign) prevents silent sign-flip bugs
  if the module is reused for a context where higher is favorable (e.g. a shipowner's
  revenue forecast).

ARCHITECTURE:
  Pure function — no I/O, no model calls, no warehouse access.
  Takes one ForecastObject in, returns ScenarioPaths out.
  Independently unit-testable; feeds decision.py's C_s per-scenario cost evaluation.

EDGE CASES (from DOC3):
  - confidence_band is (x, x) (zero width) → all three scenarios collapse to same path;
    not an error, means forecast is very confident.
  - trajectory has only one point → all three scenarios have one point too.
  - Empty trajectory → returns empty lists for all three paths.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from backend.config.constants import (
    SCENARIO_OPTIMISTIC_BAND_FRACTION,
    SCENARIO_PESSIMISTIC_BAND_FRACTION,
)
from backend.warehouse.models import ForecastObject

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Directionality constant (DOC3: must be a NAMED CONSTANT, not an inferred sign)
# ---------------------------------------------------------------------------

# For freight rates: the requester PAYS the rate, so LOWER is favorable.
# Change this constant (never an inline ±) if the module is ever reused for
# a context where higher is favorable (e.g. shipowner revenue).
FAVORABLE_DIRECTION: str = "lower"   # "lower" | "upper"


# ---------------------------------------------------------------------------
# Output type
# ---------------------------------------------------------------------------

@dataclass
class ScenarioPaths:
    """
    Three labelled trajectory paths produced by generate_scenarios().

    Each path is a list of {day: int, point_estimate: float} dicts —
    the same shape as ForecastObject.trajectory.

    Consumed by decision.py's per-scenario cost evaluation (C_s in DOC2 §11.3).
    """
    base:        List[Dict[str, Any]]
    optimistic:  List[Dict[str, Any]]
    pessimistic: List[Dict[str, Any]]


# ---------------------------------------------------------------------------
# Core function
# ---------------------------------------------------------------------------

def generate_scenarios(forecast: ForecastObject) -> ScenarioPaths:
    """
    Generate Base / Optimistic / Pessimistic trajectory paths from a ForecastObject.

    Base:
        The stored trajectory as-is — no transformation.

    Optimistic (for a cost the requester pays — FAVORABLE_DIRECTION = "lower"):
        Each point shifted toward the LOWER edge (confidence_band["lower"]) by
        SCENARIO_OPTIMISTIC_BAND_FRACTION of the distance from base to that edge.
        → optimistic_point = base_point - FRACTION * (base_point - lower_bound)
        → Result: lower cost → favorable outcome for the buyer.

    Pessimistic:
        Symmetric shift toward the UPPER edge (confidence_band["upper"]).
        → pessimistic_point = base_point + FRACTION * (upper_bound - base_point)
        → Result: higher cost → unfavorable outcome for the buyer.

    Degenerate case (zero-width band):
        lower == upper → shift is 0 → all three paths are identical. Not an error.

    Arguments:
        forecast: A ForecastObject as returned by repository.get_latest_forecast()
                  or get_forecast(). confidence_band may be a JSON string or dict.

    Returns:
        ScenarioPaths with base, optimistic, pessimistic trajectory lists.
    """
    # Parse trajectory
    traj_raw = forecast.trajectory
    if isinstance(traj_raw, str):
        try:
            traj_raw = json.loads(traj_raw)
        except (json.JSONDecodeError, TypeError):
            logger.warning("generate_scenarios: could not parse trajectory JSON — returning empty paths.")
            return ScenarioPaths(base=[], optimistic=[], pessimistic=[])

    if not traj_raw:
        return ScenarioPaths(base=[], optimistic=[], pessimistic=[])

    # Parse confidence_band
    cb_raw = forecast.confidence_band
    if isinstance(cb_raw, str):
        try:
            cb_raw = json.loads(cb_raw)
        except (json.JSONDecodeError, TypeError):
            logger.warning("generate_scenarios: could not parse confidence_band JSON — using point estimates.")
            cb_raw = {}

    lower_bound = float(cb_raw.get("lower", forecast.point_estimate))
    upper_bound = float(cb_raw.get("upper", forecast.point_estimate))

    # Build the three paths
    base_path:        List[Dict[str, Any]] = []
    optimistic_path:  List[Dict[str, Any]] = []
    pessimistic_path: List[Dict[str, Any]] = []

    for point in traj_raw:
        day = point.get("day", 0)
        base_val = float(point.get("point_estimate", 0.0))

        # Optimistic: shift toward LOWER (favorable for a cost payer)
        opt_val = base_val - SCENARIO_OPTIMISTIC_BAND_FRACTION * (base_val - lower_bound)

        # Pessimistic: shift toward UPPER (unfavorable for a cost payer)
        pess_val = base_val + SCENARIO_PESSIMISTIC_BAND_FRACTION * (upper_bound - base_val)

        base_path.append({"day": day, "point_estimate": round(base_val, 2)})
        optimistic_path.append({"day": day, "point_estimate": round(opt_val, 2)})
        pessimistic_path.append({"day": day, "point_estimate": round(pess_val, 2)})

    return ScenarioPaths(
        base=base_path,
        optimistic=optimistic_path,
        pessimistic=pessimistic_path,
    )
