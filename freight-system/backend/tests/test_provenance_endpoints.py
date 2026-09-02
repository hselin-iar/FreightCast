"""
tests/test_provenance_endpoints.py — Unit tests for /provenance/situations and /provenance/catalog
"""
from __future__ import annotations

from fastapi.testclient import TestClient
from backend.api.main import app

client = TestClient(app)


def test_get_provenance_situations():
    """GET /provenance/situations returns rich scenarios with citations."""
    resp = client.get("/provenance/situations")
    assert resp.status_code == 200
    data = resp.json()
    assert "scenarios" in data
    scenarios = data["scenarios"]
    assert len(scenarios) >= 4

    for sc in scenarios:
        assert sc["id"]
        assert sc["title"]
        assert sc["category"]
        assert sc["base_case_text"]
        assert sc["assumed_situation_title"]
        assert sc["assumed_situation_text"]
        assert len(sc["comparative_metrics"]) > 0
        assert len(sc["citations"]) > 0

        for cit_id, cit in sc["citations"].items():
            assert cit["id"] == cit_id
            assert cit["token"]
            assert cit["title"]
            assert cit["source"]
            assert cit["provenance"] in ("measured", "modeled", "assumed")
            assert cit["confidence"]
            assert cit["rationale"]


def test_get_provenance_catalog():
    """GET /provenance/catalog returns complete grounded parameters."""
    resp = client.get("/provenance/catalog")
    assert resp.status_code == 200
    data = resp.json()
    assert "parameters" in data
    assert "total_count" in data
    assert data["total_count"] == len(data["parameters"])
    assert data["total_count"] >= 10

    for param in data["parameters"]:
        assert param["name"]
        assert param["category"]
        assert param["value"]
        assert param["unit"]
        assert param["provenance"] in ("measured", "modeled", "assumed")
        assert param["source"]
        assert isinstance(param["verified"], bool)
        assert param["notes"]
