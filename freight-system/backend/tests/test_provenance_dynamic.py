"""
backend/tests/test_provenance_dynamic.py — Automated regression suite for
Dynamic Grounded Situational Scenario Generation and Dynamic Question Synthesis.
"""
from fastapi.testclient import TestClient
from backend.api.main import app
from backend.api.routes.provenance import build_grounded_scenarios
from backend.api.schemas import RecommendationRequest, RecommendationResponse

client = TestClient(app)


def test_provenance_situations_generate_dynamic_for_single_voyage():
    """Verify that a single-voyage recommendation generates tailored scenarios."""
    from backend.warehouse import repository
    origins = repository.get_valid_origins()
    discharge_ports = repository.get_valid_dest_ports()
    origin = origins[0] if origins else "Australia (Hay Point)"
    discharge = discharge_ports[0] if discharge_ports else "Paradip"

    rec_req = {
        "cargo_quantity": 75000,
        "origin_port": origin,
        "discharge_ports": [discharge],
        "timing_flexibility_days": 30,
    }
    rec_res = client.post("/recommendation", json=rec_req)
    assert rec_res.status_code == 200, rec_res.text
    rec_data = rec_res.json()

    # Call /provenance/situations/generate
    prov_res = client.post(
        "/provenance/situations/generate",
        json={"request": rec_req, "result": rec_data},
    )
    assert prov_res.status_code == 200, prov_res.text
    prov_data = prov_res.json()
    scenarios = prov_data.get("scenarios", [])
    assert len(scenarios) >= 3

    # Check Scenario 1 is dynamically tailored
    sc1 = scenarios[0]
    assert "75,000 MT" in sc1["base_case_text"]
    assert origin in sc1["base_case_text"]
    assert discharge in sc1["title"]
    assert len(sc1["comparative_metrics"]) >= 3
    assert "ref-cargo" in sc1["citations"]
    assert "75,000 MT" in sc1["citations"]["ref-cargo"]["token"]

    # Check Scenario 2 evaluates commitment mode
    sc2 = scenarios[1]
    assert sc2["id"] == "commitment_economics_alpha"
    assert len(sc2["comparative_metrics"]) >= 3


def test_provenance_situations_generate_dynamic_for_multi_voyage_split():
    """Verify that a large volume recommendation generates multi-voyage split scenarios."""
    from backend.warehouse import repository
    origins = repository.get_valid_origins()
    discharge_ports = repository.get_valid_dest_ports()
    origin = origins[0] if origins else "Australia (Hay Point)"
    discharge = "Dhamra" if "Dhamra" in discharge_ports else discharge_ports[0]

    rec_req = {
        "cargo_quantity": 160000,
        "origin_port": origin,
        "discharge_ports": [discharge],
        "timing_flexibility_days": 30,
    }
    rec_res = client.post("/recommendation", json=rec_req)
    assert rec_res.status_code == 200, rec_res.text
    rec_data = rec_res.json()

    # Call /provenance/situations/generate
    prov_res = client.post(
        "/provenance/situations/generate",
        json={"request": rec_req, "result": rec_data},
    )
    assert prov_res.status_code == 200, prov_res.text
    prov_data = prov_res.json()
    scenarios = prov_data.get("scenarios", [])
    assert len(scenarios) >= 3

    # Check Scenario 1 is dynamically tailored to 160,000 MT
    sc1 = scenarios[0]
    assert "160,000 MT" in sc1["base_case_text"]
    assert origin in sc1["base_case_text"]
    assert discharge in sc1["title"]
