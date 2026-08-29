"""
tests/test_constraint_rules.py — Constraint / Feasibility Engine tests.

DOC4 Build Step 5 Done When:
  test_constraint_rules.py passes, including:
    - Boundary cases: draft exactly at limit passes, one cm over fails
    - Both lightening branches: eligible deeper port available / none available

No warehouse or DB required — constraint.py is a pure-function module.

Run: pytest backend/tests/test_constraint_rules.py -v
"""
from __future__ import annotations

import pytest
from backend.engine.constraint import (
    FeasibleOption,
    check_feasibility,
    LIGHTENING_PENALTY_DAYS,
    LIGHTENING_PENALTY_COST_USD,
    PARCEL_FIT_FRACTION,
    _rule1_draft,
    _rule2_loa,
    _rule3_beam,
    _rule4_parcel_fit,
    _rule5_handling_rate,
    _rule6_tidal_window,
    _rule7_lightening,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

PARADIP_PORT = {
    "max_draft_m": 14.0,
    "max_loa_m": 250.0,
    "max_beam_m": 43.0,
    "handling_rate_tpd": 40_000.0,
    "tidal_dependent": "false",
}

GANGAVARAM_PORT = {
    "max_draft_m": 18.5,
    "max_loa_m": 300.0,
    "max_beam_m": 50.0,
    "handling_rate_tpd": 55_000.0,
    "tidal_dependent": "false",
}

TIDAL_PORT = {
    "max_draft_m": 14.0,
    "max_loa_m": 250.0,
    "max_beam_m": 43.0,
    "handling_rate_tpd": 38_000.0,
    "tidal_dependent": "true",
}

CAPESIZE_SPEC = {"draft_m": 18.2, "loa_m": 295.0, "beam_m": 47.0}
PANAMAX_SPEC  = {"draft_m": 14.2, "loa_m": 229.0, "beam_m": 36.3}
SUPRA_SPEC    = {"draft_m": 10.8, "loa_m": 185.0, "beam_m": 32.3}

ALL_VESSEL_SPECS = {
    "Capesize":          CAPESIZE_SPEC,
    "Panamax/Kamsarmax": PANAMAX_SPEC,
    "Supramax/Ultramax": SUPRA_SPEC,
}


# ---------------------------------------------------------------------------
# Rule 1: Draft — unit tests
# ---------------------------------------------------------------------------

class TestRule1Draft:
    def test_draft_exactly_at_limit_passes(self):
        """Boundary case: draft == port max → passes (≤ is the rule)."""
        assert _rule1_draft(14.0, 14.0) is True

    def test_draft_1cm_over_limit_fails(self):
        """Boundary case: 14.01m > 14.0m limit → fails."""
        assert _rule1_draft(14.01, 14.0) is False

    def test_draft_well_under_limit_passes(self):
        assert _rule1_draft(10.5, 14.0) is True

    def test_draft_well_over_limit_fails(self):
        assert _rule1_draft(18.2, 14.0) is False


# ---------------------------------------------------------------------------
# Rule 2: LOA — unit tests
# ---------------------------------------------------------------------------

class TestRule2LOA:
    def test_loa_exactly_at_limit_passes(self):
        assert _rule2_loa(250.0, 250.0) is True

    def test_loa_1m_over_limit_fails(self):
        assert _rule2_loa(251.0, 250.0) is False

    def test_loa_well_under_passes(self):
        assert _rule2_loa(185.0, 250.0) is True


# ---------------------------------------------------------------------------
# Rule 3: Beam — unit tests
# ---------------------------------------------------------------------------

class TestRule3Beam:
    def test_beam_exactly_at_limit_passes(self):
        assert _rule3_beam(43.0, 43.0) is True

    def test_beam_1cm_over_fails(self):
        assert _rule3_beam(43.01, 43.0) is False

    def test_beam_under_passes(self):
        assert _rule3_beam(36.3, 43.0) is True


# ---------------------------------------------------------------------------
# Rule 4: Parcel-fit — unit tests
# ---------------------------------------------------------------------------

class TestRule4ParcelFit:
    def test_small_cargo_on_capesize_flagged(self):
        """20,000 tonnes on a Capesize (capacity ~180,000) → inefficient fit."""
        assert _rule4_parcel_fit(20_000.0, "Capesize") is True

    def test_full_capesize_load_not_flagged(self):
        """Full load → not inefficient."""
        assert _rule4_parcel_fit(150_000.0, "Capesize") is False

    def test_borderline_exactly_at_threshold_not_flagged(self):
        """cargo_quantity == PARCEL_FIT_FRACTION * capacity → NOT flagged (uses strict <)."""
        capesize_capacity = 180_000.0
        threshold = PARCEL_FIT_FRACTION * capesize_capacity
        assert _rule4_parcel_fit(threshold, "Capesize") is False

    def test_1_tonne_below_threshold_flagged(self):
        capesize_capacity = 180_000.0
        threshold = PARCEL_FIT_FRACTION * capesize_capacity
        assert _rule4_parcel_fit(threshold - 1.0, "Capesize") is True

    def test_supramax_full_load_not_flagged(self):
        assert _rule4_parcel_fit(55_000.0, "Supramax/Ultramax") is False

    def test_unknown_vessel_class_does_not_raise(self):
        """Unknown vessel class → uses Capesize fallback (180k) — should not crash."""
        result = _rule4_parcel_fit(5_000.0, "UnknownVesselClass")
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# Rule 5: Handling rate — unit tests
# ---------------------------------------------------------------------------

class TestRule5HandlingRate:
    def test_standard_calculation(self):
        """80,000 tonnes at 40,000 t/day → 2.0 days."""
        assert _rule5_handling_rate(80_000.0, 40_000.0) == pytest.approx(2.0)

    def test_zero_handling_rate_returns_zero(self):
        """Guard against division by zero."""
        assert _rule5_handling_rate(80_000.0, 0.0) == 0.0

    def test_proportional_to_quantity(self):
        d1 = _rule5_handling_rate(50_000.0, 40_000.0)
        d2 = _rule5_handling_rate(100_000.0, 40_000.0)
        assert d2 == pytest.approx(d1 * 2.0)


# ---------------------------------------------------------------------------
# Rule 6: Tidal window — unit tests
# ---------------------------------------------------------------------------

class TestRule6TidalWindow:
    def test_non_tidal_port_returns_none(self):
        assert _rule6_tidal_window("Gangavaram", is_tidal_dependent=False) is None

    def test_tidal_port_returns_note_string(self):
        note = _rule6_tidal_window("Haldia", is_tidal_dependent=True)
        assert note is not None
        assert "tide-dependent" in note.lower() or "tidal" in note.lower()
        assert "Haldia" in note

    def test_tidal_note_mentions_decision_engine(self):
        """Note must guide the Decision Engine's τ selection (DOC2 §8 Rule 6)."""
        note = _rule6_tidal_window("Paradip", is_tidal_dependent=True)
        assert note is not None
        # Must reference timing/τ guidance, not just a display string
        assert any(word in note.lower() for word in ["timing", "arrival", "τ", "window", "decision"])


# ---------------------------------------------------------------------------
# Rule 7: Lightening — unit tests
#   Done When criteria: both branches (eligible port / none available)
# ---------------------------------------------------------------------------

class TestRule7Lightening:
    def test_draft_ok_no_lightening_needed(self):
        """Draft ≤ port limit → no lightening required."""
        requires, port = _rule7_lightening(14.0, 14.0, "Paradip")
        assert requires is False
        assert port is None

    def test_draft_exactly_at_limit_no_lightening(self):
        """Boundary: draft == max → no lightening."""
        requires, port = _rule7_lightening(14.0, 14.0, "Paradip")
        assert requires is False

    def test_draft_1cm_over_with_eligible_lightening_port(self):
        """
        Lightening branch 1: draft exceeds limit AND Paradip has eligible
        lightening ports (Gangavaram, Dhamra) → feasible with lightening.
        """
        requires, port = _rule7_lightening(14.01, 14.0, "Paradip")
        assert requires is True
        assert port is not None
        assert port in ("Gangavaram", "Dhamra")

    def test_capesize_at_paradip_requires_lightening_eligible(self):
        """Capesize draft 18.2m > Paradip 14.0m → lightening at Gangavaram."""
        requires, port = _rule7_lightening(18.2, 14.0, "Paradip")
        assert requires is True
        assert port == "Gangavaram"  # first entry in LIGHTENING_PORTS["Paradip"]

    def test_no_eligible_lightening_port_returns_none(self):
        """
        Lightening branch 2: draft exceeds limit but Gangavaram has no
        lightening ports available → requires=True, port=None (infeasible).
        """
        requires, port = _rule7_lightening(20.0, 18.5, "Gangavaram")
        assert requires is True
        assert port is None

    def test_vizag_no_lightening_port(self):
        """Vizag is deep draft — but if exceeded, no lightening route exists."""
        requires, port = _rule7_lightening(22.0, 18.0, "Vizag")
        assert requires is True
        assert port is None  # Vizag has no lightening ports configured


# ---------------------------------------------------------------------------
# Integration: check_feasibility() — full 8-rule pipeline
# ---------------------------------------------------------------------------

class TestCheckFeasibility:
    """
    Integration tests for the full check_feasibility() pipeline.
    Uses parametrized port and vessel combinations to test each rule path.
    """

    def test_supramax_fits_paradip_cleanly(self):
        """
        Supramax (draft=10.8, loa=185, beam=32.3) vs Paradip (draft=14, loa=250, beam=43)
        → feasible, no lightening, no parcel-fit flag (for reasonable cargo quantity).
        """
        options = check_feasibility(
            cargo_quantity=50_000.0,
            discharge_ports=["Paradip"],
            port_constraints={"Paradip": PARADIP_PORT},
            vessel_specs={"Supramax/Ultramax": SUPRA_SPEC},
        )
        assert len(options) == 1
        opt = options[0]
        assert opt.is_feasible is True
        assert opt.requires_lightening is False
        assert opt.is_inefficient_fit is False
        assert opt.vessel_class == "Supramax/Ultramax"
        assert opt.port == "Paradip"
        assert opt.discharge_days == pytest.approx(50_000.0 / 40_000.0, rel=1e-3)

    def test_capesize_fails_paradip_loa(self):
        """
        Capesize (LOA=295m) vs Paradip (max_loa=250m)
        → LOA hard-blocks before lightening is even considered.
        Infeasible due to LOA, not draft.
        (Real constraint: Paradip's berths are too short for Capesize.)
        """
        options = check_feasibility(
            cargo_quantity=150_000.0,
            discharge_ports=["Paradip"],
            port_constraints={"Paradip": PARADIP_PORT},
            vessel_specs={"Capesize": CAPESIZE_SPEC},
        )
        assert len(options) == 1
        opt = options[0]
        assert opt.is_feasible is False
        assert "LOA" in opt.infeasible_reason

    def test_panamax_fails_paradip_draft_boundary(self):
        """
        Panamax (draft=14.2m) vs Paradip (max_draft=14.0m)
        → 14.2 > 14.0 → needs lightening → eligible ports exist → feasible with lightening.
        """
        options = check_feasibility(
            cargo_quantity=75_000.0,
            discharge_ports=["Paradip"],
            port_constraints={"Paradip": PARADIP_PORT},
            vessel_specs={"Panamax/Kamsarmax": PANAMAX_SPEC},
        )
        opt = options[0]
        assert opt.is_feasible is True
        assert opt.requires_lightening is True

    def test_capesize_passes_gangavaram(self):
        """
        Capesize (draft=18.2m, loa=295, beam=47) vs Gangavaram (draft=18.5, loa=300, beam=50)
        → all rules pass cleanly (no lightening needed).
        """
        options = check_feasibility(
            cargo_quantity=150_000.0,
            discharge_ports=["Gangavaram"],
            port_constraints={"Gangavaram": GANGAVARAM_PORT},
            vessel_specs={"Capesize": CAPESIZE_SPEC},
        )
        assert len(options) == 1
        opt = options[0]
        assert opt.is_feasible is True
        assert opt.requires_lightening is False

    def test_draft_exactly_at_limit_passes(self):
        """
        Done When boundary: vessel draft exactly equals port max → passes Rule 1.
        """
        exact_spec = {"draft_m": 14.0, "loa_m": 200.0, "beam_m": 38.0}
        options = check_feasibility(
            cargo_quantity=60_000.0,
            discharge_ports=["Paradip"],
            port_constraints={"Paradip": PARADIP_PORT},
            vessel_specs={"TestVessel": exact_spec},
        )
        assert options[0].is_feasible is True
        assert options[0].requires_lightening is False

    def test_draft_1cm_over_limit_triggers_lightening(self):
        """
        Done When boundary: 14.01m > 14.0m → lightening required.
        Paradip has eligible lightening ports → feasible with lightening.
        """
        over_spec = {"draft_m": 14.01, "loa_m": 200.0, "beam_m": 38.0}
        options = check_feasibility(
            cargo_quantity=60_000.0,
            discharge_ports=["Paradip"],
            port_constraints={"Paradip": PARADIP_PORT},
            vessel_specs={"TestVessel": over_spec},
        )
        assert options[0].is_feasible is True
        assert options[0].requires_lightening is True
        assert options[0].lightening_port is not None

    def test_infeasible_loa_excluded(self):
        """A vessel with LOA exceeding port limit is marked infeasible."""
        huge_spec = {"draft_m": 10.0, "loa_m": 400.0, "beam_m": 38.0}   # LOA way over
        options = check_feasibility(
            cargo_quantity=60_000.0,
            discharge_ports=["Paradip"],
            port_constraints={"Paradip": PARADIP_PORT},
            vessel_specs={"HugeVessel": huge_spec},
        )
        assert options[0].is_feasible is False
        assert "LOA" in options[0].infeasible_reason

    def test_infeasible_beam_excluded(self):
        """Beam exceeds port limit → infeasible."""
        wide_spec = {"draft_m": 10.0, "loa_m": 200.0, "beam_m": 55.0}  # beam over 43
        options = check_feasibility(
            cargo_quantity=60_000.0,
            discharge_ports=["Paradip"],
            port_constraints={"Paradip": PARADIP_PORT},
            vessel_specs={"WideVessel": wide_spec},
        )
        assert options[0].is_feasible is False
        assert "Beam" in options[0].infeasible_reason

    def test_infeasible_no_lightening_port(self):
        """
        Done When lightening branch 2: vessel draft exceeds port limit AND
        no lightening port available on route → infeasible.
        """
        deep_spec = {"draft_m": 25.0, "loa_m": 200.0, "beam_m": 38.0}
        options = check_feasibility(
            cargo_quantity=60_000.0,
            discharge_ports=["Gangavaram"],   # Gangavaram has no lightening ports
            port_constraints={"Gangavaram": GANGAVARAM_PORT},
            vessel_specs={"DeepVessel": deep_spec},
        )
        assert options[0].is_feasible is False
        assert "lightening" in options[0].infeasible_reason.lower()

    def test_parcel_fit_flag_does_not_block(self):
        """Rule 4 is SOFT — a small cargo on a large vessel is feasible but flagged."""
        options = check_feasibility(
            cargo_quantity=10_000.0,   # tiny parcel on Capesize
            discharge_ports=["Gangavaram"],
            port_constraints={"Gangavaram": GANGAVARAM_PORT},
            vessel_specs={"Capesize": CAPESIZE_SPEC},
        )
        opt = options[0]
        assert opt.is_feasible is True
        assert opt.is_inefficient_fit is True

    def test_tidal_port_produces_note(self):
        """Rule 6: tidal port → tidal_window_note is populated (not None)."""
        options = check_feasibility(
            cargo_quantity=50_000.0,
            discharge_ports=["TidalPort"],
            port_constraints={"TidalPort": TIDAL_PORT},
            vessel_specs={"Supramax/Ultramax": SUPRA_SPEC},
        )
        opt = options[0]
        assert opt.is_feasible is True
        assert opt.tidal_window_note is not None
        assert "tide" in opt.tidal_window_note.lower() or "tidal" in opt.tidal_window_note.lower()

    def test_non_tidal_port_has_no_note(self):
        """Rule 6: non-tidal port → tidal_window_note is None."""
        options = check_feasibility(
            cargo_quantity=50_000.0,
            discharge_ports=["Gangavaram"],
            port_constraints={"Gangavaram": GANGAVARAM_PORT},
            vessel_specs={"Supramax/Ultramax": SUPRA_SPEC},
        )
        assert options[0].tidal_window_note is None

    def test_rule8_vessel_size_ordering(self):
        """
        Rule 8: Larger vessel classes proposed first within each port.
        Capesize (rank 1) must appear before Panamax (rank 2) before Supramax (rank 3).
        """
        options = check_feasibility(
            cargo_quantity=150_000.0,
            discharge_ports=["Gangavaram"],
            port_constraints={"Gangavaram": GANGAVARAM_PORT},
            vessel_specs=ALL_VESSEL_SPECS,
        )
        classes = [o.vessel_class for o in options]
        assert classes.index("Capesize") < classes.index("Panamax/Kamsarmax")
        assert classes.index("Panamax/Kamsarmax") < classes.index("Supramax/Ultramax")

    def test_multi_port_returns_options_for_each(self):
        """Options are produced for all requested discharge ports."""
        options = check_feasibility(
            cargo_quantity=50_000.0,
            discharge_ports=["Paradip", "Gangavaram"],
            port_constraints={"Paradip": PARADIP_PORT, "Gangavaram": GANGAVARAM_PORT},
            vessel_specs={"Supramax/Ultramax": SUPRA_SPEC},
        )
        ports_in_output = {o.port for o in options}
        assert "Paradip" in ports_in_output
        assert "Gangavaram" in ports_in_output

    def test_unknown_port_skipped_gracefully(self):
        """Missing port in port_constraints → skipped with a warning, not a crash."""
        options = check_feasibility(
            cargo_quantity=50_000.0,
            discharge_ports=["UnknownPort"],
            port_constraints={},  # empty — port not found
            vessel_specs={"Supramax/Ultramax": SUPRA_SPEC},
        )
        assert options == []

    def test_empty_vessel_specs_returns_empty(self):
        """No vessel specs → no options."""
        options = check_feasibility(
            cargo_quantity=50_000.0,
            discharge_ports=["Paradip"],
            port_constraints={"Paradip": PARADIP_PORT},
            vessel_specs={},
        )
        assert options == []

    def test_discharge_days_in_feasible_option(self):
        """Rule 5: discharge_days correctly reflects cargo_quantity / handling_rate."""
        options = check_feasibility(
            cargo_quantity=80_000.0,
            discharge_ports=["Paradip"],
            port_constraints={"Paradip": PARADIP_PORT},  # handling_rate=40_000
            vessel_specs={"Supramax/Ultramax": SUPRA_SPEC},
        )
        opt = options[0]
        assert opt.is_feasible is True
        assert opt.discharge_days == pytest.approx(80_000.0 / 40_000.0, rel=1e-3)

    def test_all_three_vessel_classes_at_paradip(self):
        """
        Full three-class test at Paradip:
        - Supramax: draft 10.8 < 14.0, LOA 185 < 250, beam 32.3 < 43 → feasible, no lightening
        - Panamax:  draft 14.2 > 14.0, LOA 229 < 250, beam 36.3 < 43 → feasible with lightening
        - Capesize: LOA 295 > 250 → infeasible (LOA hard-block, before draft even checked)
        """
        options = check_feasibility(
            cargo_quantity=80_000.0,
            discharge_ports=["Paradip"],
            port_constraints={"Paradip": PARADIP_PORT},
            vessel_specs=ALL_VESSEL_SPECS,
        )
        by_class = {o.vessel_class: o for o in options}

        supra = by_class["Supramax/Ultramax"]
        assert supra.is_feasible is True
        assert supra.requires_lightening is False

        panamax = by_class["Panamax/Kamsarmax"]
        assert panamax.is_feasible is True
        assert panamax.requires_lightening is True
        assert panamax.lightening_port is not None

        cape = by_class["Capesize"]
        assert cape.is_feasible is False
        assert "LOA" in cape.infeasible_reason

    def test_tidal_flag_string_parsing(self):
        """tidal_dependent='true'/'false' strings (as stored from CSV) are parsed correctly."""
        port_true  = dict(PARADIP_PORT, tidal_dependent="true")
        port_false = dict(PARADIP_PORT, tidal_dependent="false")
        port_bool  = dict(PARADIP_PORT, tidal_dependent=True)

        for port_data, expected_note in [(port_true, True), (port_false, False), (port_bool, True)]:
            opts = check_feasibility(
                cargo_quantity=50_000.0,
                discharge_ports=["P"],
                port_constraints={"P": port_data},
                vessel_specs={"Supramax/Ultramax": SUPRA_SPEC},
            )
            if expected_note:
                assert opts[0].tidal_window_note is not None
            else:
                assert opts[0].tidal_window_note is None
