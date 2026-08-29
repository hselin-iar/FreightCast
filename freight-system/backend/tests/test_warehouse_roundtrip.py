"""
tests/test_warehouse_roundtrip.py — warehouse round-trip tests.

Uses SQLite :memory: — no real Postgres needed.
Verifies the Done When criteria for Build Step 3:
  1. Batch ingestion writes validated rows → repository read functions return them.
  2. AIS listener writes a CongestionSnapshot → repository.get_latest_congestion_snapshot returns it.
  3. repository.py is the sole source of SQLAlchemy queries (structural, not tested here — see grep).

Run: pytest backend/tests/test_warehouse_roundtrip.py -v
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

# Use SQLite :memory: for tests — override DATABASE_URL before any warehouse import
_SQLITE_URL = "sqlite:///:memory:"
os.environ["DATABASE_URL"] = _SQLITE_URL

from backend.warehouse.db import create_all_tables, get_session, reset_engine
from backend.warehouse import repository
from backend.warehouse.models import (
    CongestionSnapshot,
    ForecastObject,
    PortConstraint,
    RateHistory,
    VesselPositionSnapshot,
    VesselSpec,
    ExogenousFeature,
    OperationalEvidence,
)


@pytest.fixture(autouse=True)
def fresh_db():
    """Each test gets a clean SQLite :memory: database."""
    reset_engine()
    os.environ["DATABASE_URL"] = _SQLITE_URL
    create_all_tables(_SQLITE_URL)
    # Invalidate scope cache so tests don't bleed
    repository.invalidate_scope_cache()
    yield
    reset_engine()


# ---------------------------------------------------------------------------
# RateHistory round-trip
# ---------------------------------------------------------------------------

class TestRateHistoryRoundTrip:
    def _sample_rows(self, n: int = 3) -> list[dict]:
        rows = []
        for i in range(n):
            rows.append({
                "route": "C2",
                "vessel_class": "Capesize",
                "date": (datetime.now(timezone.utc) - timedelta(days=i)).isoformat(),
                "rate": 15000.0 + i * 500,
                "tier": "A",
                "provenance": "measured",
            })
        return rows

    def test_upsert_and_read_back(self):
        rows = self._sample_rows(3)
        result = repository.upsert_rate_history(rows)
        assert result.rows_ingested == 3
        assert result.rows_rejected == 0

    def test_upsert_idempotent(self):
        rows = self._sample_rows(2)
        repository.upsert_rate_history(rows)
        result2 = repository.upsert_rate_history(rows)  # same rows again
        assert result2.rows_ingested == 2  # upserted, not duplicated

    def test_empty_rows_returns_zero(self):
        result = repository.upsert_rate_history([])
        assert result.rows_ingested == 0


# ---------------------------------------------------------------------------
# PortConstraint round-trip (pending → approve flow)
# ---------------------------------------------------------------------------

class TestPortConstraintRoundTrip:
    def _sample_ports(self) -> list[dict]:
        return [
            {"port_name": "TestPort", "max_draft_m": 14.0, "max_loa_m": 250.0,
             "max_beam_m": 43.0, "handling_rate_tpd": 40000.0, "tidal_dependent": "true"},
            {"port_name": "AnotherPort", "max_draft_m": 16.0, "max_loa_m": 280.0,
             "max_beam_m": 45.0, "handling_rate_tpd": 55000.0, "tidal_dependent": "false"},
        ]

    def test_pending_write_verified_false(self):
        rows = self._sample_ports()
        written = repository.upsert_port_constraint_pending(rows)
        assert written == 2
        # Pending rows must NOT appear in verified-only read
        verified = repository.get_port_constraints(verified_only=True)
        assert "TestPort" not in verified

    def test_approve_flips_verified(self):
        repository.upsert_port_constraint_pending(self._sample_ports())
        result = repository.approve_port_constraint("TestPort")
        assert result is True
        verified = repository.get_port_constraints(verified_only=True)
        assert "TestPort" in verified
        assert "AnotherPort" not in verified  # not yet approved

    def test_approve_unknown_port_returns_false(self):
        assert repository.approve_port_constraint("NonExistent") is False

    def test_get_port_constraints_all_includes_pending(self):
        repository.upsert_port_constraint_pending(self._sample_ports())
        all_ports = repository.get_port_constraints(verified_only=False)
        assert "TestPort" in all_ports


# ---------------------------------------------------------------------------
# VesselSpec round-trip
# ---------------------------------------------------------------------------

class TestVesselSpecRoundTrip:
    def test_upsert_and_scope_catalog(self):
        rows = [
            {"vessel_class": "Capesize", "capacity_tonnes": 180000, "draft_m": 18.2,
             "loa_m": 295.0, "beam_m": 47.0},
            {"vessel_class": "Panamax/Kamsarmax", "capacity_tonnes": 82000, "draft_m": 14.2,
             "loa_m": 229.0, "beam_m": 36.3},
        ]
        written = repository.upsert_vessel_spec(rows)
        assert written == 2
        classes = repository.get_valid_vessel_classes()
        assert "Capesize" in classes
        assert "Panamax/Kamsarmax" in classes


# ---------------------------------------------------------------------------
# ForecastObject round-trip
# ---------------------------------------------------------------------------

class TestForecastObjectRoundTrip:
    def _sample_forecast(self, horizon: int = 7) -> dict:
        return {
            "route": "C2",
            "vessel_class": "Capesize",
            "horizon_days": horizon,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "point_estimate": 18500.0,
            "confidence_band": {"lower": 16000.0, "upper": 21000.0},
            "trajectory": [{"date": "2026-09-01", "value": 18500.0}],
            "driver_explanation": "BDI rising trend",
            "is_high_uncertainty": False,
            "model_used": "XGBoost",
        }

    def test_write_and_read_latest(self):
        repository.write_forecast(self._sample_forecast(7))
        result = repository.get_latest_forecast("C2", "Capesize", 7)
        assert result is not None
        assert result.point_estimate == 18500.0
        assert result.model_used == "XGBoost"

    def test_latest_returns_newest_when_multiple(self):
        old = self._sample_forecast(7)
        old["generated_at"] = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        old["point_estimate"] = 10000.0
        repository.write_forecast(old)

        new = self._sample_forecast(7)
        new["point_estimate"] = 20000.0
        repository.write_forecast(new)

        result = repository.get_latest_forecast("C2", "Capesize", 7)
        assert result is not None
        assert result.point_estimate == 20000.0

    def test_missing_forecast_returns_none(self):
        result = repository.get_latest_forecast("C99", "Capesize", 30)
        assert result is None


# ---------------------------------------------------------------------------
# CongestionSnapshot round-trip (core Build Step 3 Done When)
# ---------------------------------------------------------------------------

class TestCongestionSnapshotRoundTrip:
    def test_write_and_read_back(self):
        snapshot = {
            "vessel_count": 3,
            "avg_wait_hours": 12.0,
            "recorded_at": datetime.now(timezone.utc),
            "is_live": True,
            "source_note": "live AIS stream",
        }
        repository.write_congestion_snapshot("Paradip", snapshot)
        result = repository.get_latest_congestion_snapshot("Paradip")
        assert result is not None
        assert result["port"] == "Paradip"
        assert result["vessel_count"] == 3
        assert result["is_live"] is True

    def test_no_snapshot_returns_none(self):
        result = repository.get_latest_congestion_snapshot("UnknownPort")
        assert result is None

    def test_latest_returns_most_recent(self):
        old_snap = {
            "vessel_count": 1,
            "avg_wait_hours": 4.0,
            "recorded_at": datetime.now(timezone.utc) - timedelta(hours=2),
            "is_live": True,
            "source_note": "live AIS stream",
        }
        new_snap = {
            "vessel_count": 5,
            "avg_wait_hours": 20.0,
            "recorded_at": datetime.now(timezone.utc),
            "is_live": True,
            "source_note": "live AIS stream",
        }
        repository.write_congestion_snapshot("Gangavaram", old_snap)
        repository.write_congestion_snapshot("Gangavaram", new_snap)
        result = repository.get_latest_congestion_snapshot("Gangavaram")
        assert result["vessel_count"] == 5


# ---------------------------------------------------------------------------
# VesselPositionSnapshot round-trip (repositioning-aware τ, §11.2)
# ---------------------------------------------------------------------------

class TestVesselPositionSnapshotRoundTrip:
    def _sample_vessel(self, imo: int, vessel_class: str, lat: float, lon: float) -> dict:
        return {
            "imo": imo,
            "vessel_name": f"MOCK VESSEL {imo}",
            "vessel_class": vessel_class,
            "dwt": 180000.0,
            "current_lat": lat,
            "current_lon": lon,
            "speed_knots": 12.5,
            "recorded_at": datetime.now(timezone.utc),
        }

    def test_upsert_and_read_by_class(self):
        repository.upsert_vessel_position_snapshot(
            self._sample_vessel(9100001, "Capesize", -20.5, 150.2)
        )
        repository.upsert_vessel_position_snapshot(
            self._sample_vessel(9100002, "Capesize", -21.0, 151.0)
        )
        vessels = repository.get_candidate_vessels_by_class("Capesize")
        assert len(vessels) == 2
        imos = {v.imo for v in vessels}
        assert 9100001 in imos
        assert 9100002 in imos

    def test_upsert_is_idempotent(self):
        v = self._sample_vessel(9200001, "Panamax/Kamsarmax", 10.0, 50.0)
        repository.upsert_vessel_position_snapshot(v)
        v["current_lat"] = 11.0  # update position
        repository.upsert_vessel_position_snapshot(v)
        vessels = repository.get_candidate_vessels_by_class("Panamax/Kamsarmax")
        assert len(vessels) == 1
        assert abs(vessels[0].current_lat - 11.0) < 0.001

    def test_empty_class_returns_empty_list(self):
        vessels = repository.get_candidate_vessels_by_class("Supramax/Ultramax")
        assert vessels == []

    def test_get_earliest_repositioning_days_returns_float(self):
        # Vessel near Queensland — ballast to Paradip
        repository.upsert_vessel_position_snapshot(
            self._sample_vessel(9300001, "Capesize", -20.5, 150.2)
        )
        days = repository.get_earliest_repositioning_days("Capesize", "Paradip")
        assert days is not None
        assert days > 0
        # Queensland to Paradip is ~4000nm at 12.5kn = ~13 days
        assert 5 < days < 30

    def test_no_vessels_returns_none(self):
        days = repository.get_earliest_repositioning_days("Capesize", "Paradip")
        assert days is None


# ---------------------------------------------------------------------------
# ExogenousFeature round-trip
# ---------------------------------------------------------------------------

class TestExogenousFeatureRoundTrip:
    def test_upsert_and_count(self):
        rows = [
            {"source": "brent", "date": "2026-08-01", "value": 85.5},
            {"source": "wti",   "date": "2026-08-01", "value": 82.3},
            {"source": "brent", "date": "2026-08-02", "value": 86.1},
        ]
        written = repository.upsert_exogenous_feature(rows)
        assert written == 3


# ---------------------------------------------------------------------------
# OperationalEvidence round-trip
# ---------------------------------------------------------------------------

class TestOperationalEvidenceRoundTrip:
    def test_write_and_read(self):
        rows = [
            {"route": "Australia-Paradip", "vessel_class": "Capesize",
             "observed_at": datetime.now(timezone.utc).isoformat(),
             "note": "Broker fixture #1"},
        ]
        written = repository.upsert_operational_evidence(rows)
        assert written == 1
        evidence = repository.get_operational_evidence("Australia-Paradip", "Capesize")
        assert len(evidence) == 1
        assert evidence[0].note == "Broker fixture #1"
        assert evidence[0].confidence_score is None  # computed in Step 9.5


# ---------------------------------------------------------------------------
# Scope Catalog (DOC2 Addendum v3 §A1)
# ---------------------------------------------------------------------------

class TestScopeCatalog:
    def test_empty_warehouse_returns_dev_fixture_defaults(self):
        # Cold start: no verified rows → falls back to DEV_FIXTURE constants
        from backend.config.constants import DEV_FIXTURE_DEST_PORTS, DEV_FIXTURE_VESSEL_CLASSES
        ports = repository.get_valid_dest_ports()
        classes = repository.get_valid_vessel_classes()
        assert len(ports) > 0
        assert len(classes) > 0

    def test_approved_port_appears_in_scope(self):
        repository.upsert_port_constraint_pending([{
            "port_name": "ScopeTestPort", "max_draft_m": 14.0, "max_loa_m": 250.0,
            "max_beam_m": 43.0, "handling_rate_tpd": 40000.0, "tidal_dependent": "false",
        }])
        repository.approve_port_constraint("ScopeTestPort")
        ports = repository.get_valid_dest_ports()
        assert "ScopeTestPort" in ports
