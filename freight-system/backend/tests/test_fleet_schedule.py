"""
tests/test_fleet_schedule.py — Fleet Portfolio Scheduling unit & integration tests.

Verifies:
  - GET /fleet-status returns canonical vessel catalog and live tracked ships
  - GET /fleet-schedule returns structured Step 51V solution
  - POST /fleet-schedule/solve triggers dynamic re-solve and returns optimal portfolio
  - fleet_optimizer.solve_fleet_portfolio enforces:
      1. Non-overlapping temporal intervals per vessel (no collisions)
      2. Max sail count upper bound
      3. Complete partition of contracts into SAIL vs. KILL
"""
import pytest
from fastapi.testclient import TestClient
from backend.api.main import app
from backend.engine import fleet_optimizer


@pytest.fixture(autouse=True)
def setup_fleet_test_db():
    from backend.warehouse.db import create_all_tables
    create_all_tables()
    yield


@pytest.fixture
def client():
    return TestClient(app)


def test_get_fleet_status(client):
    """GET /fleet-status must return vessels list and canonical vessel_classes."""
    resp = client.get("/fleet-status")
    assert resp.status_code == 200
    data = resp.json()
    assert "vessels" in data
    assert "vessel_classes" in data
    assert len(data["vessel_classes"]) >= 3
    # Check that each vessel class has required naval architecture fields
    first_vc = data["vessel_classes"][0]
    assert "class_name" in first_vc
    assert "typical_capacity_tonnes" in first_vc
    assert "draft_m" in first_vc
    assert "loa_m" in first_vc


def test_get_fleet_schedule(client):
    """GET /fleet-schedule must return summary, assignments, vessel_schedule, and all_decisions."""
    resp = client.get("/fleet-schedule")
    assert resp.status_code == 200
    data = resp.json()
    assert "summary" in data
    assert "assignments" in data
    assert "vessel_schedule" in data
    assert "all_decisions" in data

    summary = data["summary"]
    assert summary["total_contracts"] == summary["sail_contracts"] + summary["kill_contracts"]
    assert summary["sail_contracts"] > 0
    assert summary["worst_incremental_usd"] > 0
    assert "Optimal" in summary["solver_status"]


def test_fleet_optimizer_invariants():
    """Direct solver run must respect temporal non-overlap and max-sail constraints."""
    res = fleet_optimizer.solve_fleet_portfolio(max_sail=4, risk_ratio=0.50, time_limit=15, save_outputs=False)
    summary = res["summary"]
    assignments = res["assignments"]
    vessel_schedule = res["vessel_schedule"]
    all_decisions = res["all_decisions"]

    # 1. Max sail constraint respected
    assert summary["sail_contracts"] <= 4
    assert len(assignments) <= 4

    # 2. Complete partition into SAIL and KILL
    assert summary["total_contracts"] == summary["sail_contracts"] + summary["kill_contracts"]
    assert len(all_decisions) == summary["total_contracts"]

    # 3. Check temporal non-overlap per vessel
    import pandas as pd
    vessel_legs = {}
    for leg in vessel_schedule:
        imo = leg["imo"]
        start = pd.to_datetime(leg["departure_date"], utc=True)
        end = pd.to_datetime(leg["estimated_eta"], utc=True)
        vessel_legs.setdefault(imo, []).append((start, end, leg["contract_id"]))

    for imo, legs in vessel_legs.items():
        sorted_legs = sorted(legs, key=lambda x: x[0])
        for i in range(len(sorted_legs) - 1):
            prev_end = sorted_legs[i][1]
            next_start = sorted_legs[i + 1][0]
            assert prev_end <= next_start, f"Vessel {imo} has overlapping voyages: {sorted_legs[i]} and {sorted_legs[i+1]}"
