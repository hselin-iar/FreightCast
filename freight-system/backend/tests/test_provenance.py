"""
tests/test_provenance.py — Build Step 9: Provenance & Explainability Layer
===========================================================================
DOC3 §FEATURE: Provenance & Explainability Layer (no dedicated test file
specified, but DOC3 says test_decision_engine_milp.py should assert that
commitment_benchmark-derived terms are tagged "assumed").

This file covers:
  1. provenance.py helpers: tag_measured, tag_modeled, tag_assumed
  2. CostBreakdown.provenance is "assumed" + note is non-empty
  3. Strategy.provenance is "assumed" + provenance_note set when default benchmark used
  4. Strategy.provenance is "modeled" when real benchmark provided
  5. compute_sensitivity() runs against a solved Strategy without re-invoking the MILP
  6. ForecastObject.provenance is "modeled" (as set by forecasting.py)
"""
from __future__ import annotations

import pytest

from backend.engine.provenance import (
    Provenance,
    SensitivityResult,
    compute_sensitivity,
    tag_assumed,
    tag_measured,
    tag_modeled,
)


# ---------------------------------------------------------------------------
# 1. Tagging helpers
# ---------------------------------------------------------------------------

class TestTagHelpers:
    def test_tag_measured_returns_literal(self):
        result = tag_measured()
        assert result == "measured"

    def test_tag_modeled_returns_literal(self):
        result = tag_modeled()
        assert result == "modeled"

    def test_tag_modeled_with_uncertainty_still_returns_modeled(self):
        result = tag_modeled(uncertainty_flag=True)
        assert result == "modeled"

    def test_tag_assumed_returns_tuple(self):
        prov, note = tag_assumed("placeholder constant for tax rate")
        assert prov == "assumed"
        assert "placeholder" in note.lower()

    def test_tag_assumed_requires_non_empty_note(self):
        with pytest.raises(ValueError, match="non-empty note"):
            tag_assumed("")

    def test_tag_assumed_note_travels_with_value(self):
        note_text = "DEFAULT_COMMITMENT_BENCHMARK_PCT used — not cargo-specific"
        prov, note = tag_assumed(note_text)
        assert note == note_text


# ---------------------------------------------------------------------------
# 2. CostBreakdown carries typed provenance + note
# ---------------------------------------------------------------------------

class TestCostBreakdownProvenance:
    """Tests that build_cost_coefficient() returns CostBreakdown with correct provenance."""

    def _make_route_physics(self):
        from backend.engine.cost_terms import RoutePhysics
        return RoutePhysics(
            origin="Hay Point, Australia",
            destination="Paradip, India",
            distance_nm=4899.0,
            laden_consumption_tpd=41.0,
            ballast_consumption_tpd=32.0,
        )

    def test_cost_breakdown_provenance_is_assumed(self):
        from backend.engine.cost_terms import build_cost_coefficient
        physics = self._make_route_physics()
        bd = build_cost_coefficient(
            quantity=70_000.0,
            mode="locked",
            rate_at_tau=13.80,
            base_rate_at_lock_day=13.80,
            commitment_benchmark_pct=95.0,
            route_physics=physics,
            bunker_price_usd_per_tonne=620.0,
            ballast_consumption_tpd=32.0,
            handling_rate_tpd=35_000.0,
            repositioning_days=0.0,
            idle_days=0.0,
            requires_lightening=False,
            lightening_penalty_days=0.0,
        )
        assert bd.provenance == "assumed"
        assert bd.provenance_note is not None
        assert len(bd.provenance_note) > 0

    def test_cost_breakdown_total_equals_bucket_sum(self):
        from backend.engine.cost_terms import build_cost_coefficient
        physics = self._make_route_physics()
        bd = build_cost_coefficient(
            quantity=70_000.0,
            mode="spot",
            rate_at_tau=14.00,
            base_rate_at_lock_day=13.80,
            commitment_benchmark_pct=95.0,
            route_physics=physics,
            bunker_price_usd_per_tonne=620.0,
            ballast_consumption_tpd=32.0,
            handling_rate_tpd=35_000.0,
            repositioning_days=0.0,
            idle_days=0.0,
            requires_lightening=False,
            lightening_penalty_days=0.0,
        )
        expected = round(
            bd.ocean_freight + bd.bunker + bd.opex + bd.other_cost + bd.port_handling
            + bd.lightening_extra + bd.tax + bd.waiting, 2
        )
        assert bd.total == expected


# ---------------------------------------------------------------------------
# 3 & 4. Strategy.provenance from decision.solve()
# ---------------------------------------------------------------------------

