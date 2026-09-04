"""
backend/engine/evidence.py — Operational Evidence Layer.

Post-solve advisory overlay from ShipOffer broker data.
NOT wired into MILP objective/constraints (DOC2 Addendum v3 §A3, DOC3 §FEATURE: Operational Evidence Layer).

Public function:
  score_operational_evidence(route: str, vessel_class: str) -> OperationalEvidenceScore
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, Optional

from backend.engine.provenance import Provenance, tag_modeled
from backend.warehouse import repository

logger = logging.getLogger(__name__)

ConfidenceLevel = Literal["strong", "moderate", "weak", "no_data"]


@dataclass
class OperationalEvidenceScore:
    """
    Typed output of score_operational_evidence().
    DOC3 §FEATURE: Operational Evidence Layer:
      route, vessel_class, confidence, observation_count, most_recent_observation_at, note, provenance
    """
    route: str
    vessel_class: str
    confidence: ConfidenceLevel
    observation_count: int
    most_recent_observation_at: Optional[datetime]
    note: str
    provenance: Provenance = "modeled"


def score_operational_evidence(route: str, vessel_class: str) -> OperationalEvidenceScore:
    """
    Score the real-world operational evidence for a (route, vessel_class) pair.

    Reads warehouse.repository.get_operational_evidence(route, vessel_class).
    Computes an auditable, transparent confidence signal based on observation count and recency:
      - "no_data": 0 observations
      - "strong": >= 3 observations or most recent within 14 days
      - "moderate": 1-2 observations within 45 days
      - "weak": observations older than 45 days

    Called AFTER decision.solve() produces a Strategy — never influences solver choices.
    """
    try:
        observations = repository.get_operational_evidence(route, vessel_class)
    except Exception as exc:
        logger.warning("get_operational_evidence failed for (%s, %s): %s", route, vessel_class, exc)
        observations = []

    if not observations:
        note = f"No verified broker fixture reports observed for {route} ({vessel_class}). Recommendation relies on econometric forecasting."
        return OperationalEvidenceScore(
            route=route,
            vessel_class=vessel_class,
            confidence="no_data",
            observation_count=0,
            most_recent_observation_at=None,
            note=note,
            provenance="modeled",
        )

    count = len(observations)
    most_recent = max(obs.observed_at for obs in observations) if observations else None
    
    # Recency check
    now = datetime.now(timezone.utc)
    if most_recent and most_recent.tzinfo is None:
        most_recent = most_recent.replace(tzinfo=timezone.utc)
    
    age_days = (now - most_recent).days if most_recent else 999

    if count >= 3 or age_days <= 14:
        confidence: ConfidenceLevel = "strong"
        note = f"Strong market evidence: {count} broker fixture reports observed on this corridor (most recent {age_days}d ago)."
    elif age_days <= 45:
        confidence = "moderate"
        note = f"Moderate market evidence: {count} broker fixture reports observed within the past 45 days."
    else:
        confidence = "weak"
        note = f"Weak/aging market evidence: {count} historical broker reports observed ({age_days}d old)."

    return OperationalEvidenceScore(
        route=route,
        vessel_class=vessel_class,
        confidence=confidence,
        observation_count=count,
        most_recent_observation_at=most_recent,
        note=note,
        provenance="modeled",
    )
