"""
tests/test_api_layer.py — Build Step 10: API Layer smoke tests.

DOC3 §FEATURE: API Layer — TESTING PLAN:
  "None dedicated at the route level — routes are thin pass-throughs to
   already-tested engine functions."

We test the route wiring itself (correct status codes, correct schema shapes,
scope validation 422s, and CORS header presence) using FastAPI TestClient with
mocked engine calls so we don't need a live DB.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from backend.api.main import app
from backend.engine.decision import Strategy, VoyageDetail


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


def _fake_strategy() -> Strategy:
    from backend.engine.provenance import tag_modeled
    return Strategy(
        voyage_count=1,
        commitment_mode="spot",
        voyages=[VoyageDetail(
            port="Paradip, India",
            vessel_class="Panamax",
            mode="spot",
            fix_day=7,
            cost_by_scenario={"base": 1_700_000.0, "optimistic": 1_500_000.0, "pessimistic": 1_900_000.0},
            lightening_required=False,
            lightening_port=None,
            discharge_days=2.0,
            tidal_window_note=None,
        )],
        total_cost_worst_case=1_900_000.0,
        cost_breakdown={"ocean_freight": 1_000_000.0, "bunker": 700_000.0, "total": 1_700_000.0},
        contains_high_uncertainty_voyage=False,
        solved_via="milp",
        provenance=tag_modeled(),
        provenance_note=None,
    )


# ---------------------------------------------------------------------------
# GET /health — always 200, correct schema
# ---------------------------------------------------------------------------

class TestHealthRoute:
    def test_health_returns_200(self, client):
        with patch("backend.api.routes.health.repository.get_valid_vessel_classes", return_value=["Panamax"]), \
             patch("backend.api.routes.health.repository.get_latest_retrain_timestamp", return_value=None), \
             patch("backend.api.routes.health.repository.get_latest_ais_timestamp", return_value=None):
            resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_has_required_fields(self, client):
        with patch("backend.api.routes.health.repository.get_valid_vessel_classes", return_value=[]), \
             patch("backend.api.routes.health.repository.get_latest_retrain_timestamp", return_value=None), \
             patch("backend.api.routes.health.repository.get_latest_ais_timestamp", return_value=None):
            resp = client.get("/health")
        body = resp.json()
        for field in ("status", "warehouse_reachable", "models_loaded"):
            assert field in body, f"Missing field: {field}"

    def test_health_degraded_when_no_models(self, client):
        with patch("backend.api.routes.health.repository.get_valid_vessel_classes", return_value=["Panamax"]), \
             patch("backend.api.routes.health.repository.get_latest_retrain_timestamp", return_value=None), \
             patch("backend.api.routes.health.repository.get_latest_ais_timestamp", return_value=None):
            resp = client.get("/health")
        assert resp.json()["status"] == "degraded"

    def test_health_error_when_warehouse_down(self, client):
        from backend.warehouse.db import WarehouseUnavailableError
        with patch("backend.api.routes.health.repository.get_valid_vessel_classes",
                   side_effect=WarehouseUnavailableError("down")):
            resp = client.get("/health")
        assert resp.json()["status"] == "error"
        assert resp.json()["warehouse_reachable"] is False


# ---------------------------------------------------------------------------
# GET /scope — returns lists (empty ok), correct shape
# ---------------------------------------------------------------------------

class TestScopeRoute:
    def test_scope_returns_200(self, client):
        with patch("backend.api.routes.scope.repository.get_valid_origins", return_value=[]), \
             patch("backend.api.routes.scope.repository.get_valid_dest_ports", return_value=[]), \
             patch("backend.api.routes.scope.repository.get_valid_vessel_classes", return_value=[]):
            resp = client.get("/scope")
        assert resp.status_code == 200

    def test_scope_has_three_lists(self, client):
        with patch("backend.api.routes.scope.repository.get_valid_origins",
                   return_value=["Hay Point, Australia"]), \
             patch("backend.api.routes.scope.repository.get_valid_dest_ports",
                   return_value=["Paradip, India"]), \
             patch("backend.api.routes.scope.repository.get_valid_vessel_classes",
                   return_value=["Panamax"]):
            resp = client.get("/scope")
        body = resp.json()
        assert "origins" in body
        assert "dest_ports" in body
        assert "vessel_classes" in body
        assert body["origins"] == ["Hay Point, Australia"]

    def test_scope_empty_on_cold_start(self, client):
        """Empty lists on cold start must NOT be an error per DOC3 edge cases."""
        with patch("backend.api.routes.scope.repository.get_valid_origins", return_value=[]), \
             patch("backend.api.routes.scope.repository.get_valid_dest_ports", return_value=[]), \
             patch("backend.api.routes.scope.repository.get_valid_vessel_classes", return_value=[]):
            resp = client.get("/scope")
        assert resp.status_code == 200
        assert resp.json()["origins"] == []


# ---------------------------------------------------------------------------
# POST /recommendation — scope validation + successful pass-through
# ---------------------------------------------------------------------------

class TestRecommendationRoute:
    def _patch_scope(self):
        return [
            patch("backend.api.routes.recommendation.repository.get_valid_origins",
                  return_value=["Hay Point, Australia"]),
            patch("backend.api.routes.recommendation.repository.get_valid_dest_ports",
                  return_value=["Paradip, India"]),
            patch("backend.api.routes.recommendation.repository.get_valid_vessel_classes",
                  return_value=["Panamax", "Capesize"]),
        ]

    def test_recommendation_requires_body(self, client):
        resp = client.post("/recommendation", json={})
        assert resp.status_code == 422

    def test_recommendation_422_on_unknown_origin(self, client):
        patches = self._patch_scope()
        with patches[0], patches[1], patches[2]:
            resp = client.post("/recommendation", json={
                "cargo_quantity": 70000,
                "origin_port": "UNKNOWN PORT",
                "discharge_ports": ["Paradip, India"],
                "timing_flexibility_days": 14,
            })
        assert resp.status_code == 422
        assert "not in verified scope" in resp.json()["detail"]

    def test_recommendation_422_on_unknown_discharge_port(self, client):
        patches = self._patch_scope()
        with patches[0], patches[1], patches[2]:
            resp = client.post("/recommendation", json={
                "cargo_quantity": 70000,
                "origin_port": "Hay Point, Australia",
                "discharge_ports": ["UNKNOWN PORT"],
                "timing_flexibility_days": 14,
            })
        assert resp.status_code == 422

    def test_recommendation_422_on_invalid_exclude_vessel(self, client):
        patches = self._patch_scope()
        with patches[0], patches[1], patches[2]:
            resp = client.post("/recommendation", json={
                "cargo_quantity": 70000,
                "origin_port": "Hay Point, Australia",
                "discharge_ports": ["Paradip, India"],
                "timing_flexibility_days": 14,
                "constraints": {"exclude_vessel": ["NONEXISTENT_CLASS"]},
            })
        assert resp.status_code == 422
        assert "not in verified scope" in resp.json()["detail"]

    def test_recommendation_passes_through_to_solve(self, client):
        fake = _fake_strategy()
        patches = self._patch_scope()
        with patches[0], patches[1], patches[2], \
             patch("backend.api.routes.recommendation.decision.solve",
                   return_value=(fake, [])) as mock_solve:
            resp = client.post("/recommendation", json={
                "cargo_quantity": 70000,
                "origin_port": "Hay Point, Australia",
                "discharge_ports": ["Paradip, India"],
                "timing_flexibility_days": 14,
            })
        assert resp.status_code == 200
        mock_solve.assert_called_once()
        body = resp.json()
        assert "recommendation" in body
        assert "scenario_comparison" in body

    def test_recommendation_response_includes_provenance(self, client):
        fake = _fake_strategy()
        patches = self._patch_scope()
        with patches[0], patches[1], patches[2], \
             patch("backend.api.routes.recommendation.decision.solve",
                   return_value=(fake, [])):
            resp = client.post("/recommendation", json={
                "cargo_quantity": 70000,
                "origin_port": "Hay Point, Australia",
                "discharge_ports": ["Paradip, India"],
                "timing_flexibility_days": 14,
            })
        rec = resp.json()["recommendation"]
        assert "provenance" in rec
        assert rec["provenance"] in ("measured", "modeled", "assumed")

    def test_recommendation_empty_constraints_treated_as_no_constraints(self, client):
        """constraints={} must behave identically to omitting constraints."""
        fake = _fake_strategy()
        patches = self._patch_scope()
        with patches[0], patches[1], patches[2], \
             patch("backend.api.routes.recommendation.decision.solve",
                   return_value=(fake, [])) as mock_solve:
            resp = client.post("/recommendation", json={
                "cargo_quantity": 70000,
                "origin_port": "Hay Point, Australia",
                "discharge_ports": ["Paradip, India"],
                "timing_flexibility_days": 14,
                "constraints": {},
            })
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# POST /scenario — voyage_count + commitment_mode required; conflict check
# ---------------------------------------------------------------------------

class TestScenarioRoute:
    def _scope_patches(self):
        return [
            patch("backend.api.routes.recommendation.repository.get_valid_origins",
                  return_value=["Hay Point, Australia"]),
            patch("backend.api.routes.recommendation.repository.get_valid_dest_ports",
                  return_value=["Paradip, India"]),
            patch("backend.api.routes.recommendation.repository.get_valid_vessel_classes",
                  return_value=["Panamax"]),
        ]

    def test_scenario_422_if_voyage_count_missing(self, client):
        resp = client.post("/scenario", json={
            "cargo_quantity": 70000,
            "origin_port": "Hay Point, Australia",
            "discharge_ports": ["Paradip, India"],
            "timing_flexibility_days": 14,
            "commitment_mode": "spot",
            # voyage_count missing
        })
        assert resp.status_code == 422

    def test_scenario_422_on_mode_force_conflict(self, client):
        """force_mode='locked' + commitment_mode='spot' must 422 per DOC3 edge cases."""
        resp = client.post("/scenario", json={
            "cargo_quantity": 70000,
            "origin_port": "Hay Point, Australia",
            "discharge_ports": ["Paradip, India"],
            "timing_flexibility_days": 14,
            "voyage_count": 1,
            "commitment_mode": "spot",
            "constraints": {"force_mode": "locked"},
        })
        assert resp.status_code == 422
        # Pydantic 422 returns detail as a list of error dicts; conflict message is in msg
        detail = resp.json()["detail"]
        msgs = detail if isinstance(detail, str) else " ".join(e.get("msg", "") for e in detail)
        assert "Conflict" in msgs


# ---------------------------------------------------------------------------
# GET /port-status
# ---------------------------------------------------------------------------

class TestPortStatusRoute:
    def test_port_status_returns_200(self, client):
        snap = {
            "port": "Paradip, India",
            "vessel_count": 3,
            "avg_wait_hours": 12.5,
            "recorded_at": None,
            "is_live": False,
            "source_note": "seeded",
            "bunker_price_usd": 620.0,
        }
        with patch("backend.api.routes.port_status.congestion.get_congestion_snapshot",
                   return_value=snap):
            resp = client.get("/port-status?port=Paradip%2C+India")
        assert resp.status_code == 200
        body = resp.json()
        assert body["provenance"] == "assumed"   # is_live=False → assumed

    def test_port_status_is_live_provenance_measured(self, client):
        snap = {
            "port": "Paradip, India",
            "vessel_count": 1,
            "avg_wait_hours": 4.0,
            "recorded_at": "2026-08-29T05:00:00+00:00",
            "is_live": True,
            "source_note": "AIS live",
            "bunker_price_usd": None,
        }
        with patch("backend.api.routes.port_status.congestion.get_congestion_snapshot",
                   return_value=snap):
            resp = client.get("/port-status?port=Paradip%2C+India")
        assert resp.json()["provenance"] == "measured"