class TestStrategyProvenance:
    """
    Verifies that Strategy carries correctly typed provenance + note.
    Uses an in-memory SQLite session, same pattern as other integration tests.
    """

    @pytest.fixture(autouse=True)
    def _setup_db(self):
        """Minimal in-memory DB with one seeded route for a solve() call."""
        import math
        import os
        from datetime import datetime, timedelta, timezone

        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool

        from backend.warehouse import db as _db
        from backend.warehouse import repository
        from backend.warehouse.models import Base, RoutePhysics

        # Inject sqlite:// into env so get_engine() doesn't raise on missing DATABASE_URL
        sqlite_url = "sqlite:///:memory:"
        os.environ["DATABASE_URL"] = sqlite_url

        engine = create_engine(
            sqlite_url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            echo=False,
        )
        _db._engine = engine
        _db._SessionFactory = sessionmaker(bind=engine, expire_on_commit=False)
        Base.metadata.create_all(engine)
        repository.invalidate_scope_cache()

        # Vessel specs
        repository.upsert_vessel_spec([
            {"vessel_class": "Panamax", "capacity_tonnes": 75_000.0, "draft_m": 14.5, "loa_m": 225.0, "beam_m": 32.3},
            {"vessel_class": "Supramax", "capacity_tonnes": 58_000.0, "draft_m": 13.0, "loa_m": 190.0, "beam_m": 32.2},
        ])

        # Port constraints
        repository.upsert_port_constraint_pending([
            {"port_name": "Paradip, India", "max_draft_m": 16.0, "max_loa_m": 300.0,
             "max_beam_m": 46.0, "handling_rate_tpd": 35_000.0, "tidal_dependent": True},
        ])
        repository.approve_port_constraint("Paradip, India")

        # Route physics
        from sqlalchemy.orm import Session
        with Session(engine) as session:
            session.add(RoutePhysics(
                origin="Hay Point, Australia",
                destination="Paradip, India",
                distance_nm=4899.0,
                laden_consumption_tpd=41.0,
                ballast_consumption_tpd=32.0,
            ))
            session.commit()

        # Bunker price
        from datetime import datetime, timezone
        repository.write_congestion_snapshot("bunker", {
            "vessel_count": 0,
            "avg_wait_hours": 0.0,
            "bunker_price_usd": 620.0,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "is_live": False,
            "source_note": "test fixture",
        })

        # Rate history — 100 rows
        now = datetime.now(timezone.utc)
        rate_rows = []
        for i in range(100):
            d = now - timedelta(days=100 - i)
            rate_rows.append({
                "route": "Hay Point, Australia→Paradip, India",
                "vessel_class": "Panamax",
                "date": d.isoformat(),
                "rate": round(13.80 * (1 + math.sin(i / 8.0) * 0.05), 2),
                "tier": "A",
                "provenance": "measured",
            })
        repository.upsert_rate_history(rate_rows)

        # Train forecasts
        from backend.engine import forecasting
        forecasting.train_and_evaluate(
            routes=["Hay Point, Australia→Paradip, India"],
            vessel_classes=["Panamax"],
            horizons=[14],
        )

    def test_strategy_provenance_assumed_when_default_benchmark(self):
        """When commitment_benchmark_pct is None (uses system default), provenance must be 'assumed'."""
        from backend.engine import decision
        strategy, _ = decision.solve(
            cargo_quantity=70_000.0,
            origin_port="Hay Point, Australia",
            discharge_ports=["Paradip, India"],
            timing_flexibility_days=14,
            commitment_benchmark_pct=None,   # triggers default → "assumed"
        )
        assert strategy.provenance == "assumed", (
            f"Expected 'assumed' when default benchmark used, got {strategy.provenance!r}"
        )
        assert strategy.provenance_note is not None
        assert "DEFAULT_COMMITMENT_BENCHMARK_PCT" in strategy.provenance_note

    def test_strategy_provenance_modeled_when_explicit_benchmark(self):
        """When commitment_benchmark_pct is explicitly supplied, provenance must be 'modeled'."""
        from backend.engine import decision
        strategy, _ = decision.solve(
            cargo_quantity=70_000.0,
            origin_port="Hay Point, Australia",
            discharge_ports=["Paradip, India"],
            timing_flexibility_days=14,
            commitment_benchmark_pct=92.0,   # explicit → "modeled"
        )
        assert strategy.provenance == "modeled", (
            f"Expected 'modeled' when explicit benchmark supplied, got {strategy.provenance!r}"
        )
        assert strategy.provenance_note is None

    def test_strategy_solved_via_milp_not_fallback(self):
        """Confirmed: normal path returns solved_via='milp', not always hybrid_fallback."""
        from backend.engine import decision
        strategy, _ = decision.solve(
            cargo_quantity=70_000.0,
            origin_port="Hay Point, Australia",
            discharge_ports=["Paradip, India"],
            timing_flexibility_days=14,
        )
        assert strategy.solved_via == "milp"


