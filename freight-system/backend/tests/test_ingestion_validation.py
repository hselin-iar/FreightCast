"""
tests/test_ingestion_validation.py — unit tests for validation.py's four checks.

DOC4 Build Step 1 Done When:
  - validation.py's four checks pass unit tests against known-good and known-bad
    fixture rows.
  - A malformed row is rejected with a logged reason rather than silently dropped
    or crashing the run.

Run: pytest backend/tests/test_ingestion_validation.py -v
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from backend.ingestion.validation import (
    BDI_SCHEMA,
    BUNKER_SCHEMA,
    PORT_CONSTRAINT_SCHEMA,
    RATE_5TC_SCHEMA,
    MACRO_FEATURES_SCHEMA,
    IngestSchema,
    ColumnSpec,
    validate,
)
from backend.ingestion.types import ValidatedBatch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bdi_row(date_offset: int = 1, bdi: float = 1800.0, source: str = "test") -> dict:
    return {
        "date": (date.today() - timedelta(days=date_offset)).isoformat(),
        "bdi_value": bdi,
        "source": source,
    }


def _bunker_row(date_offset: int = 1, price: float = 620.0) -> dict:
    return {
        "date": (date.today() - timedelta(days=date_offset)).isoformat(),
        "price_usd": price,
        "fuel_code": "VLSFO_USD",
    }


# ---------------------------------------------------------------------------
# 1. Schema / type check
# ---------------------------------------------------------------------------

class TestSchemaCheck:
    def test_known_good_row_passes(self):
        df = pd.DataFrame([_bdi_row()])
        batch = validate(df, BDI_SCHEMA)
        assert len(batch.rows) == 1
        assert len(batch.rejected) == 0

    def test_missing_required_column_rejects_all_rows(self):
        df = pd.DataFrame([{"date": date.today().isoformat(), "source": "test"}])
        # "bdi_value" is missing
        batch = validate(df, BDI_SCHEMA)
        assert len(batch.rejected) == 1
        assert "bdi_value" in batch.rejected[0].reason.lower() or "missing" in batch.rejected[0].reason.lower()

    def test_wrong_dtype_numeric_column_rejects_row(self):
        row = _bdi_row()
        row["bdi_value"] = "not_a_number"
        df = pd.DataFrame([row])
        batch = validate(df, BDI_SCHEMA)
        assert len(batch.rejected) == 1
        assert "bdi_value" in batch.rejected[0].reason

    def test_nan_in_required_column_rejects_row(self):
        import math
        row = _bdi_row()
        row["bdi_value"] = float("nan")
        df = pd.DataFrame([row])
        batch = validate(df, BDI_SCHEMA)
        # NaN in a required column should reject
        assert len(batch.rejected) == 1

    def test_multiple_rows_only_bad_one_rejected(self):
        good = _bdi_row(date_offset=2)
        bad = _bdi_row(date_offset=1)
        bad["bdi_value"] = "BAD"
        df = pd.DataFrame([good, bad])
        batch = validate(df, BDI_SCHEMA)
        assert len(batch.rows) == 1
        assert len(batch.rejected) == 1

    def test_empty_dataframe_returns_empty_batch_with_alert(self):
        df = pd.DataFrame()
        batch = validate(df, BDI_SCHEMA)
        assert len(batch.rows) == 0
        assert len(batch.rejected) == 0
        assert any("empty" in a.lower() for a in batch.alerts)


# ---------------------------------------------------------------------------
# 2. Freshness check
# ---------------------------------------------------------------------------

class TestFreshnessCheck:
    def test_fresh_data_no_alert(self):
        df = pd.DataFrame([_bdi_row(date_offset=1)])
        batch = validate(df, BDI_SCHEMA)
        freshness_alerts = [a for a in batch.alerts if "freshness" in a.lower()]
        assert freshness_alerts == []

    def test_stale_data_raises_alert_but_keeps_row(self):
        stale_row = _bdi_row()
        stale_row["date"] = (date.today() - timedelta(days=10)).isoformat()
        df = pd.DataFrame([stale_row])
        batch = validate(df, BDI_SCHEMA)
        # Row should still be in batch (freshness is an alert, not a rejection)
        assert len(batch.rows) == 1
        freshness_alerts = [a for a in batch.alerts if "freshness" in a.lower()]
        assert len(freshness_alerts) == 1

    def test_port_constraint_schema_no_freshness_check(self):
        """Port constraints have no date column — no freshness alert expected."""
        row = {
            "port_name": "TestPort", "max_draft_m": 14.0, "max_loa_m": 250.0,
            "max_beam_m": 43.0, "handling_rate_tpd": 40000.0, "tidal_dependent": "true",
        }
        df = pd.DataFrame([row])
        batch = validate(df, PORT_CONSTRAINT_SCHEMA)
        freshness_alerts = [a for a in batch.alerts if "freshness" in a.lower()]
        assert freshness_alerts == []


# ---------------------------------------------------------------------------
# 3. Gap-fill check
# ---------------------------------------------------------------------------

class TestGapFill:
    def test_weekend_gap_forward_filled_and_alert_raised(self):
        """Create a Mon and Wed row; Tue gap should be filled."""
        rows = []
        # Walk back to find a Mon-Wed span
        d = date.today()
        while d.weekday() != 0:   # find a Monday
            d -= timedelta(days=1)
        # Monday + Wednesday (skip Tuesday)
        rows.append({"date": d.isoformat(), "bdi_value": 1800.0, "source": "test"})
        rows.append({"date": (d + timedelta(days=2)).isoformat(), "bdi_value": 1900.0, "source": "test"})
        df = pd.DataFrame(rows)
        batch = validate(df, BDI_SCHEMA)
        # Gap-fill alert should be present
        gap_alerts = [a for a in batch.alerts if "gap" in a.lower() or "fill" in a.lower()]
        assert len(gap_alerts) >= 1
        # Filled rows should include Tuesday
        dates = {r["date"] if isinstance(r["date"], str) else str(r["date"]) for r in batch.rows}
        tue = (d + timedelta(days=1)).isoformat()
        assert tue in dates

    def test_no_gaps_no_gap_alert(self):
        """Consecutive business days — no gap-fill alert."""
        rows = []
        d = date.today()
        while d.weekday() != 0:
            d -= timedelta(days=1)
        for i in range(3):
            rows.append({"date": (d + timedelta(days=i)).isoformat(), "bdi_value": 1800.0 + i, "source": "test"})
        df = pd.DataFrame(rows)
        batch = validate(df, BDI_SCHEMA)
        gap_alerts = [a for a in batch.alerts if "gap" in a.lower() or "fill" in a.lower()]
        assert gap_alerts == []


# ---------------------------------------------------------------------------
# 4. Plausibility check
# ---------------------------------------------------------------------------

class TestPlausibilityCheck:
    def test_value_below_min_rejected(self):
        row = _bdi_row()
        row["bdi_value"] = -100.0    # below min_val=0.0
        df = pd.DataFrame([row])
        batch = validate(df, BDI_SCHEMA)
        assert len(batch.rejected) == 1
        assert "< min" in batch.rejected[0].reason

    def test_value_above_max_rejected(self):
        row = _bdi_row()
        row["bdi_value"] = 99999.0   # above max_val=30_000.0
        df = pd.DataFrame([row])
        batch = validate(df, BDI_SCHEMA)
        assert len(batch.rejected) == 1
        assert "> max" in batch.rejected[0].reason

    def test_borderline_values_accepted(self):
        row_min = _bdi_row(); row_min["bdi_value"] = 0.0
        row_max = _bdi_row(date_offset=2); row_max["bdi_value"] = 30_000.0
        df = pd.DataFrame([row_min, row_max])
        batch = validate(df, BDI_SCHEMA)
        assert len(batch.rejected) == 0

    def test_port_constraint_out_of_range_draft_rejected(self):
        row = {
            "port_name": "BadPort", "max_draft_m": 0.5,   # below min=5.0
            "max_loa_m": 250.0, "max_beam_m": 43.0,
            "handling_rate_tpd": 40000.0, "tidal_dependent": "false",
        }
        df = pd.DataFrame([row])
        batch = validate(df, PORT_CONSTRAINT_SCHEMA)
        assert len(batch.rejected) == 1
        assert "< min" in batch.rejected[0].reason

    def test_bunker_unrealistic_price_rejected(self):
        row = _bunker_row(); row["price_usd"] = 5000.0   # above max=2_500.0
        df = pd.DataFrame([row])
        batch = validate(df, BUNKER_SCHEMA)
        assert len(batch.rejected) == 1

    def test_good_row_never_crashes(self):
        """validate() must never raise an uncaught exception on any input."""
        try:
            df = pd.DataFrame([_bdi_row()])
            validate(df, BDI_SCHEMA)
        except Exception as exc:
            pytest.fail(f"validate() raised unexpectedly: {exc}")

    def test_completely_malformed_row_never_crashes(self):
        """A row that's entirely garbage should be rejected cleanly, not crash."""
        df = pd.DataFrame([{"date": "not-a-date", "bdi_value": "bad", "source": 12345}])
        try:
            batch = validate(df, BDI_SCHEMA)
        except Exception as exc:
            pytest.fail(f"validate() raised unexpectedly on malformed row: {exc}")
        assert len(batch.rejected) >= 1


