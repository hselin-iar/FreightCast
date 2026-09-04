"""
backend/tests/conftest.py — Global pytest fixtures and engine initialization.
"""
import os
import pytest
from backend.warehouse.db import create_all_tables, reset_engine, get_session
from backend.warehouse.models import PortConstraint


@pytest.fixture(autouse=True, scope="session")
def ensure_default_database_initialized():
    """Ensure baseline tables and port constraints exist across the test session."""
    # Ensure default SQLite URL if not set
    if not os.environ.get("DATABASE_URL"):
        os.environ["DATABASE_URL"] = "sqlite:///freight_dev.db"

    reset_engine()
    create_all_tables()

    # Verify baseline ports exist
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
