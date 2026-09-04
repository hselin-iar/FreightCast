import pytest
from fastapi.testclient import TestClient
from backend.api.main import app
from backend.warehouse.db import create_all_tables, get_session
from backend.warehouse.models import PortConstraint

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_port_test_db():
    create_all_tables()
    with get_session() as session:
        for name, draft, loa, beam, tpd, tidal in [
            ("Paradip", 14.5, 260.0, 43.0, 40000.0, True),
            ("Gangavaram", 18.5, 300.0, 50.0, 60000.0, False),
            ("Dhamra", 15.0, 280.0, 45.0, 50000.0, True),
            ("Australia (Hay Point)", 19.0, 330.0, 55.0, 80000.0, False),
            ("South Africa (Richards Bay)", 18.0, 310.0, 50.0, 70000.0, False),
            ("Indonesia (East Kalimantan)", 15.5, 270.0, 45.0, 45000.0, False),
        ]:
            existing = session.query(PortConstraint).filter_by(name=name).first()
            if not existing:
                session.add(PortConstraint(
                    name=name, max_draft_m=draft, max_loa_m=loa, max_beam_m=beam,
                    handling_rate_tpd=tpd, tidal_dependent=tidal, verified=True, source="measured"
                ))
        session.commit()
    yield


def test_get_port_constraints_endpoint():
    """Verify GET /port-constraints returns complete verified hydrodynamics and coordinates."""
    resp = client.get("/port-constraints")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 6

    names = {p["name"] for p in data}
    expected_ports = {
        "Paradip",
        "Gangavaram",
        "Dhamra",
        "Australia (Hay Point)",
        "South Africa (Richards Bay)",
        "Indonesia (East Kalimantan)",
    }
    assert expected_ports.issubset(names), f"Missing ports: {expected_ports - names}"

    for item in data:
        assert item["max_draft_m"] > 0
        assert item["max_loa_m"] > 0
        assert item["max_beam_m"] > 0
        assert item["handling_rate_tpd"] > 0
        assert item["role"] in ("discharge", "load")
        assert -90.0 <= item["lat"] <= 90.0
        assert -180.0 <= item["lon"] <= 180.0
        assert item["verified"] is True


def test_port_hydrodynamic_clearance_invariants():
    """Verify physical constraints align with Naval Architecture standards."""
    resp = client.get("/port-constraints")
    assert resp.status_code == 200
    by_name = {p["name"]: p for p in resp.json()}

    # Gangavaram is deepwater: capable of docking fully-laden Capesize (>18m)
    assert by_name["Gangavaram"]["max_draft_m"] >= 18.0
    # Paradip and Dhamra are draft-constrained for full Capesize without dredging/lightening (<18m)
    assert by_name["Paradip"]["max_draft_m"] < 18.0
    assert by_name["Dhamra"]["max_draft_m"] < 18.0