# ---------------------------------------------------------------------------
# 5. Integration: run() functions smoke test
# ---------------------------------------------------------------------------

class TestRunSmoke:
    """
    Smoke tests: each batch module's run() must return IngestResult without crashing.
    Done When criterion: rows_ingested > 0 for fixture-backed modules.
    """

    def test_bdi_run(self):
        from backend.ingestion.batch.bdi_ingest import run
        result = run()
        assert result.rows_ingested > 0, f"BDI: expected rows_ingested>0, got {result}"

    def test_bunker_run_fallback(self):
        """With no API key set, must use fallback CSV and return rows."""
        import os; os.environ.pop("OILPRICEAPI_API_KEY", None)
        from backend.ingestion.batch import bunker_ingest
        # Reload to pick up env change
        import importlib; importlib.reload(bunker_ingest)
        result = bunker_ingest.run()
        assert result.rows_ingested > 0, f"Bunker fallback: expected rows_ingested>0, got {result}"
        stale_alerts = [a for a in result.alerts if "assumed" in a.lower() or "provenance" in a.lower()]
        assert stale_alerts, "Bunker fallback must produce a stale/assumed alert"

    def test_port_constraint_run_pending_verification(self):
        from backend.ingestion.batch.port_constraint_ingest import run
        result = run()
        # rows_ingested=0 by design (pending_verification, not active)
        assert result.rows_ingested == 0
        assert len(result.pending_verification) > 0, (
            "Port constraints: expected pending_verification to have rows"
        )

    def test_fleet_demand_run(self):
        from backend.ingestion.batch.fleet_demand_ingest import run
        result = run()
        assert result.rows_ingested > 0, f"Fleet demand: expected rows_ingested>0, got {result}"

    def test_rate_5tc_run(self):
        from backend.ingestion.batch.rate_5tc_ingest import run
        result = run()
        assert result.rows_ingested > 0, f"Rate 5TC: expected rows_ingested>0, got {result}"

    def test_macro_features_run(self):
        from backend.ingestion.batch.macro_features_ingest import run
        result = run()
        assert result.rows_ingested > 0, f"Macro features: expected rows_ingested>0, got {result}"

    def test_operational_evidence_run(self):
        from backend.ingestion.batch.operational_evidence_ingest import run
        result = run()
        assert result.rows_ingested > 0, f"Operational evidence: expected rows_ingested>0, got {result}"
