# config/constants.py
# DOC3 §2 — all constants verbatim.
# DO NOT read these for runtime validation — they are DEV-FIXTURE DEFAULTS ONLY.
# Live validation uses repository.get_valid_origins() / get_valid_dest_ports() /
# get_valid_vessel_classes() (DOC2 Addendum v3 §A1).

# ---------------------------------------------------------------------------
# Decision scope — DEV FIXTURE DEFAULTS (DOC 2 Addendum v3 §A1)
# Origins/ports/vessel classes are queried live from the warehouse; constants
# below seed a local dev warehouse from data/raw/*.csv when no warehouse exists.
# ---------------------------------------------------------------------------
DEV_FIXTURE_ORIGINS = [
    "Australia (Hay Point)",
    "Indonesia (East Kalimantan)",
    "South Africa (Richards Bay)",
]
DEV_FIXTURE_DEST_PORTS = [
    "Paradip",
    "Gangavaram",
    "Dhamra",
    # Vizag added once its port_constraints row exists — no constants change needed
]
DEV_FIXTURE_VESSEL_CLASSES = [
    "Supramax/Ultramax",
    "Panamax/Kamsarmax",
    "Capesize",
]

# ---------------------------------------------------------------------------
# Forecasting (DOC 2 §7 / §18.2)
# ---------------------------------------------------------------------------
CONDITIONS_MONITOR_LOWER_PCTL = 2.5
CONDITIONS_MONITOR_UPPER_PCTL = 97.5
MIN_OBSERVATIONS_FOR_XGBOOST = 80    # PROVISIONAL — Lowered from 500 → 80 (2026-08-29).
                                      # Rationale: the real drycargo_5tc_c5 series has 164
                                      # obs; 80 keeps a ≥50-obs min-train buffer before
                                      # the first walk-forward fold and lets XGBoost
                                      # compete on ARIMA-scale datasets.
                                      # Review after 6 months of real retrain cycles:
                                      # if enriched XGBoost consistently loses to ARIMA
                                      # at < ~120 obs, raise this threshold back to 120.
                                      # Below threshold: ARIMA/naive only (gate unchanged:
                                      # must beat naive by ≥5% walk-forward MAE).


FORECAST_HORIZONS_DAYS = [7, 14, 30]
RETRAIN_SCHEDULE_CRON = "0 3 * * 1"  # weekly, Monday 03:00
# ConditionsMonitor freshness thresholds for live market spike detection
BDI_FRESHNESS_THRESHOLD_DAYS = 3      # BDI data older than this → staleness alert
BUNKER_STALENESS_ALERT_HOURS = 48     # Bunker price older than this → staleness alert

# Real exogenous sources now available (DOC 2 Addendum v3 §A2) — feed into
# feature construction, not decision-scope validation.
EXOGENOUS_FEATURE_SOURCES = [
    "brent",
    "wti",
    "iron_ore",
    "bdry",
    "gscpi",
    "bunker_vlsfo",
    "bunker_mgo",
]

# ---------------------------------------------------------------------------
# Decision Engine — MILP (DOC 2 §11)
# ---------------------------------------------------------------------------
MILP_SOLVE_TIMEOUT_SECONDS = 60.0
MILP_SOLVER = "CBC"   # swap to "CP-SAT" behind the same decision.solve() interface if needed
HYBRID_FALLBACK_VOYAGE_COUNTS = [1, 2, 3]          # used only if the MILP solve times out/fails
HYBRID_FALLBACK_COMMITMENT_MODES = ["all-spot", "all-locked", "hybrid"]
# Scenario band fractions — "bull" = optimistic edge, "bear" = pessimistic edge
# (renamed from OPTIMISTIC/PESSIMISTIC to match research pipeline bear/base/bull naming)
SCENARIO_BULL_BAND_FRACTION = 0.5     # how far toward the favorable CI edge "Bull" shifts
SCENARIO_BEAR_BAND_FRACTION = 0.5     # symmetric, unfavorable edge
# Legacy aliases (kept for any tests still referencing the old names)
SCENARIO_OPTIMISTIC_BAND_FRACTION = SCENARIO_BULL_BAND_FRACTION
SCENARIO_PESSIMISTIC_BAND_FRACTION = SCENARIO_BEAR_BAND_FRACTION

