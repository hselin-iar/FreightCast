"""
backend/tests/test_operational_evidence.py

Tests for DOC3 §FEATURE: Operational Evidence Layer (engine/evidence.py).
"""
import pytest
from datetime import datetime, timezone, timedelta
from backend.engine.evidence import score_operational_evidence, OperationalEvidenceScore
from backend.warehouse.db import get_session
from backend.warehouse.models import OperationalEvidence


def test_operational_evidence_scoring_with_no_data():
    score = score_operational_evidence("NonExistentOrigin→NonExistentPort", "Capesize")
    assert isinstance(score, OperationalEvidenceScore)
    assert score.confidence == "no_data"
    assert score.observation_count == 0
    assert score.most_recent_observation_at is None
    assert score.provenance == "modeled"
    assert "econometric forecasting" in score.note


def test_operational_evidence_scoring_with_real_corridors():
    with get_session() as s:
        exists = s.query(OperationalEvidence).filter_by(route="Australia (Hay Point)→Paradip", vessel_class="Capesize").first()
        if not exists:
            s.add(OperationalEvidence(
                route="Australia (Hay Point)→Paradip",
                vessel_class="Capesize",
                observed_at=datetime.now(timezone.utc)
            ))
            s.commit()
    score = score_operational_evidence("Australia (Hay Point)→Paradip", "Capesize")
    assert isinstance(score, OperationalEvidenceScore)
    assert score.confidence in ("strong", "moderate")
    assert score.observation_count >= 1
    assert score.provenance == "modeled"


from starlette.testclient import TestClient
from backend.api.main import app


def test_operational_evidence_api_endpoint():
    client = TestClient(app)
    resp = client.get("/recommendation/evidence?route=Australia%20(Hay%20Point)→Visakhapatnam&vessel_class=Capesize")
    assert resp.status_code == 200
    data = resp.json()
    assert data["route"] == "Australia (Hay Point)→Visakhapatnam"
    assert data["vessel_class"] == "Capesize"
    assert data["confidence"] in ("strong", "moderate", "weak", "no_data")
    assert data["provenance"] == "modeled"