# ---------------------------------------------------------------------------
# 5. compute_sensitivity — no second MILP solve
# ---------------------------------------------------------------------------

class TestComputeSensitivity:
    """
    compute_sensitivity() is a pure function over already-computed cost terms.
    It must never re-invoke solve() or any warehouse query.
    """

    COST_BREAKDOWN = {
        "ocean_freight": 966_000.0,
        "bunker":        769_891.0,
        "port_handling":  30_000.0,
        "lightening_extra": 0.0,
        "total": 1_765_891.0,
    }
    COST_BY_SCENARIO = {
        "0": {"base": 1_705_201.0, "optimistic": 1_550_000.0, "pessimistic": 1_860_000.0}
    }

    def test_returns_sensitivity_result(self):
        result = compute_sensitivity(self.COST_BREAKDOWN, self.COST_BY_SCENARIO)
        assert isinstance(result, SensitivityResult)

    def test_provenance_is_modeled(self):
        result = compute_sensitivity(self.COST_BREAKDOWN, self.COST_BY_SCENARIO)
        assert result.provenance == "modeled"

    def test_bars_present_for_all_drivers(self):
        result = compute_sensitivity(self.COST_BREAKDOWN, self.COST_BY_SCENARIO)
        driver_labels = {b.driver for b in result.bars}
        assert any("Freight Rate" in d for d in driver_labels)
        assert any("Bunker" in d for d in driver_labels)
        assert any("Scenario" in d for d in driver_labels)

    def test_bars_sorted_largest_delta_first(self):
        result = compute_sensitivity(self.COST_BREAKDOWN, self.COST_BY_SCENARIO)
        deltas = [abs(b.delta_cost) for b in result.bars]
        assert deltas == sorted(deltas, reverse=True)

    def test_perturbation_pct_respected(self):
        result = compute_sensitivity(self.COST_BREAKDOWN, self.COST_BY_SCENARIO, perturbation_pct=10.0)
        assert result.perturbation_pct == 10.0

    def test_freight_up_delta_equals_freight_times_pct(self):
        result = compute_sensitivity(self.COST_BREAKDOWN, {}, perturbation_pct=5.0)
        freight_up = next(b for b in result.bars if "Freight Rate +" in b.driver)
        expected = round(self.COST_BREAKDOWN["ocean_freight"] * 0.05, 2)
        assert abs(freight_up.delta_cost - expected) < 1.0   # within $1

    def test_no_milp_solve_invoked(self, monkeypatch):
        """compute_sensitivity must not call decision.solve() or pulp."""
        import pulp
        called = []
        monkeypatch.setattr(pulp, "LpProblem", lambda *a, **kw: called.append(1) or pulp.LpProblem(*a, **kw))
        compute_sensitivity(self.COST_BREAKDOWN, self.COST_BY_SCENARIO)
        assert not called, "compute_sensitivity must not create a new LpProblem"

    def test_provenance_note_documents_no_resolve(self):
        result = compute_sensitivity(self.COST_BREAKDOWN, self.COST_BY_SCENARIO)
        assert result.provenance_note is not None
        assert "no second milp solve" in result.provenance_note.lower()


# ---------------------------------------------------------------------------
# 6. ForecastObject.provenance is "modeled"
# ---------------------------------------------------------------------------

class TestForecastObjectProvenance:
    def test_forecast_object_has_provenance_column(self):
        from backend.warehouse.models import ForecastObject
        assert hasattr(ForecastObject, "provenance"), \
            "ForecastObject must have a 'provenance' column (Build Step 9)"

    def test_forecast_object_default_provenance_is_modeled(self):
        """The column default is 'modeled' — verify at the column-default level."""
        from backend.warehouse.models import ForecastObject
        import sqlalchemy
        col = ForecastObject.__table__.columns["provenance"]
        # Column-level default should be "modeled"
        assert col.default is not None
        default_val = col.default.arg if hasattr(col.default, "arg") else None
        assert default_val == "modeled", (
            f"Expected column default 'modeled', got {default_val!r}"
        )