# commitment_benchmark default — MUST read the honesty label in ProvenanceBadge
DEFAULT_COMMITMENT_BENCHMARK_PCT = 10.0    # UNVERIFIED placeholder — see DOC 2 §11.8/§20

# Step 51V Sail vs Kill portfolio risk controls (transplanted from research pipeline)
# MILP_RISK_RATIO: worst-case portfolio incremental must be ≥ this fraction of base-case incremental.
# Mirrors step51v RISK_RATIO=0.60 — protects SAIL from sailing contracts that destroy value in bear market.
MILP_RISK_RATIO: float = 0.60
# MILP_KILL_BENCHMARK_PCT: fraction of forecasted spot rate used as kill-value baseline.
# 1.0 = SAIL's walk-away value equals full spot market rate for that cargo × qty.
MILP_KILL_BENCHMARK_PCT: float = 1.0

# ---------------------------------------------------------------------------
# Cost terms (DOC 2 §10's C_s components) — see FEATURE: Cost Terms Module
# Bunker consumption is now REAL physics (distance × laden/ballast rate),
# sourced from the route-physics warehouse table — no longer a flat assumed
# constant. See that FEATURE section for the replacement function signature.
# ---------------------------------------------------------------------------
PORT_HANDLING_DAY_RATE_USD = 15000.0    # UNVERIFIED placeholder — tagged "assumed", per-day port call cost
WAITING_COST_PER_DAY_USD = 12000.0     # UNVERIFIED placeholder — tagged "assumed", idle-day cost (DOC2 §10 "waiting" term)
TAX_RATE_PCT = 5.0                      # UNVERIFIED placeholder — tagged "assumed", per DOC2 §12's mock-data policy

# ---------------------------------------------------------------------------
# Scope Catalog cache (DOC 2 Addendum v3 §A1)
# ---------------------------------------------------------------------------
SCOPE_CATALOG_CACHE_TTL_SECONDS = 300   # scope doesn't change every request

# ---------------------------------------------------------------------------
# AIS
# ---------------------------------------------------------------------------
AIS_CONGESTION_CACHE_TTL_SECONDS = 60
AIS_BOUNDING_BOXES: dict = {
    "Paradip": {},     # populated per verified port — grows automatically as ports are added
    "Gangavaram": {},
    "Dhamra": {},
}  # grows automatically as ports are added, per §A1

# ---------------------------------------------------------------------------
# OilPriceAPI live bunker feed (confirmed in handoff Step 50A)
# See FEATURE: Data Ingestion Layer's bunker_ingest.py for the fallback path
# ---------------------------------------------------------------------------
OILPRICEAPI_VLSFO_URL = "https://api.oilpriceapi.com/v1/prices/latest?by_code=VLSFO_USD"

# ---------------------------------------------------------------------------
# Repositioning physics (DOC 2 §11.2, v3 Final, NEW)
# Default speeds used when a tracked vessel's own AIS-reported speed isn't available
# ---------------------------------------------------------------------------
DEFAULT_BALLAST_SPEED_KNOTS = 12.0   # step50b/step51u: all 358 production routes use 12.0 kn
DEFAULT_LADEN_SPEED_KNOTS = 12.0
# Safety buffer added to raw repositioning hours before computing earliest_feasible_departure_day.
# Mirrors step51a REPOSITION_BUFFER_HOURS = 6.0 from the handoff research pipeline.
# ceil((reposition_hours + REPOSITION_BUFFER_HOURS) / 24) → earliest_day in _compute_tau().
REPOSITION_BUFFER_HOURS: float = 6.0
