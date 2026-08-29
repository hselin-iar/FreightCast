# DOC 3 (v3, Final) — Module & Coding Architecture
### Intelligent Freight Forecasting & Chartering — Full Build (per confirmed DOC 2, v3 Final)
Bridges DOC 2 (v3, Final) — system architecture — MILP-based Decision Engine enriched
with real AIS vessel-repositioning physics, full data pipeline, React frontend — into
actual code structure. Supersedes the original DOC 3 and the prior v2 pass; this
revision folds in DOC2_v3_Final.md's newest handoff features (real AIS vessel tracking,
departure/repositioning physics, the live OilPriceAPI bunker feed, and the explicit
fleet-portfolio-vs-single-request scope boundary) into the module/coding architecture.

This document assumes the **DOC 3 Migration Delta** as context: modules marked KEEP or
ADAPT there are treated as already-solved building blocks below, not re-derived from
DOC 2's prose. Where a function signature below matches the old build exactly, that's
intentional — the goal is minimum churn on what already works. One correction to the
Migration Delta: its pricing-formula classification didn't survive contact with the
MILP's linearity requirement — see §0.1 and `FEATURE: Cost Terms Module` below.

---

## INDEX — read this, then jump to ONE section below. Do not read this file top to bottom.

| Section | What's there |
|---|---|
| `## 0. Decisions locked before writing this doc` | Stack/scope decisions for the full build |
| `## 0.1 Carried over unchanged from the prior build` | What NOT to regenerate — see Migration Delta |
| `## 1. Repo & module layout` | Full folder tree |
| `## 2. Config` | `constants.py` contents |
| `### FEATURE: Data Ingestion Layer` | → Build Step 1 |
| `### FEATURE: AIS Listener & Congestion Module` | → Build Step 2 |
| `### FEATURE: Data Warehouse` | → Build Step 3 |
| `### FEATURE: Forecasting Engine` | → Build Step 4 |
| `### FEATURE: Constraint / Feasibility Engine` | → Build Step 5 (carried over) |
| `### FEATURE: Scenario Generator` | → Build Step 6 |
| `### FEATURE: Cost Terms Module` | → Build Step 7 (reinvented — read before Decision Engine) |
| `### FEATURE: Decision Engine (MILP Optimizer)` | → Build Step 8 |
| `### FEATURE: Provenance & Explainability Layer` | → Build Step 9 |
| `### FEATURE: Operational Evidence Layer` | → Build Step 9.5 (new, DOC 2 Addendum v3 §A3) |
| `### FEATURE: API Layer` | → Build Step 10 |
| `### FEATURE: Dashboard (React + Recharts)` | → Build Step 11 |
| `### FEATURE: Chatbot` | → Build Step 12 |
| `## 4. Cross-cutting: Deployment & environment` | → Build Step 13 |
| `## 5. Assumptions flagged in this document` | Only open if a step's behavior seems to depend on an unstated assumption |

---

## 0. Decisions locked before writing this doc

| Decision | Chosen | Why |
|---|---|---|
| Persistence | **PostgreSQL**, TimescaleDB extension added once live ingestion runs across many routes | Matches DOC 2 §4 exactly. Replaces the prior build's in-memory CSV approach — data now arrives continuously (AIS) and on a schedule (batch), so it needs a real backing store. |
| Ingestion | **Batch ETL on a lightweight scheduler** (cron or APScheduler) for daily/monthly sources + a **persistent WebSocket process** for AIS | DOC 2 §4/§5 — two different cadences need two different runtime shapes; forcing AIS into a request/response model would lose live updates. |
| Forecasting retrain | **Weekly scheduled retrain, decoupled from the request path** | DOC 2 §4's core principle: "forecasting is decoupled from the user's request." The Decision Engine only ever reads a stored `forecast_object`. |
| Decision Engine solver | **PuLP + CBC**, primary. **OR-Tools CP-SAT** documented as a drop-in alternative behind the same interface if CBC's solve time is unstable at demo scale | DOC 2 §11 lists both; committing to one now (CBC) keeps the interface concrete, but `decision.py`'s solver call is isolated so swapping is a one-function change, not a rewrite. |
| Dashboard stack | **React + Recharts** (Vite) | DOC 2 §16.1, explicit. Supersedes the prior build's Streamlit decision — see Migration Delta §1 item 4. |
| Testing depth | **Minimal, targeted**, but the flagged set changes: **cost formula, constraint rules, MILP formulation/objective** — the three places a silent bug would misinform a real chartering decision. `entry_timing`'s old test file is retired; its scenarios move into the MILP test suite (timing is now a solver constraint, not a standalone function). | Same principle as the prior build, re-scoped to where the risk actually lives now. |
| Chatbot LLM | **Anthropic Claude API, tool-calling**, wrapping `/recommendation` — unchanged from the prior build | DOC 2 §16.2 confirms the same "thin wrapper, no second code path" design. |
| Provenance tagging | **A shared `Provenance` type used by every engine output**, not a dashboard-only concept | DOC 2 §12 makes provenance tags a baseline requirement on every number shown, not a nice-to-have — so it has to originate where the number originates (forecasting, cost terms, congestion), not be bolted on in the frontend. `[ASSUMPTION: implemented as a lightweight enum + optional note field attached to every relevant pydantic model, not a separate service.]` |
| Cost-term module | **Reinvented, not carried over** — see §0.1 and the dedicated FEATURE section below | The prior build's `_price_spot_voyage`/`_price_locked_voyage` were written for a single pre-resolved `TimingDecision` and only covered freight+bunker+port+lightening. DOC 2 §10's `C_s` explicitly requires tax and waiting terms too, and — because MILP objectives must be linear — cost has to be precomputable as a coefficient for *every* candidate `(voyage, vessel, port, τ, mode, scenario)` combination before the solve runs, not computed after a timing decision is already made. That's a shape change, not a formula tweak. |
| Deployment | **Render** (Web Service + Background Worker + Cron Job + managed Postgres, one project, one `render.yaml` blueprint) for the backend trio; **Vercel** for the React static build | See §4 for the full reasoning — chosen specifically for being the least new tooling a vibecoder has to learn mid-project while still giving each of the three backend processes (API, AIS listener, scheduler) its own correctly-typed Render service. |
| Decision scope | **Data-driven, not hardcoded.** Origins/ports/vessel classes are whatever's verified in the warehouse, not fixed constants. See DOC 2 Addendum v3 §A1. | The original 3×3×3 scope was an MVP-era artifact. SAIL needs this to scale to every route/port/vessel it cares about without a code change per addition — growth happens through the existing ingestion + human-verification pipeline, not a constants.py edit. |
| Cost physics | **Real distance-based bunker consumption** (laden/ballast, actual nautical distance) replaces the flat assumed per-day placeholder | Real voyage-distance/physics data is now available (see DOC 2 Addendum v3 §A2) — no reason to keep an assumed constant where a measured one is possible. |
| Operational Evidence | **New advisory overlay**, scored post-solve from real ShipOffer broker data, explicitly NOT wired into the MILP objective/constraints | DOC 2 Addendum v3 §A3 — keeps the Decision Engine deterministic and auditable; market-alignment is context for a human, not an optimization input. |
| Repositioning-aware τ | **Real vessel-position grounding (NEW)**, via MyShipTracking AIS ingestion (handoff Steps 48–49G/51A) — decision.py's τ generation computes an actual earliest-feasible departure date per vessel class/route when position data exists, falling back to calendar-only candidates otherwise | DOC 2 §11.2 (v3 Final) — a genuine enrichment of the existing time-representation logic, not a new decision-variable dimension. |
| Scope boundary — single-request only | **Explicit, single-request `<4s` scope.** `/recommendation` solves for one `cargo_request` at a time; the handoff's Step 51V batch fleet-portfolio optimizer (16 contracts × 36 ships, 10,890 non-overlap conflict edges, ~118s solve) stays an offline batch pipeline, never folded into the interactive API path | DOC 2 §13/§14 (v3 Final, mirrors DOC2 §11) — different latency profile, different decision-maker, would blur the "one clear number for one clear request" honesty story. See `FEATURE: Decision Engine`'s deferral note. |

---

## 0.1 Carried over unchanged from the prior build

Per the Migration Delta, these are correct as-is and should be imported/extended, not
regenerated from DOC 2's prose:

- **`engine/constraint.py`** — Rules 1–8, the `FeasibleOption` shape, and its full test file. DOC 2 §8 confirms the same 8 rules. Only change: add provenance/optional fields as needed, don't touch the rule logic.
- **`engine/congestion.py`'s `CongestionSnapshot` shape and fallback behavior** — extended to read from the warehouse (continuous AIS writes) instead of calling `aisstream.io` directly per-request, but the shape and the "never let AIS take down `/recommendation`" behavior are unchanged.
- **The chatbot's single-tool, no-second-code-path principle** — unchanged design, new implementation surface (React instead of Streamlit).
- **API endpoint names** — `/recommendation`, `/forecast`, `/compatible-vessels`, `/scenario`, `/port-status`, `/health` — all unchanged (DOC 2 §15 confirms this explicitly). Only the request/response schemas grow.

**NOT carried over, correcting the Migration Delta's earlier read:** the prior build's
`_price_spot_voyage`/`_price_locked_voyage` cost formulas. On closer inspection against
DOC 2 §10, these need to be reinvented — see `### FEATURE: Cost Terms Module` below for
why and what replaces them. The Migration Delta's other classifications all still hold;
this is the one place where "looks reusable" didn't survive contact with the MILP's
linearity requirement.

---

## 1. Repo & module layout

```
/freight-system/
├── backend/
│   ├── ingestion/
│   │   ├── batch/
│   │   │   ├── bdi_ingest.py            # daily — BDI, investing.com CSV / OilPriceAPI
│   │   │   ├── bunker_ingest.py         # daily — OilPriceAPI maritime endpoint, GET
│   │   │   │                            #   https://api.oilpriceapi.com/v1/prices/latest?by_code=VLSFO_USD
│   │   │   │                            #   (production endpoint confirmed working, handoff Step 50A),
│   │   │   │                            #   falls back to data/raw/bunker_singapore.csv
│   │   │   ├── port_constraint_ingest.py# monthly — pdfplumber/camelot + manual verification queue
│   │   │   ├── fleet_demand_ingest.py   # monthly/quarterly — orderbook, coal/steel figures
│   │   │   ├── rate_5tc_ingest.py       # NEW — tiered/audited Capesize 5TC dataset, DOC2 Addendum v3 §A2
│   │   │   ├── macro_features_ingest.py # NEW — Brent/WTI/Iron Ore/BDRY/GSCPI, §A2
│   │   │   ├── operational_evidence_ingest.py  # NEW — ShipOffer broker data, §A3
│   │   │   └── vessel_position_ingest.py # NEW — candidate bulk-carrier AIS snapshots (IMO, name, lat/lon,
│   │   │                                 #   speed, draft, verified DWT) via MyShipTracking, handoff Step 49G;
│   │   │                                 #   may also live inside ais_listener.py's batch/backfill path — see
│   │   │                                 #   FEATURE: AIS Listener & Congestion Module below
│   │   ├── ais_listener.py              # persistent WebSocket process, DUAL CONCERN (DOC2 §4 v3 Final):
│   │   │                                 #   (a) port congestion → port_congestion_snapshot (unchanged)
│   │   │                                 #   (b) real vessel fleet tracking (Queensland, Richards Bay,
│   │   │                                 #       Kalimantan loading regions) → vessel_position_snapshot
│   │   ├── validation.py                # schema/type, freshness, gap-fill, plausibility checks (DOC2 §18.1)
│   │   └── scheduler.py                 # cron/APScheduler entrypoint — triggers batch jobs + weekly retrain
│   ├── warehouse/
│   │   ├── models.py                    # SQLAlchemy: RateHistory, PortConstraint, VesselSpec, ForecastObject,
│   │   │                                #   CongestionSnapshot, ExogenousFeature, RoutePhysics, OperationalEvidence,
│   │   │                                #   VesselPositionSnapshot (NEW — real AIS-tracked candidate vessels)
│   │   ├── db.py                        # engine/session setup, Postgres (+ TimescaleDB)
│   │   ├── migrations/                  # alembic
│   │   └── repository.py                # typed query functions — the ONLY place raw SQL/ORM queries live
│   ├── config/
│   │   └── constants.py
│   ├── engine/
│   │   ├── forecasting.py               # scheduled training/eval, conditions monitor, damped trend
│   │   ├── constraint.py                # Rules 1–8 — CARRIED OVER, see §0.1
│   │   ├── cost_terms.py                # freight/bunker/port/tax/waiting/lightening coefficients — REINVENTED, see FEATURE below
│   │   ├── scenario.py                  # Scenario Generator: Base/Optimistic/Pessimistic paths
│   │   ├── decision.py                  # MILP Optimizer: variables, constraints, objective, solve, hybrid fallback
│   │   ├── provenance.py                # measured/modeled/assumed tagging helpers, shared across engines
│   │   ├── evidence.py                  # Operational Evidence Layer — NEW, DOC 2 Addendum v3 §A3
│   │   └── congestion.py                # reads latest snapshot from warehouse — CARRIED OVER shape
│   ├── api/
│   │   ├── main.py                      # FastAPI app, CORS (now load-bearing — separate frontend origin)
│   │   ├── routes/
│   │   │   ├── recommendation.py
│   │   │   ├── forecast.py
│   │   │   ├── compatible_vessels.py
│   │   │   ├── scenario.py
│   │   │   ├── port_status.py
│   │   │   ├── scope.py                 # NEW — GET /scope, DOC 2 Addendum v3 §A1
│   │   │   └── health.py                # now also reports warehouse connectivity + last retrain timestamp
│   │   └── schemas.py                   # request/response contracts — grows substantially, see §3
│   └── tests/
│       ├── test_constraint_rules.py     # CARRIED OVER, unmodified
│       ├── test_cost_terms.py           # NEW — replaces test_strategy_cost_formula.py, see FEATURE below
│       └── test_decision_engine_milp.py # NEW — replaces test_entry_timing.py
├── frontend/                             # React + Recharts (Vite + TypeScript)
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx                      # route/tab shell: Recommendation | Chatbot
│   │   ├── pages/
│   │   │   └── RecommendationPage.tsx
│   │   ├── components/
│   │   │   ├── StrategyTable.tsx
│   │   │   ├── ForecastChart.tsx        # trajectory + confidence band
│   │   │   ├── ScenarioFanChart.tsx     # Base/Opt/Pess overlay — DOC2 §16.3 item 2
│   │   │   ├── AISRouteMap.tsx          # DOC2 §16.3 item 3
│   │   │   ├── WhatIfSliders.tsx        # debounced live re-solve — DOC2 §16.3 item 1
│   │   │   ├── ProvenanceBadge.tsx      # measured / modeled / assumed
│   │   │   ├── SensitivityPanel.tsx     # tornado chart — DOC2 §16.3 baseline panel
│   │   │   ├── RobustnessReadout.tsx    # worst-case cost / regret
│   │   │   ├── WhyNotComparator.tsx     # DOC2 §16.3 item 4
│   │   │   └── ExecutiveBriefExport.tsx # DOC2 §16.3 item 5
│   │   ├── chat/
│   │   │   └── ChatPanel.tsx            # chat UI, tool-calling round trip, receives dashboard_update events
│   │   └── lib/
│   │       └── apiClient.ts             # every backend call goes through here, nowhere else
│   ├── package.json
│   └── vite.config.ts
├── requirements.txt
├── .env.example                          # DATABASE_URL, AISSTREAM_API_KEY, ANTHROPIC_API_KEY, VITE_API_BASE_URL
└── README.md
```

**Dependency rule (unchanged principle, DOC 2 §4):** `engine/` never imports from `api/`,
`ingestion/`, or `frontend/`. `engine/` reads only through `warehouse/repository.py` —
never raw SQL, never a direct AIS/HTTP call. `api/routes/` call `engine/` functions and
shape the response — no business logic in a route handler. `frontend/` never touches the
backend except through `apiClient.ts`.

---

## 2. Config — `config/constants.py`

```python
# Decision scope (DOC 2 Addendum v3 §A1) — NO LONGER a hardcoded allow-list.
# Origins/ports/vessel classes are queried live from the warehouse via
# repository.get_valid_origins() / get_valid_dest_ports() / get_valid_vessel_classes().
# The constants below are DEV-FIXTURE DEFAULTS ONLY — used to seed a local dev warehouse
# from data/raw/*.csv when no warehouse exists yet, never read directly for validation.
DEV_FIXTURE_ORIGINS = ["Australia (Hay Point)", "Indonesia (East Kalimantan)", "South Africa (Richards Bay)"]
DEV_FIXTURE_DEST_PORTS = ["Paradip", "Gangavaram", "Dhamra"]  # Vizag added once its port_constraints row exists — no constants change needed
DEV_FIXTURE_VESSEL_CLASSES = ["Supramax/Ultramax", "Panamax/Kamsarmax", "Capesize"]

# Forecasting (DOC 2 §7 / §18.2)
CONDITIONS_MONITOR_LOWER_PCTL = 2.5
CONDITIONS_MONITOR_UPPER_PCTL = 97.5
MIN_OBSERVATIONS_FOR_XGBOOST = 500  # below this: ARIMA/naive only, flagged on dashboard
FORECAST_HORIZONS_DAYS = [7, 14, 30]
RETRAIN_SCHEDULE_CRON = "0 3 * * 1"  # weekly, Monday 03:00
# Real exogenous sources now available (DOC 2 Addendum v3 §A2) — feed into feature
# construction, not decision-scope validation:
EXOGENOUS_FEATURE_SOURCES = ["brent", "wti", "iron_ore", "bdry", "gscpi", "bunker_vlsfo", "bunker_mgo"]

# Decision Engine — MILP (DOC 2 §11)
MILP_SOLVE_TIMEOUT_SECONDS = 4.0
MILP_SOLVER = "CBC"  # swap to "CP-SAT" behind the same decision.solve() interface if needed
HYBRID_FALLBACK_VOYAGE_COUNTS = [1, 2, 3]     # used only if the MILP solve times out/fails
HYBRID_FALLBACK_COMMITMENT_MODES = ["all-spot", "all-locked", "hybrid"]
SCENARIO_OPTIMISTIC_BAND_FRACTION = 0.5   # how far toward the favorable CI edge "Optimistic" shifts
SCENARIO_PESSIMISTIC_BAND_FRACTION = 0.5  # symmetric, unfavorable edge

# commitment_benchmark default — MUST read the honesty label in ProvenanceBadge
DEFAULT_COMMITMENT_BENCHMARK_PCT = 10.0  # UNVERIFIED placeholder — see DOC 2 §11.8/§20

# Cost terms (DOC 2 §10's C_s components) — see FEATURE: Cost Terms Module
# Bunker consumption is now REAL physics (distance x laden/ballast rate), sourced from
# the route-physics warehouse table — no longer a flat assumed constant. See that
# FEATURE section for the replacement function signature.
PORT_HANDLING_DAY_RATE_USD = 15000.0     # UNVERIFIED placeholder — tagged "assumed", per-day port call cost
WAITING_COST_PER_DAY_USD = 12000.0       # UNVERIFIED placeholder — tagged "assumed", idle-day cost (DOC2 §10 "waiting" term)
TAX_RATE_PCT = 5.0                        # UNVERIFIED placeholder — tagged "assumed", per DOC2 §12's mock-data policy

# Scope Catalog cache (DOC 2 Addendum v3 §A1) — scope doesn't change every request
SCOPE_CATALOG_CACHE_TTL_SECONDS = 300

# AIS
AIS_CONGESTION_CACHE_TTL_SECONDS = 60
AIS_BOUNDING_BOXES = {
    "Paradip": {...},
    "Gangavaram": {...},
    "Dhamra": {...},
}  # populated per verified port — grows automatically as ports are added, per §A1

# OilPriceAPI live bunker feed (confirmed in handoff Step 50A) — see FEATURE: Data
# Ingestion Layer's bunker_ingest.py for the fallback path
OILPRICEAPI_VLSFO_URL = "https://api.oilpriceapi.com/v1/prices/latest?by_code=VLSFO_USD"

# Repositioning physics (DOC 2 §11.2, v3 Final, NEW) — default speeds used when a
# tracked vessel's own AIS-reported speed isn't available
DEFAULT_BALLAST_SPEED_KNOTS = 12.5
DEFAULT_LADEN_SPEED_KNOTS = 12.0
```

---

## 3. Feature-by-feature module architecture

### FEATURE: Data Ingestion Layer

```
MODULE STRUCTURE:
  /backend/ingestion/
    ├── batch/bdi_ingest.py, bunker_ingest.py, port_constraint_ingest.py, fleet_demand_ingest.py,
    │          rate_5tc_ingest.py, macro_features_ingest.py, operational_evidence_ingest.py
    ├── validation.py
    └── scheduler.py

FUNCTION & CLASS DESIGN:
  Each batch/*.py module exposes exactly one entrypoint: run() -> IngestResult, called by
  scheduler.py on its own cadence (daily for BDI/bunker/5TC, monthly for constraints/fleet).
  run() does: fetch raw source -> validation.validate(raw, schema) -> repository.upsert(...).

  rate_5tc_ingest.py (NEW, DOC 2 Addendum v3 §A2):
    - Ingests the tiered/audited Capesize 5TC dataset (already NLP-extracted and verified
      offline — this module ingests the CLEAN output, it does not re-run extraction) as
      the primary RateHistory source, tagged provenance="measured".
    - Tier A/B distinction from the source data is preserved as a confidence field on the
      ingested row, not collapsed — a downstream consumer (forecasting.py) can choose to
      weight or filter by tier later without re-ingesting.

  macro_features_ingest.py (NEW, DOC 2 Addendum v3 §A2):
    - Ingests EXOGENOUS_FEATURE_SOURCES (Brent, WTI, Iron Ore, BDRY, GSCPI) into a
      dedicated exogenous_features table, keyed by (source, date) — kept separate from
      RateHistory since these aren't freight rates themselves, just model inputs.

  operational_evidence_ingest.py (NEW, DOC 2 Addendum v3 §A3):
    - Ingests ShipOffer broker fixture/position reports into an operational_evidence
      table. Feeds engine/evidence.py (see that FEATURE section) — this module only
      ingests and validates, it does not compute the confidence score itself.

  bunker_ingest.py (DOC 2 §5, v3 Final):
    - Production endpoint, confirmed working end-to-end in the handoff (Step 50A):
      GET https://api.oilpriceapi.com/v1/prices/latest?by_code=VLSFO_USD
      (see config/constants.py's OILPRICEAPI_VLSFO_URL).
    - Falls back to data/raw/bunker_singapore.csv if the live endpoint is unreachable —
      the ingested row is tagged provenance="assumed"/stale in that case rather than
      silently treated as a fresh measured price (same freshness-check pattern as §6.1).

  vessel_position_ingest.py (NEW, handoff Step 49G, DOC 2 §5/§11.2 v3 Final):
    - Ingests candidate bulk-carrier AIS position snapshots (IMO, vessel_name, latitude,
      longitude, speed_knots, draft, verified DWT) sourced via MyShipTracking, writing to
      warehouse.repository.upsert_vessel_position_snapshot(...) — see
      FEATURE: Data Warehouse's VesselPositionSnapshot model.
    - Enrichment only, not a scope change to the MILP's decision-variable granularity
      (DOC 2 §5, v3 Final) — this feeds the Decision Engine's repositioning-aware τ
      generation (§11.2), it never turns the optimizer into a per-IMO assignment problem.
    - May run as a batch/backfill job here, or be folded directly into ais_listener.py's
      continuous stream (see FEATURE: AIS Listener & Congestion Module) — either shape
      writes to the same VesselPositionSnapshot table through repository.py.

  validation.validate(raw_df, schema: IngestSchema) -> ValidatedBatch
    - Schema/type check: reject rows with wrong dtypes or missing required columns (DOC2 §18.1)
    - Freshness check: latest point > 2 days old on a daily feed -> flagged alert, not silently accepted
    - Gap-filling: weekend/holiday gaps in daily series forward-filled
    - Plausibility check: draft/LOA/beam within sane bounds before reaching port_constraint_table
    - Returns ValidatedBatch{rows: list, rejected: list, alerts: list} — nothing is silently dropped
      without a logged reason.

  port_constraint_ingest.py specifically:
    - Extraction via pdfplumber/camelot (source docs are structurally irregular, DOC2 §5)
    - Any NEW or CHANGED port constraint value is written to a `pending_verification` table,
      not directly to the active port_constraint_table — a human sign-off step flips it to
      active (DOC2 §18.1: "these numbers are safety-critical, not just statistically
      inconvenient if wrong"). This is a hard requirement, not a nice-to-have for MVP polish.
    - This is now also the system's port-scope growth mechanism (DOC 2 Addendum v3 §A1):
      adding a new port (e.g. Vizag, once its constraints are available — real or an
      explicitly-flagged placeholder) means adding a verified row here, nothing else.

INTERFACES & CONTRACTS:
  IngestResult = {source: str, rows_ingested: int, rows_rejected: int, alerts: list[str]}
  Downstream modules never see raw source data — only what's passed validation and,
  for port constraints, human sign-off.

ERROR HANDLING STRATEGY:
  A failed batch run logs and alerts (does not crash the scheduler process) — one bad
  day's BDI fetch must not take down bunker ingestion or the retrain schedule.
  Startup: on first boot, refuse to serve /recommendation until at least one successful
  ingest of each required source has completed (surfaced via /health).

EDGE CASES TO HANDLE:
  - Source temporarily unreachable -> retry with backoff, then alert if still failing after N tries
  - PDF extraction produces a value the plausibility check rejects -> logged, NOT silently
    substituted with a prior value; goes to pending_verification as a flagged anomaly
  - Port/vessel/origin name not yet present in the warehouse's verified scope (DOC 2
    Addendum v3 §A1) -> logged, held in pending_verification rather than silently
    dropped — this is now the NORMAL path for scope growth, not an error condition

PERFORMANCE CONSIDERATIONS:
  Batch jobs run on their own schedule, off the request path entirely — no latency budget
  to worry about here at this data scale (315 files / ~13.65MB total across the real
  dataset — trivial for a scheduled batch job regardless of source count).

TESTING PLAN:
  Unit: validation.py's four checks against known-good and known-bad fixture rows.
  Not one of the three flagged high-risk areas (a rejected/flagged row is a visible,
  logged outcome, not a silent wrong number) — manual spot-check before demo otherwise.
```

---

### FEATURE: AIS Listener & Congestion Module

```
STATUS: DUAL CONCERN (DOC 2 §4, v3 Final) — this module now has two responsibilities
  sharing one persistent connection, not one:
    (a) Port congestion — geofenced port bounding boxes -> CongestionSnapshot (unchanged)
    (b) Vessel fleet tracking — bulk-carrier positions in loading regions (Queensland,
        Richards Bay, Kalimantan) -> VesselPositionSnapshot / VesselSpec enrichment,
        grounding the Decision Engine's departure-repositioning physics (§11.2)

MODULE STRUCTURE:
  /backend/ingestion/ais_listener.py    # persistent process, not a route handler
  /backend/engine/congestion.py         # CARRIED OVER shape, read path only for concern (a)

FUNCTION & CLASS DESIGN:
  ais_listener.py runs as its own long-lived process (separate from the FastAPI app),
  subscribed to two distinct geofence/subscription targets over the same connection:
    connect() -> maintains a persistent WebSocket to aisstream.io / MyShipTracking,
      subscribed to (a) AIS_BOUNDING_BOXES for each in-scope port, AND (b) the loading
      regions (Queensland, Richards Bay, Kalimantan) where candidate bulk carriers are
      tracked.
    on_message(msg) -> routes by subscription target:
      - Port-congestion messages: updates an in-memory vessel-position map, and on each
        geofence-enter/exit event, computes {vessel_count, avg_wait_hours} for that port
        and writes it via warehouse.repository.write_congestion_snapshot(port, snapshot).
      - Vessel-fleet messages (NEW, handoff Step 49G): parses IMO, vessel_name,
        vessel_class, dwt, lat/lon, speed_knots, recorded_at and writes via
        warehouse.repository.upsert_vessel_position_snapshot(...) — see
        FEATURE: Data Warehouse's VesselPositionSnapshot model. This is the continuous-
        stream counterpart to vessel_position_ingest.py's batch/backfill path; both
        write through the same repository function.
    Reconnect logic: exponential backoff on disconnect, per DOC2 §19's "AIS feed can drop"
      risk — the listener must self-heal without a manual restart, for BOTH concerns.

  congestion.py (read path, called from API/engine):
    get_congestion_snapshot(port: str) -> CongestionSnapshot
      - Reads the latest row from warehouse for that port.
      - If the latest row is older than AIS_CONGESTION_CACHE_TTL_SECONDS * some staleness
        multiplier (listener presumed down), is_live is still True/False based on when it
        was written, but source_note explicitly says "stale — AIS feed may be down"
        rather than silently serving old numbers as current (DOC2 §19).
      - If no row exists at all for that port yet (cold start / feature flag path), falls
        back to a seeded placeholder — same CARRIED OVER behavior as before.

INTERFACES & CONTRACTS:
  CongestionSnapshot = {port, vessel_count, avg_wait_hours, is_live: bool, source_note: str}
  — unchanged shape from the prior build (Migration Delta §2). Every caller (entry-timing
  logic now inside decision.py, /port-status, dashboard) reads this exact shape.

  VesselPositionSnapshot — see FEATURE: Data Warehouse for the full ORM shape; consumed
  by decision.py's repositioning-aware τ generation (§11.2) and the dashboard's AIS route
  map (DOC 2 §16.3 item 3).

ERROR HANDLING STRATEGY:
  ais_listener.py failures never propagate to the request path — it's an independent
  process; if it's down, congestion.py's staleness check handles concern (a), and
  decision.py's graceful calendar-only τ fallback (§11.2) handles concern (b) — a
  coverage gap in either stream degrades gracefully, it never blocks a solve.

EDGE CASES TO HANDLE:
  - Listener process crashes -> supervised restart (systemd/Docker restart policy); both
    concerns resume from wherever their respective streams reconnect
  - Port requested that isn't in the warehouse's currently verified scope (DOC 2
    Addendum v3 §A1) -> ValueError, programming error not a business outcome (same
    principle as before — the set of valid ports just isn't a fixed constant anymore)
  - MyShipTracking coverage is partial or regional, or the vessel-position feed drops ->
    the last known position for a tracked vessel ages rather than silently vanishing
    (same gap-fill pattern as §18.1's other feeds); decision.py falls back to calendar-
    only τ candidates for that class/route, tagged `assumed`
  - Speed/position values outside physically sane bounds (AIS jitter/spoofing) ->
    rejected by validation.py's plausibility check (§18.1), not written to
    VesselPositionSnapshot

PERFORMANCE CONSIDERATIONS:
  Listener writes are async/fire-and-forget to the warehouse — never blocks on a slow DB
  write mid-stream, for either concern. Read path is a single indexed row lookup, cached
  per AIS_CONGESTION_CACHE_TTL_SECONDS (congestion) or queried directly by vessel_class
  (repositioning — a handful of rows, no caching needed at this scale).

TESTING PLAN:
  None dedicated (not a flagged high-risk calc; failure mode is a labelled fallback for
  both concerns). Manual check before demo: kill the listener process, confirm
  /port-status degrades to the "stale"/seeded-fallback path cleanly, and confirm a
  /recommendation solve for a class with no fresh vessel-position data still returns a
  plan via the calendar-only τ fallback — neither concern should ever produce a 500.
```

---

### FEATURE: Data Warehouse

```
MODULE STRUCTURE:
  /backend/warehouse/
    ├── models.py       # SQLAlchemy ORM models
    ├── db.py            # engine/session setup
    ├── migrations/      # alembic
    └── repository.py    # the ONLY module with query logic — everything else imports this

FUNCTION & CLASS DESIGN:
  models.py:
    RateHistory(route, vessel_class, date, rate, tier: str | None, source: Provenance)
    PortConstraint(name, max_draft_m, max_loa_m, max_beam_m, handling_rate_tpd,
                    tidal_dependent: bool, verified: bool, source: Provenance)
    VesselSpec(class_name, typical_capacity_tonnes, draft_m, loa_m, beam_m)
    ForecastObject(route, vessel_class, horizon_days, generated_at, point_estimate,
                    confidence_band, trajectory: JSON, driver_explanation, is_high_uncertainty,
                    model_used) — one row per route x vessel x horizon x generation date, per DOC2 §7
    CongestionSnapshot(port, vessel_count, avg_wait_hours, recorded_at, is_live)
    ExogenousFeature(source: str, date, value)   # NEW — Brent/WTI/Iron Ore/BDRY/GSCPI, DOC2 Addendum v3 §A2
    RoutePhysics(origin, destination, distance_nm, laden_consumption_tpd, ballast_consumption_tpd)
                                                   # NEW — feeds cost_terms.py's real bunker cost, §A2
    OperationalEvidence(route, vessel_class, observed_at, confidence_score, note)
                                                   # NEW — feeds engine/evidence.py, §A3
    VesselPositionSnapshot(imo: int [PK], vessel_name, vessel_class, dwt, current_lat,
                            current_lon, speed_knots, recorded_at)
                                                   # NEW — real candidate bulk-carrier
                                                   # telemetry (handoff Step 49G), feeds
                                                   # decision.py's repositioning-aware τ
                                                   # generation, §11.2 (v3 Final):
      class VesselPositionSnapshot(Base):
          __tablename__ = "vessel_position_snapshot"
          imo:         Mapped[int]      = mapped_column(Integer, primary_key=True)
          vessel_name: Mapped[str]      = mapped_column(String(100))
          vessel_class: Mapped[str]     = mapped_column(String(100), index=True)
          dwt:         Mapped[float]    = mapped_column(Float)
          current_lat: Mapped[float]    = mapped_column(Float)
          current_lon: Mapped[float]    = mapped_column(Float)
          speed_knots: Mapped[float]    = mapped_column(Float)
          recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

  repository.py exposes typed functions only, e.g.:
    get_latest_forecast(route, vessel_class, horizon_days) -> ForecastObject | None
    get_port_constraints() -> dict[str, PortConstraint]
    get_route_physics(origin, destination) -> RoutePhysics | None
    get_operational_evidence(route, vessel_class) -> list[OperationalEvidence]
    write_forecast(obj: ForecastObject) -> None
    write_congestion_snapshot(port, snapshot) -> None
    upsert_rate_history(rows: list[RateHistoryRow]) -> IngestResult
    get_valid_origins() -> list[str]          # NEW — Scope Catalog, DOC 2 Addendum v3 §A1
    get_valid_dest_ports() -> list[str]        # NEW — reads verified port_constraints rows
    get_valid_vessel_classes() -> list[str]    # NEW — reads verified vessel_specs rows
    upsert_vessel_position_snapshot(snapshot: VesselPositionSnapshot) -> None
                                               # NEW — written by both ais_listener.py's
                                               # continuous stream and vessel_position_ingest.py's
                                               # batch/backfill path, §11.2
    get_candidate_vessels_by_class(vessel_class: str) -> list[VesselPositionSnapshot]
                                               # NEW — real tracked candidates for a class,
                                               # used by decision.py's τ generation, §11.2
    get_earliest_repositioning_days(vessel_class: str, origin_port: str) -> float | None
                                               # NEW — ballast transit days from the
                                               # nearest/earliest candidate vessel's current
                                               # position to origin_port; None if no
                                               # coverage exists for that class (graceful
                                               # calendar-only fallback, §11.2)
  No caller outside repository.py ever constructs a SQLAlchemy query directly (DOC 2's
  general "no black box, auditable" principle extended to the data layer's boundaries).

  The three get_valid_*() functions are cached in-process for SCOPE_CATALOG_CACHE_TTL_SECONDS
  — scope doesn't change on every request, but does need to reflect new port-verification
  sign-offs within a few minutes, not require a redeploy.

INTERFACES & CONTRACTS:
  Every read function returns the same typed objects the prior build's data_access/schemas.py
  defined (PortConstraint, VesselSpec) plus the new ForecastObject/CongestionSnapshot
  persistence shapes — engine/ code should not need to change its consumption pattern
  much beyond "call repository.X() instead of loaders.X()".
  get_valid_origins()/get_valid_dest_ports()/get_valid_vessel_classes() return plain
  list[str] — this is the ONE place in the system where "is X in scope" is decided;
  api/schemas.py's request validation and the frontend's dropdown population both call
  through here (the API via a `GET /scope` route, DOC 3's API Layer section), never a
  hardcoded constant.

ERROR HANDLING STRATEGY:
  Connection failures raise a typed WarehouseUnavailableError, caught at the API layer and
  converted to a clear 503 with "backend data layer unreachable" — never a raw DB traceback
  reaching the frontend.

EDGE CASES TO HANDLE:
  - No forecast yet for a route x vessel x horizon (first boot, before first retrain
    completes) -> get_latest_forecast returns None, forecasting.py's get_forecast()
    surfaces this as ForecastUnavailableError, same pattern as the prior build
  - TimescaleDB extension not yet enabled (early in the build) -> RateHistory queries
    still function as plain Postgres, just without hypertable optimizations; add the
    extension once ingestion volume justifies it, not before
  - get_valid_dest_ports() returns an empty list (nothing verified yet, cold start) ->
    the API's /scope route and dashboard must render "no ports available yet" cleanly,
    not an empty-looking broken form
  - No RoutePhysics row for a given (origin, destination) -> cost_terms.py's bunker cost
    function must raise a clear error rather than silently falling back to a guessed
    distance — see FEATURE: Cost Terms Module's updated edge cases
  - get_candidate_vessels_by_class() / get_earliest_repositioning_days() return
    empty/None for a class with no AIS coverage yet -> NOT an error; decision.py's τ
    generation treats this exactly like the "no forecast yet" case above — graceful
    fallback to calendar-only candidates, tagged `assumed` (§11.2)

PERFORMANCE CONSIDERATIONS:
  Index ForecastObject on (route, vessel_class, horizon_days, generated_at DESC) —
  get_latest_forecast is the hottest read path, called on every /recommendation request.
  get_valid_*() functions are cheap distinct-value queries, cached per
  SCOPE_CATALOG_CACHE_TTL_SECONDS so they don't add a query to every request either.

TESTING PLAN:
  None dedicated at the ORM level — exercised transitively by engine tests, same
  testing-depth philosophy as the prior build's data_access layer.
```

---

### FEATURE: Forecasting Engine

```
MODULE STRUCTURE:
  /backend/engine/forecasting.py
    ├── train_and_evaluate():  scheduled entrypoint (called by ingestion/scheduler.py, weekly)
    ├── get_forecast():        the ONLY read path, called per-request
    ├── ConditionsMonitor:     level + volatility check — CARRIED OVER logic
    └── damped_trend():        fallback model — CARRIED OVER logic

FUNCTION & CLASS DESIGN:
  train_and_evaluate() -> None
    - Runs on RETRAIN_SCHEDULE_CRON, NOT at API startup (this is the one real behavior
      change from the prior build — see Decisions §0).
    - Per (route, vessel_class) pair in scope (up to 4 ports x 3 vessel classes x 3
      origins, per updated DEST_PORTS): fits Naive, ARIMA, XGBoost, Prophet.
    - Walk-forward validation (DOC 2 §18.2): rolling backtest, train up to T, test T+1..T+k,
      slide forward — never a random split.
    - Gate: a model only populates a stored ForecastObject if it beats the naive
      random-walk baseline on MAE/RMSE/MAPE/R² + directional accuracy. If XGBoost fails
      the gate, fall back to ARIMA, then naive-adjacent damped_trend.
    - Ablation: re-run the primary model with each exogenous feature removed, confirm
      each earns its place (logged, not blocking — informational for DOC2 §18.2).
    - < MIN_OBSERVATIONS_FOR_XGBOOST rows for a pair -> skip XGBoost, ARIMA/naive only,
      model_used reflects this.
    - Writes one ForecastObject per (route, vessel_class, horizon) via
      warehouse.repository.write_forecast().

  get_forecast(route, vessel_class, horizon_days) -> ForecastObject
    - Single public entrypoint every other module and the API route calls — SAME
      contract as the prior build's function of the same name.
    - Calls warehouse.repository.get_latest_forecast(...) — a read, not a compute.
    - Runs ConditionsMonitor.check(route) against the CURRENT day's live bunker/bdi/rate
      values (these are read fresh from the warehouse, independent of the stored
      forecast's generation date) — if it trips, the served forecast is the damped_trend
      variant already computed and gated at the last retrain, not a live recomputation.
    - SRP check: this function decides WHICH stored model output to serve; it triggers no
      training itself.

INTERFACES & CONTRACTS:
  ForecastObject = {
    route, vessel_class, horizon_days,
    point_estimate: float, confidence_band: (float, float),
    trajectory: list[{day: int, point_estimate: float}],   # read by Scenario Generator
    driver_explanation: str, is_high_uncertainty: bool,
    model_used: Literal["xgboost","arima","naive","damped_trend"],
    generated_at: datetime,
    provenance: Provenance   # NEW — "modeled", always, per DOC2 §12
  }
  Identical to the prior build's shape plus one field (provenance) — Scenario Generator
  and the MILP's cost terms consume this exact shape, nothing else.

ERROR HANDLING STRATEGY:
  get_forecast() raises ForecastUnavailableError if no gated forecast exists yet for that
  pair (e.g. before the first retrain completes, or a pair that never clears the naive
  baseline) — API converts to 422, same pattern as the prior build.

EDGE CASES TO HANDLE:
  - Retrain job itself fails mid-run for one pair -> that pair keeps serving its last
    successfully-gated ForecastObject rather than going unavailable; alert logged
  - horizon_days beyond what trajectory covers -> clamp, don't extrapolate silently
  - Conditions monitor trips between retrains (live bunker/bdi spikes) -> served forecast
    switches to damped_trend immediately on the next read, without waiting for the weekly
    retrain — this is why ConditionsMonitor.check() runs at READ time, not just at train time

PERFORMANCE CONSIDERATIONS:
  Weekly retrain across ~36 route x vessel pairs (4 ports x 3 origins x 3 vessel classes)
  x 3 horizons runs as an off-request background job — minutes are fine. get_forecast()
  is a single indexed warehouse read plus a cheap conditions check — must stay fast since
  it's called from inside the MILP's per-scenario cost evaluation.

TESTING PLAN:
  Not one of the three flagged high-risk areas (same reasoning as the prior build: a
  wrong forecast is bounded by its shipped confidence band). Manual verification of the
  walk-forward gate and conditions-monitor trip logic before demo.
```

---

### FEATURE: Constraint / Feasibility Engine

```
STATUS: CARRIED OVER — see Migration Delta §2 and §0.1 above.

The prior build's `engine/constraint.py`, its `FeasibleOption` shape, and
`tests/test_constraint_rules.py` are correct as-is. DOC 2 §8 confirms the same 8 rules
(draft, LOA, beam, parcel-fit, handling-rate estimate, tidal window, lightening,
vessel-size ranking hint) with the same semantics, including Rule 8's ranking hint being
advisory only. DEST_PORTS is no longer a fixed constant at all (DOC 2 Addendum v3 §A1) —
the rule functions operate on whatever PortConstraint rows the caller passes in, so this
module needs zero changes for scope growth; a new port (Vizag included, once its
constraints row exists — real or explicitly-flagged placeholder) just works.

ONE addition: FeasibleOption gains a tidal-window detail that now needs to reach the
Decision Engine's time-point selection (DOC 2 §8 Rule 6: "This detail is passed along to
the Decision Engine's entry-timing step rather than resolved here") — previously this was
informational only. Add a field, don't touch the rule functions:

  FeasibleOption += { tidal_window_note: str | None }  # already existed; now also consumed
                                                          # by decision.py's τ selection, not
                                                          # just displayed

Re-run the existing test file unmodified against this one additive field before Build Step 5
is considered done — if it still passes, the carry-over is confirmed clean.
```

---

### FEATURE: Scenario Generator

```
MODULE STRUCTURE:
  /backend/engine/scenario.py
    └── generate_scenarios(): the sole public function

FUNCTION & CLASS DESIGN:
  generate_scenarios(forecast: ForecastObject) -> ScenarioPaths
    - Base: forecast.trajectory as-is.
    - Optimistic: each trajectory point shifted toward the favorable edge of
      forecast.confidence_band by SCENARIO_OPTIMISTIC_BAND_FRACTION.
    - Pessimistic: symmetric shift toward the unfavorable edge.
    - Pure function — no I/O, no model calls, takes one ForecastObject in, returns three
      labelled trajectories out. Independently unit-testable for exactly that reason.
    - "Favorable"/"unfavorable" direction depends on whether this is a cost the requester
      pays (freight rate: favorable = lower) — this directionality is a named constant
      per use case, not inferred implicitly, to avoid a silent sign-flip bug.

INTERFACES & CONTRACTS:
  ScenarioPaths = {
    base: list[{day, point_estimate}],
    optimistic: list[{day, point_estimate}],
    pessimistic: list[{day, point_estimate}]
  }
  This is exactly what decision.py's per-scenario cost evaluation (C_s in DOC 2 §11.3)
  iterates over — three trajectories, same shape as ForecastObject.trajectory.

ERROR HANDLING STRATEGY:
  None needed beyond what ForecastObject already guarantees (non-empty trajectory) —
  this function cannot itself fail given a valid ForecastObject.

EDGE CASES TO HANDLE:
  - confidence_band is (x, x) (zero width, degenerate) -> all three scenarios collapse to
    the same path; not an error, just means the forecast is very confident
  - trajectory has only one point (short horizon) -> all three scenarios have one point too

PERFORMANCE CONSIDERATIONS:
  Trivial — a few arithmetic operations per trajectory point, called once per
  (route, vessel_class) pair relevant to a request, well inside the MILP solve's own budget.

TESTING PLAN:
  Unit: known ForecastObject + known confidence_band -> hand-calculated Optimistic/
  Pessimistic values. Not one of the three flagged high-risk areas on its own, but it
  feeds directly into the MILP objective, so its output is exercised heavily by
  test_decision_engine_milp.py's fixtures rather than tested in isolation as high-risk.
```

---

### FEATURE: Cost Terms Module

```
STATUS: REINVENTED — not carried over. See §0.1's correction note above for why.

WHY THE OLD FORMULAS DON'T SURVIVE:
  1. `_price_spot_voyage(quantity, forecast, timing)` took a pre-resolved `TimingDecision`
     from the prior build's standalone entry-timing sub-routine. That sub-routine no
     longer exists as a separate step — timing is now a MILP decision variable (z_{i,\u03c4}),
     chosen BY the solve, not before it. A cost function that requires the answer before
     it can compute the answer's cost is backwards for a MILP: the solver needs a cost
     COEFFICIENT for every candidate \u03c4 (and every candidate vessel/port/mode/scenario)
     before it runs, so it can compare them. This module produces that coefficient table.
  2. The old formula covered freight + bunker + port handling + lightening only. DOC 2
     §5.6 is explicit that C_s also includes tax and waiting terms. These were simply
     missing before, not implicit in something else.
  3. Locked-mode pricing has a subtlety the old single-forecast design never had to
     handle: DOC 2 §10 prices a locked voyage using "the Base-path rate at the lock
     date" — NOT the Base/Optimistic/Pessimistic rate for whichever scenario s is being
     evaluated. A locked voyage's cost is the same fixed number across all three
     scenario evaluations of C_s (that's what "locked" means — it doesn't move with the
     market). Getting this wrong (re-deriving locked cost per scenario) would silently
     make locked voyages look artificially risk-sensitive in the robustness readout —
     exactly the kind of bug the flagged-high-risk testing exists to catch.

MODULE STRUCTURE:
  /backend/engine/cost_terms.py
    ├── spot_freight_cost():        quantity x rate at a specific (route, vessel, τ, scenario)
    ├── locked_freight_cost():      quantity x Base-path rate at lock day, minus commitment_benchmark
    ├── bunker_cost():               distance-based physics — laden/ballast consumption over
    │                                 real nautical distance (DOC 2 Addendum v3 §A2), not a
    │                                 flat assumed per-day placeholder
    ├── port_handling_cost():        from PortConstraint.handling_rate_tpd + PORT_HANDLING_DAY_RATE_USD
    ├── waiting_cost():               idle days x WAITING_COST_PER_DAY_USD
    ├── tax_cost():                   quantity x TAX_RATE_PCT
    ├── lightening_penalty_cost():    from FeasibleOption.lightening_penalty_days
    ├── repositioning_cost():         NEW — ballast fuel consumption during repositioning,
    │                                 only when real AIS coordinates ground the voyage
    │                                 (§11.2); 0.0 and tagged `assumed` in fallback mode
    └── build_cost_coefficient():     orchestrates all of the above into ONE number per
                                        (voyage, vessel, port, τ, mode, scenario) — this is
                                        the function decision.py actually calls when
                                        constructing the MILP's objective coefficients

FUNCTION & CLASS DESIGN:
  spot_freight_cost(quantity: float, rate: float) -> float
    - quantity x rate. `rate` is the scenario path's point estimate AT the specific day
      τ being evaluated — resolved by the caller (decision.py) before this is called;
      this function stays a pure one-liner precisely so it's trivially testable.

  locked_freight_cost(quantity: float, base_rate_at_lock_day: float,
                       commitment_benchmark_pct: float) -> float
    - quantity x base_rate_at_lock_day x (1 - commitment_benchmark_pct / 100)
    - Caller MUST pass the Base scenario's rate regardless of which scenario s the
      overall C_s is being computed for — see point 3 above. decision.py's coefficient
      loop is responsible for holding this constant across s; this function has no way
      to enforce that itself, which is exactly why it's called out in the test plan below.

  bunker_cost(route_physics: RoutePhysics, laden: bool, bunker_price_usd_per_tonne: float) -> float
    - (route_physics.laden_consumption_tpd if laden else route_physics.ballast_consumption_tpd)
      x (route_physics.distance_nm / assumed_speed_knots / 24) x bunker_price_usd_per_tonne
    - route_physics comes from warehouse.repository.get_route_physics(origin, destination) —
      real distance/consumption data, tagged provenance="measured" (DOC 2 Addendum v3 §A2),
      replacing the prior placeholder-constant design. bunker_price_usd_per_tonne still
      comes from the warehouse's latest measured bunker price, unchanged from before.
    - If no RoutePhysics row exists for a given (origin, destination) pair, this function
      raises rather than guessing a distance — see edge cases below.

  port_handling_cost(quantity: float, port: PortConstraint) -> float
    - (quantity / port.handling_rate_tpd) x PORT_HANDLING_DAY_RATE_USD
    - Reuses the SAME discharge-duration estimate Rule 5 (§5.5, carried-over constraint
      engine) already produces — do not recompute discharge days here independently.

  waiting_cost(idle_days: float) -> float
    - idle_days x WAITING_COST_PER_DAY_USD. `idle_days` is supplied by decision.py from
      the gap between a voyage's arrival-ready date and its actual berth/fix date — this
      module doesn't compute idle days itself, only prices a given amount of it.

  tax_cost(quantity: float) -> float
    - quantity x (TAX_RATE_PCT / 100) x <effective freight rate used for that voyage>.
      Kept as its own function (rather than folded into freight_cost) specifically so its
      "assumed" provenance tag stays attached to a single, isolatable line in the
      5-bucket cost breakdown, not smeared across the freight bucket.

  lightening_penalty_cost(feasible_option: FeasibleOption) -> float
    - feasible_option.lightening_penalty_days x PORT_HANDLING_DAY_RATE_USD (reuses the
      same day-rate as ordinary port handling — a lightening call is priced as an extra
      port day, not a separate cost category)
    - Returns 0.0 if lightening_required is False (never None — see prior build's
      "not applicable != free" edge case, still holds).

  repositioning_cost(ballast_consumption_tpd: float | None, repositioning_days: float | None,
                      bunker_price_usd_per_tonne: float) -> float
    - ballast_consumption_tpd x repositioning_days x bunker_price_usd_per_tonne (DOC 2
      §11.2/§11.4, v3 Final).
    - repositioning_days comes from warehouse.repository.get_earliest_repositioning_days()
      via decision.py's τ generation (§11.2, and FEATURE: Decision Engine below).
    - If either input is None (no real AIS position data grounds this class/route —
      fallback mode), returns 0.0 and the caller tags that term `assumed` rather than
      omitting it — consistent zero, not a missing value, same pattern as waiting_cost's
      idle_days=0 case below.

  build_cost_coefficient(quantity, vessel_class, port: PortConstraint,
                          feasible_option: FeasibleOption, mode: Literal["spot","locked"],
                          rate_at_tau: float, base_rate_at_lock_day: float,
                          commitment_benchmark_pct: float, bunker_price: float,
                          voyage_duration_days: float, idle_days: float,
                          repositioning_days: float | None = None,
                          ballast_consumption_tpd: float | None = None) -> CostBreakdown
    - Calls the above sub-functions, sums them, and returns BOTH the total AND the
      5-bucket breakdown (ocean freight, bunker, port & handling, lightening/extra calls,
      risk buffer) — DOC 2 §11.7's output requirement. "risk buffer" = the spread between
      this coefficient's Optimistic and Pessimistic values for the same voyage, computed
      by decision.py after calling this three times (once per scenario), not by this
      function itself.
    - repositioning_cost() folds into the existing "bunker" bucket (it's still bunker
      fuel, just for the ballast leg) rather than adding a 6th bucket — DOC 2 §11.7's
      5-bucket shape stays fixed regardless of whether repositioning grounds a given
      voyage or not.

INTERFACES & CONTRACTS:
  CostBreakdown = {
    ocean_freight: float, bunker: float, port_handling: float,
    lightening_extra: float, tax: float, total: float,
    provenance: Provenance  # "assumed" if tax/waiting/port-day-rate placeholders
                              # dominate the term; "measured"/"modeled" for the now-real
                              # bunker/freight terms (DOC 2 Addendum v3 §A2)
  }
  This is exactly the shape decision.py's per-(voyage, τ, mode, scenario) coefficient
  table is built from, and exactly the shape the dashboard's 5-bucket stacked bar and
  WhyNotComparator render without reshaping.

ERROR HANDLING STRATEGY:
  Pure functions, no I/O — the only way this module fails is a caller passing an
  (origin, destination) pair with no RoutePhysics row (KeyError-equivalent lookup miss),
  which should be a loud ValueError, same "programming error, not a business outcome"
  pattern as constraint.py — decision.py must have already confirmed the pair is in
  scope before calling bunker_cost().

EDGE CASES TO HANDLE:
  - commitment_benchmark_pct = 0 -> locked_freight_cost degenerates to
    quantity x base_rate_at_lock_day exactly, no discount — must not error or produce NaN
  - idle_days = 0 -> waiting_cost returns 0.0, not skipped/None (consistent zero, not a
    missing value, so it still shows as a $0 line in the breakdown rather than vanishing)
  - No RoutePhysics row for a given (origin, destination) -> ValueError, loud failure
    rather than a nonsensical guessed distance; this should only happen if
    decision.py's candidate-generation step has a bug, since it's expected to filter to
    only route pairs the warehouse actually has physics data for
  - repositioning_days=None / ballast_consumption_tpd=None (no AIS position data for
    that class — fallback mode) -> repositioning_cost() returns 0.0, NOT an error; this
    is the expected, common path for a class/route outside current MyShipTracking
    coverage, distinct from the RoutePhysics case above which IS a bug if it occurs

PERFORMANCE CONSIDERATIONS:
  Every function here is O(1) arithmetic. build_cost_coefficient() is called once per
  (voyage, vessel, port, τ, mode, scenario) combination the MILP considers before the
  solve — at the scale DOC 2 §11.1 targets (small candidate sets, decomposed variables),
  this is a few hundred calls at most, negligible next to the solve itself.

TESTING PLAN — one of the three flagged high-risk areas, per §0:
  Unit: spot_freight_cost, bunker_cost, port_handling_cost, waiting_cost, tax_cost,
    lightening_penalty_cost each against hand-calculated expected values from fixed inputs.
  Unit: locked_freight_cost's 0%-discount edge case, and a non-zero discount case.
  **Critical test, specific to the reinvention:** call build_cost_coefficient() three
    times for the SAME locked voyage across Base/Optimistic/Pessimistic scenario rates,
    and assert the locked_freight_cost component is IDENTICAL across all three — this is
    the exact bug class DOC 2 §10's "Base-path rate at the lock date" phrasing exists to
    prevent, and it's cheap to silently get wrong.
  Unit: build_cost_coefficient()'s 5-bucket breakdown sums to the same total as adding
    the buckets independently (catches a bucket left out of the total by mistake).
  Unit: repositioning_cost() with both real inputs (non-zero result) and with either
    input None (must return exactly 0.0, not raise) — the graceful-fallback contract
    §11.2 depends on.
```

---

### FEATURE: Decision Engine (MILP Optimizer)

```
MODULE STRUCTURE:
  /backend/engine/decision.py
    ├── solve():                the public entrypoint — replaces the prior build's search_strategies()
    ├── _build_variables():     constructs q_i, x_{i,v}, y_{i,p}, z_{i,\u03c4}, w_{i,m}, \u2113_{i,p}
    ├── _compute_tau():         NEW (handoff Step 51A, DOC 2 §11.2 v3 Final) — generates the
    │                            candidate τ set per class/route, repositioning-aware where
    │                            AIS position data grounds it, calendar-only fallback otherwise
    ├── _build_constraints():   cargo conservation, capacity, one-assignment, feasibility
    │                            linking, lightening consistency, timing, human overrides
    ├── _objective_min_max_cost(): builds C_s per scenario using cost_terms.py's REINVENTED
    │                            build_cost_coefficient(), then the min-max wrapper
    ├── _solve_cbc():           the actual PuLP+CBC call, timeout-bounded
    ├── _hybrid_fallback():     CARRIED OVER-shaped enumeration (voyage_count x commitment_mode)
    │                            if the MILP solve times out or fails
    └── /backend/tests/test_decision_engine_milp.py   \u2190 one of the three flagged high-risk areas

FUNCTION & CLASS DESIGN:
  solve(cargo_quantity, origin_port, discharge_ports, timing_flexibility_days,
        commitment_benchmark_pct=None, constraints: HumanOverrides | None = None
        ) -> tuple[Strategy, list[Strategy]]
    1. Resolve candidate (route, vessel_class) pairs from origin_port x discharge_ports x
       VESSEL_CLASSES, call constraint.check_feasibility(...) per candidate — CARRIED OVER call.
    2. For each feasible pair, call forecasting.get_forecast(...), then
       scenario.generate_scenarios(forecast) — one ScenarioPaths per pair.
    3. _build_variables(): decomposed q_i/x/y/z/w/\u2113 per DOC 2 §11.1's variable table, over a
       small candidate voyage-count range (still bounded, e.g. 1-3, but SPLITS ARE NOT
       forced even — this is the actual capability upgrade over the prior build).
    4. _compute_tau() — τ (time points) computed per DOC 2 §11.1/§11.2, enriched with
       Step 51A repositioning feasibility (NEW):
       a. Base candidate set: today, end of each week inside timing_flexibility_days,
          end of the flexibility window, and any local minimum in each candidate's
          forecast trajectory — unchanged from before.
       b. Repositioning feasibility: look up candidate vessel positions for the
          requested vessel class in the origin region via
          repository.get_candidate_vessels_by_class(vessel_class). If any exist, compute
          ballast distance (current position -> loading origin) via RoutePhysics or a
          great-circle fallback, then
          ballast_transit_days = distance_nm / (ballast_speed_knots * 24)
          — using the vessel's own AIS-reported speed where available, else
          DEFAULT_BALLAST_SPEED_KNOTS. Set
          earliest_feasible_departure = today + ballast_transit_days, and bound the
          generated τ points to
          [earliest_feasible_departure, timing_flexibility_end].
       c. Graceful fallback: if no AIS position exists for that class (cold start, feed
          down, or a class outside MyShipTracking coverage), τ generation falls back to
          the (a) calendar-only candidates unchanged, tagged `assumed` — same pattern as
          every other "real data if available, labelled fallback if not" component in
          this system (§18.1).
       d. Variable invariant, explicit: decision variables remain x_{i,v} at the
          vessel-CLASS level, never per-IMO, even when a real tracked vessel's position
          grounds step (b) — this is what keeps the CBC solve strictly inside the
          `<4s` MILP_SOLVE_TIMEOUT_SECONDS budget (§11.1/§14; see also this doc's §0
          scope-boundary decision row for why per-IMO/fleet-portfolio assignment is a
          deliberately separate, deferred problem).
    5. _build_constraints(): includes feasibility linking straight from
       constraint.check_feasibility()'s output (Rules 1-3/6/7 inherited, not re-derived),
       and constraints (HumanOverrides) applied as variable fixing, not new binaries
       (DOC 2 §11.5: "these don't need a parallel set of override binaries").
    6. _objective_min_max_cost(): calls cost_terms.build_cost_coefficient() per
       (voyage, vessel, port, τ, mode, scenario) combination — see FEATURE: Cost Terms
       Module above for why this replaces the prior build's formulas rather than reusing
       them. Locked-mode coefficients are computed once against the Base rate and reused
       identically across all three scenario evaluations, per that section's edge case.
    7. _solve_cbc() with MILP_SOLVE_TIMEOUT_SECONDS. On success: extract the winning
       assignment, compute the 5-bucket cost breakdown, worst-case cost across scenarios.
       On timeout/failure: _hybrid_fallback() runs the CARRIED OVER-shaped enumeration
       instead, still returns a full scenario_comparison[] — DOC 2 §11.6: "never a blank
       screen in a demo."
    8. Always also compute the pure-spot and pure-locked baselines as additional entries
       in scenario_comparison[] (DOC 2 §11.7 output requirement).

  DEFERRAL NOTE (mirrors DOC 2 §13; this is the note §0's scope-boundary decision row
  points to): Step 51V's batch fleet portfolio optimizer (allocating 16 contracts across
  36 ships, with 10,890 non-overlap conflict edges, over a ~118s solve) is an offline
  batch operations pipeline. It is NOT part of the interactive POST /recommendation API
  path — solve() above always solves for exactly one cargo_request against one
  candidate fleet, never a multi-contract portfolio allocation. If/when the batch
  optimizer is built, it lives as its own standalone script/service reading from the
  same warehouse tables, not as a mode or parameter of decision.py.

  HumanOverrides = {
    exclude_vessel: list[str] | None, require_port: str | None,
    max_completion_day: int | None, force_mode: Literal["spot","locked"] | None,
    min_fix_day: int | None
  }
  This is the exact schema the chatbot (§2c) and dashboard controls (§5.10) both write into.

INTERFACES & CONTRACTS:
  Strategy = {
    voyage_count: int, commitment_mode: str | "mixed",   # "mixed" now possible — MILP can
                                                            # assign different modes per voyage
    voyages: list[{port, vessel_class, mode, cost_by_scenario: {base, optimistic, pessimistic},
                   fix_day: int, feasibility: FeasibleOption}],
    total_cost_worst_case: float,
    cost_breakdown: {ocean_freight, bunker, port_handling, lightening_extra, risk_buffer},  # 5-bucket, DOC2 §11.7
    contains_high_uncertainty_voyage: bool,
    solved_via: Literal["milp","hybrid_fallback"],   # visible, never hidden which path produced this
    provenance: Provenance
  }
  API's /recommendation route returns {recommendation: Strategy, scenario_comparison: list[Strategy]}
  — same top-level contract as the prior build, richer Strategy internals.

ERROR HANDLING STRATEGY:
  If constraint.check_feasibility() returns zero feasible options across ALL candidates,
  solve() returns an explicit empty-recommendation result with a clear reason, never a
  500 (same principle as the prior build). If HumanOverrides make the feasible region
  empty (e.g. exclude_vessel excludes every option that clears the ports), same explicit
  empty result, with the reason naming which override caused it — not a generic "no
  solution found."

EDGE CASES TO HANDLE:
  - MILP solve exceeds MILP_SOLVE_TIMEOUT_SECONDS -> _hybrid_fallback(), solved_via flags it
  - commitment_benchmark_pct not supplied -> DEFAULT_COMMITMENT_BENCHMARK_PCT used,
    is_default_benchmark=True flagged (same as prior build) so ProvenanceBadge renders
    "assumed" automatically
  - HumanOverrides.max_completion_day shorter than any feasible \u03c4 -> empty result with
    that specific reason, not a silent relaxation of the constraint
  - Regret formulation NOT built for this pass (DOC 2 §11.3: documented upgrade, ships
    later) — solve() takes an unused `use_regret: bool = False` parameter reserved for
    that upgrade so the call signature doesn't need to change later, but only min-max-cost
    is implemented now

PERFORMANCE CONSIDERATIONS:
  Decomposed variables + event-based time points keep the binary count roughly two orders
  of magnitude below a single joint index (DOC 2 §11.1) — this is what keeps the CBC solve
  inside a 3-4s budget at this scale. Do not fold variables back into a joint index for
  "simplicity" — that reintroduces the exact combinatorial blowup this design avoids.

TESTING PLAN:
  Unit: _build_constraints() linking logic against a known feasible_options[] fixture —
    confirm infeasible (v,p) pairs are correctly excluded from the variable's domain.
  Unit: _objective_min_max_cost() against hand-calculated C_s for a small 2-voyage,
    3-scenario fixture — this is THE calculation a live-demo cost comparison depends on.
  Unit: HumanOverrides variable-fixing — confirm exclude_vessel/force_mode/max_completion_day
    each correctly shrink the feasible region without altering the objective itself.
  Integration: _hybrid_fallback() triggers correctly when solve time is artificially
    forced past MILP_SOLVE_TIMEOUT_SECONDS (mock the solver call), and still returns a
    valid, ranked scenario_comparison[].
```

---

### FEATURE: Provenance & Explainability Layer

```
MODULE STRUCTURE:
  /backend/engine/provenance.py

FUNCTION & CLASS DESIGN:
  Provenance = Literal["measured", "modeled", "assumed"]

  A small set of tagging helpers, used at the point each number originates — NOT
  retrofitted at the API or dashboard layer:
    tag_measured() -> Provenance            # e.g. ingested BDI/bunker/port constraint values
    tag_modeled(uncertainty_flag: bool) -> Provenance   # forecasts, derived costs
    tag_assumed(note: str) -> tuple[Provenance, str]    # commitment_benchmark, tax/duty
                                                          # placeholders, canal dues

  Every relevant pydantic/ORM model (ForecastObject, Strategy, cost-breakdown buckets,
  CongestionSnapshot) carries a `provenance: Provenance` field (and `provenance_note: str
  | None` where "assumed") set at construction time by the module that produced the
  value — forecasting.py sets "modeled" on every ForecastObject it writes; decision.py
  sets "assumed" + a note on commitment_benchmark-derived cost terms specifically, not on
  the whole Strategy.

INTERFACES & CONTRACTS:
  This is intentionally NOT a separate service or database table — it's a shared type
  imported wherever a number needs to carry its own honesty label, per DOC 2 §12's
  "every number on the dashboard carries a small badge" requirement. Centralizing it here
  (rather than each module inventing its own labeling) is what prevents drift where one
  engine's output is taggable and another's silently isn't.

  Sensitivity/robustness readouts (tornado chart, worst-case cost) are NOT new backend
  compute — DOC 2 §16.3 is explicit that these are "built directly from re-running the
  already-cached scenario cost terms." Implement as a function inside decision.py
  (compute_sensitivity(strategy: Strategy, perturbation_pct: float) -> SensitivityResult)
  that reuses the same C_s cost terms already computed during solve(), not a new solve
  per bar.

ERROR HANDLING STRATEGY: N/A — this is a tagging convention plus one pure derived-metrics
  function, not a service with its own failure modes.

EDGE CASES TO HANDLE:
  - A value with no clear single source (e.g. total_cost_worst_case, itself a function of
    both measured and modeled inputs) -> tagged "modeled" at the coarsest level the
    dashboard actually displays it at; per-bucket provenance in the 5-bucket breakdown is
    what lets a user drill into which specific term is "assumed"

PERFORMANCE CONSIDERATIONS: negligible — tag assignment is O(1) per object.

TESTING PLAN: None dedicated — covered by whatever module sets the tag (e.g.
  test_decision_engine_milp.py confirms commitment_benchmark-derived terms are tagged
  "assumed" when DEFAULT_COMMITMENT_BENCHMARK_PCT is used).
```

---

### FEATURE: Operational Evidence Layer

```
STATUS: NEW — DOC 2 Addendum v3 §A3. Promoted from "optional future idea" to a real
build step now that real ShipOffer broker data exists.

MODULE STRUCTURE:
  /backend/engine/evidence.py
    └── score_operational_evidence(): the sole public function

FUNCTION & CLASS DESIGN:
  score_operational_evidence(route: str, vessel_class: str) -> OperationalEvidenceScore
    - Reads warehouse.repository.get_operational_evidence(route, vessel_class) — recent
      ShipOffer broker fixture/position observations for this route×vessel pair.
    - Computes a simple, explainable confidence signal (e.g. count and recency of
      matching real fixtures, not a black-box ML score) — DOC 2 Addendum v3 §A3
      deliberately keeps this a heuristic, auditable calculation, consistent with the
      rest of the system's "no black box" principle (DOC 2's general architecture stance).
    - Called AFTER decision.solve() has already produced a ranked Strategy — this
      function scores candidates the Decision Engine already picked, it does not
      influence which candidates get picked.

INTERFACES & CONTRACTS:
  OperationalEvidenceScore = {
    route: str, vessel_class: str,
    confidence: Literal["strong", "moderate", "weak", "no_data"],
    observation_count: int, most_recent_observation_at: datetime | None,
    note: str,              # plain-language explanation, e.g. "3 matching broker
                              # fixtures in the last 14 days on this lane"
    provenance: Provenance  # always "modeled" — real underlying data, heuristic score
  }
  Consumed by: the dashboard's OperationalEvidenceBadge (per-voyage, alongside
  ProvenanceBadge) and WhyNotComparator (as additional context when explaining why one
  option ranked below another) — never by decision.py or cost_terms.py.

ERROR HANDLING STRATEGY:
  No observations for a route×vessel pair -> confidence="no_data", NOT an error and NOT
  treated as "weak" (a genuine absence of market data is a different claim than "the
  market disagrees with this recommendation" — conflating them would misinform).

EDGE CASES TO HANDLE:
  - ShipOffer ingestion hasn't run yet / warehouse has zero OperationalEvidence rows ->
    confidence="no_data" for everything, badge renders as "no market data yet," not blank
  - A route×vessel pair the Decision Engine picked has strong evidence but a
    lower-ranked alternative has none -> both are scored independently and shown as-is;
    this module never re-ranks or second-guesses the Decision Engine's output

PERFORMANCE CONSIDERATIONS:
  Called once per voyage in the winning Strategy (and optionally per
  scenario_comparison[] entry for WhyNotComparator) — a handful of cheap warehouse reads
  per request, well within the existing request budget.

TESTING PLAN:
  Not one of the three flagged high-risk areas — this is an advisory overlay, not a
  number that drives cost or feasibility decisions, so a wrong confidence score can't
  silently misinform the actual chartering recommendation the way a cost-formula or
  MILP bug could. Unit test the confidence-tier thresholds against known fixture counts;
  manual spot-check before demo otherwise.
```

---

### FEATURE: API Layer

```
MODULE STRUCTURE:
  /backend/api/
    ├── main.py
    ├── routes/recommendation.py, forecast.py, compatible_vessels.py, scenario.py,
    │          port_status.py, health.py, scope.py    — six original names UNCHANGED
    │          (DOC 2 §15) + scope.py NEW (DOC 2 Addendum v3 §A1)
    └── schemas.py

FUNCTION & CLASS DESIGN:
  Each route file stays a thin pass-through, same principle as the prior build:
  parse request -> call exactly one engine function -> shape response.

  POST /recommendation
    body: {cargo_quantity, origin_port, discharge_ports[], timing_flexibility_days,
           commitment_benchmark_pct?, voyage_count?, commitment_mode?, constraints?}
                                                                          # NEW: constraints
    -> calls decision.solve(...), passing constraints through as HumanOverrides
    -> returns {recommendation: Strategy, scenario_comparison: list[Strategy]}

  POST /scenario
    body: same as /recommendation but voyage_count/commitment_mode REQUIRED (pinned
    "what if" query, DOC 2 §11.5) -> same underlying decision.solve() call, always pinned

  GET /forecast?route=&vessel_class=&horizon_days=
    -> forecasting.get_forecast(...), returns ForecastObject as-is (now includes provenance)

  GET /compatible-vessels?cargo_quantity=&discharge_ports=
    -> constraint.check_feasibility(...) directly — CARRIED OVER call, unchanged

  GET /port-status?port=
    -> congestion.get_congestion_snapshot(port)

  GET /scope   (NEW, DOC 2 Addendum v3 §A1)
    -> calls repository.get_valid_origins() / get_valid_dest_ports() / get_valid_vessel_classes()
    -> returns {origins: list[str], dest_ports: list[str], vessel_classes: list[str]}
    -> this is what the dashboard's form dropdowns and schemas.py's request validation
       both read from — the single source of truth for "what's currently supported"

  GET /health
    -> {status, models_loaded: bool, warehouse_reachable: bool, last_retrain_at: datetime,
        ais_listener_last_seen: datetime}   # richer than the prior build's single flag,
                                              # since there's now more that can independently fail

INTERFACES & CONTRACTS:
  schemas.py validates: cargo_quantity > 0, discharge_ports subset of
  repository.get_valid_dest_ports() (cached via SCOPE_CATALOG_CACHE_TTL_SECONDS, NOT a
  hardcoded constant per DOC 2 Addendum v3 §A1), vessel_class subset of
  get_valid_vessel_classes(), PLUS the new `constraints` object's fields validated
  against the same live scope (e.g. exclude_vessel entries must be currently-valid
  vessel classes) before reaching decision.py — invalid overrides never silently
  produce an empty-feeling "no solution" response when the real cause is a typo.

ERROR HANDLING STRATEGY:
  Single exception handler in main.py, unchanged principle from the prior build — no raw
  traceback ever reaches the frontend. WarehouseUnavailableError -> 503 specifically
  (new — the prior build had no external dependency that could be "down" this way).

EDGE CASES TO HANDLE:
  - constraints object present but empty ({}) -> treated identically to constraints=None,
    full unconstrained search
  - /scenario called with a HumanOverrides constraints object AND voyage_count/
    commitment_mode pins that conflict (e.g. force_mode="locked" but commitment_mode=
    "all-spot") -> 422 naming the conflict, not silently letting one win
  - /scope called before any port/vessel has been verified (cold start) -> returns empty
    lists, not an error — the dashboard must render this as "nothing available yet,"
    per the Data Warehouse section's matching edge case

PERFORMANCE CONSIDERATIONS:
  /recommendation's latency is now solver-bound (up to MILP_SOLVE_TIMEOUT_SECONDS) rather
  than the prior build's near-instant brute force — this needs to be visible to the
  frontend (loading state), not assumed instant.

TESTING PLAN:
  None dedicated at the route level, same as prior build — routes are thin pass-throughs
  to already-tested engine functions.
```

---

### FEATURE: Dashboard (React + Recharts)

```
MODULE STRUCTURE:
  /frontend/src/
    ├── App.tsx, pages/RecommendationPage.tsx
    ├── components/  — StrategyTable, ForecastChart, ScenarioFanChart, AISRouteMap,
    │                  WhatIfSliders, ProvenanceBadge, SensitivityPanel, RobustnessReadout,
    │                  WhyNotComparator, ExecutiveBriefExport, OperationalEvidenceBadge
    └── lib/apiClient.ts

FUNCTION & CLASS DESIGN:
  apiClient.ts: one typed function per endpoint (getRecommendation, getForecast,
    getPortStatus, getScope, getHealth), all funneled through a single fetch wrapper with
    a consistent {error} shape on failure — same principle as the prior build's api_client.py.

  RecommendationPage.tsx:
    - 4 core fields (cargo qty, origin, destination(s), timing flexibility) + collapsed
      "advanced" commitment_benchmark control, DOC 2 §16.1 exact label text: "Assumed
      locked-rate discount vs spot (user-set). Default: X%. Adjust based on current market
      negotiations."
    - Origin/destination/vessel-class options for these fields are fetched from getScope()
      on mount, NOT hardcoded — the form grows automatically as new ports/origins/vessel
      classes get verified in the warehouse (DOC 2 Addendum v3 §A1), with no frontend
      redeploy needed.
    - On submit: getRecommendation(), passes result down — this page does no cost math,
      purely orchestrates state + renders children (unchanged principle from the prior
      Streamlit tab).
    - Holds the current Strategy/scenario_comparison[] in React state (component-local or
      a lightweight store) so WhatIfSliders can trigger re-fetches without a full page reload.

  WhatIfSliders.tsx (NEW, DOC 2 §16.3 item 1):
    - Cargo quantity, timing-flexibility window, commitment_benchmark as draggable sliders.
    - Debounced ~400ms, fires the SAME getRecommendation() call as the form submit —
      no separate endpoint, no separate code path.
    - This is explicitly called out in DOC 2 as "the single most demo-persuasive feature
      to build" — prioritize it once RecommendationPage's base form path works.

  ScenarioFanChart.tsx (NEW): Recharts overlay of Base/Optimistic/Pessimistic trajectories
    around the ForecastChart's confidence band, with the chosen fix date marked.

  AISRouteMap.tsx (NEW): origin/discharge ports plotted with live port_congestion_snapshot
    density — reuses /port-status, no new backend data.

  WhyNotComparator.tsx (NEW): clicking a non-winning scenario_comparison[] entry opens a
    side-by-side cost breakdown vs. the winner — pure re-render of already-fetched data,
    no new call.

  ExecutiveBriefExport.tsx (NEW): renders the current recommendation_response into a
    single exportable page (print-to-PDF or a formatted view) — pure formatting, DOC 2
    §5.10 item 5.

  ProvenanceBadge.tsx: small reusable component, takes {provenance, note?}, renders the
    measured/modeled/assumed badge with hover detail — used inside every other component
    that renders a number from the API (StrategyTable, ForecastChart, cost breakdown rows).

INTERFACES & CONTRACTS:
  Every component takes the exact typed shape the API returns (Strategy, ForecastObject,
  CongestionSnapshot, now each including `provenance`) — TypeScript interfaces mirroring
  the backend pydantic schemas, generated or hand-kept in sync, no re-shaping inside a
  component (same "reshape once, in apiClient, never in four render functions" principle
  as the prior build).

ERROR HANDLING STRATEGY:
  Failed API calls render a clear error banner, never an unhandled exception reaching
  React's default error boundary. A fully-timed-out /recommendation (rare, but possible
  given solver latency) shows a distinct "still solving, this can take a few seconds"
  state rather than looking identical to a hard failure.

EDGE CASES TO HANDLE:
  - Backend unreachable on load -> /health check on mount shows "backend unreachable"
    cleanly (same principle as prior build's Streamlit startup check)
  - All scenario_comparison[] entries infeasible -> explicit "no feasible strategy for
    this input" message, not a blank table
  - WhatIfSliders dragged rapidly -> debounce must actually cancel in-flight stale
    requests, not just delay firing them, or a fast drag can render an out-of-date result
    after a newer one

PERFORMANCE CONSIDERATIONS:
  Given /recommendation's solver-bound latency, WhatIfSliders' debounce window and a
  visible loading/skeleton state for StrategyTable matter more here than they did against
  the prior build's near-instant brute force.

TESTING PLAN:
  None automated (UI layer, excluded per §0 testing-depth decision) — manual click-
  through of the full demo flow, same principle as the prior build.
```

---

### FEATURE: Chatbot

```
MODULE STRUCTURE:
  /frontend/src/chat/ChatPanel.tsx
  Server-side tool-calling logic — a small backend route or edge function wrapping the
  Claude API call (kept out of the browser since ANTHROPIC_API_KEY shouldn't ship client-side;
  this is a change from the prior build's Streamlit-process-holds-the-key design, since a
  React SPA has no equivalent trusted process to hold a secret in).
  `[ASSUMPTION: implemented as a small FastAPI route, e.g. POST /chat, that holds the key
  server-side and proxies the Claude tool-calling loop — confirm before Build Step 11.]`

FUNCTION & CLASS DESIGN:
  The tool schema exposed to Claude stays a single tool wrapping /recommendation — CARRIED
  OVER principle from the prior build — but its parameters now include the `constraints`
  object (exclude_vessel, max_completion_day, etc.), since DOC 2 §3c's core new chatbot
  capability is turning "what if I can't use a Capesize, and I need this done in 12 days"
  into exactly that structured object, not just re-stating the original 4 fields.

  Conversation flow (per DOC 2 §3c):
    1. Chatbot resolves references using conversation_history (already has prior
       cargo_request, doesn't ask the manager to restate it).
    2. Maps the new sentence to a HumanOverrides-shaped constraints object.
    3. Calls the same /recommendation the dashboard calls, original cargo_request +
       new constraints — a genuine re-solve, not a filter on the old plan.
    4. Replies in plain language AND emits a dashboard_update event so the open dashboard
       re-renders with the new plan + a "changed because you asked: ..." annotation.

  dashboard_update mechanism: given both chatbot and dashboard now live in the same React
  app (ChatPanel + RecommendationPage as siblings under App.tsx), this can be a shared
  state update (context/store) rather than needing a websocket/SSE push — simpler than
  DOC 2's language might imply, since the prior build's separate-Streamlit-tabs assumption
  no longer applies. `[ASSUMPTION: implemented as shared React state, not a server push,
  since both surfaces are already in the same client — confirm this reading of §2c holds.]`

INTERFACES & CONTRACTS:
  Same Strategy/ForecastObject shapes as everywhere else — zero new data types, per DOC 2
  §5.9's explicit statement that the chatbot introduces no new schema, only a new way of
  collecting inputs (free text + structured constraints, instead of a form).

ERROR HANDLING STRATEGY:
  Claude API failure (network/auth/rate limit) -> chat-bubble error, rest of the app
  (RecommendationPage) remains fully functional — CARRIED OVER principle.

EDGE CASES TO HANDLE:
  - Free-text message missing a required field -> Claude asks a follow-up rather than
    guessing a default (system prompt instruction, same as prior build)
  - User's natural-language constraint doesn't map cleanly to any HumanOverrides field
    (e.g. a request outside the MVP's decision scope) -> Claude should say so explicitly
    rather than silently dropping it or forcing an approximate mapping

PERFORMANCE CONSIDERATIONS:
  Each turn: one Claude API round-trip + one /recommendation call, now solver-bound
  (MILP_SOLVE_TIMEOUT_SECONDS) rather than near-instant — chat UI needs a visible
  "thinking" state during the tool call, more noticeable here than in the prior build.

TESTING PLAN:
  None automated — manual check before demo: run the exact example queries from DOC 2
  §5.9's table (basic recommendation, multi-voyage/contract strategy, forecast query,
  scenario analysis, port compatibility, driver/explanation, simple follow-ups) and
  confirm every number traces back to an actual tool-call result, plus specifically test
  §2c's mid-conversation constraint-change flow end to end.
```

---

## 4. Cross-cutting: Deployment & environment

**Decision: Render for the entire backend (Web Service + Background Worker + Cron Job +
managed Postgres, one project, one `render.yaml` blueprint), Vercel for the React
static build.**

Why this pairing over the alternatives, specifically for a 1-week vibecoding build:

- **All three backend process shapes exist as first-class Render service types, in one
  project/dashboard.** The FastAPI app is a **Web Service**, the AIS listener is a
  **Background Worker** (Render's own docs describe this type as exactly "processes that
  run continuously and don't receive incoming traffic" — the AIS listener to the letter),
  and the weekly retrain + batch ingestion jobs are **Cron Jobs**, which Render runs on
  isolated compute decoupled from the web service's traffic, guarantees at-most-one
  concurrent run for, and lets you trigger manually from the dashboard for testing
  without waiting for the schedule — useful mid-build when you want to verify a retrain
  works before trusting the weekly clock.
- **One `render.yaml` blueprint can declare all four backend resources** (web, worker,
  cron, Postgres) as code in the repo, so an AI coding agent can generate and version the
  infra config directly rather than a human clicking through dashboard setup — this
  matters more for a vibecoding week than for a normal project.
- **It's the smallest possible delta from the prior build's existing familiarity** —
  the old DOC 3 already chose Render for the API; this extends that choice rather than
  introducing a second unfamiliar platform (Railway/Fly.io) for backend hosting on top of
  the frontend already having to move to a new tool (Streamlit Cloud -> Vercel).
- **Managed Postgres is one click away in the same project**, with a documented,
  broad extension list. `[ASSUMPTION: TimescaleDB specifically should be confirmed
  available for your chosen Postgres version at setup time — Render's extension support
  varies by Postgres version. This is non-blocking either way: DOC 2 §20 already treats
  TimescaleDB as an optional upgrade ("added once live ingestion runs across many
  routes"), so plain Postgres works for the full build regardless of the outcome.]`
- **Vercel for the React frontend** is close to zero-config for a Vite + React app,
  free-tier friendly, and git-push deploys — there's no reason to add a second
  general-purpose host when a frontend-specific one this simple exists.

```
render.yaml services (one blueprint, one repo):
  - type: web        name: api               -> backend/api/main.py (uvicorn)
  - type: worker      name: ais-listener      -> backend/ingestion/ais_listener.py
  - type: cron         name: retrain-and-ingest -> backend/ingestion/scheduler.py,
                                                     RETRAIN_SCHEDULE_CRON
  - type: pserv/postgres name: freight-db     -> managed Postgres, TimescaleDB enabled
                                                     if available for the chosen version

Frontend (separate Vercel project, same repo, /frontend subdirectory):
  VITE_API_BASE_URL -> points at the Render web service's public URL

Chat backend -> the small server-side /chat route (see Chatbot §3 above) lives inside
                the same FastAPI Web Service — no separate deploy target needed, it's
                just another route holding ANTHROPIC_API_KEY server-side.
```

Env vars -> `DATABASE_URL`, `AISSTREAM_API_KEY`, `ANTHROPIC_API_KEY` (Render web service
            only — never shipped to the Vercel/React build), `VITE_API_BASE_URL` (Vercel),
            `RETRAIN_SCHEDULE_CRON` (Render cron job).

---

## 5. Assumptions flagged in this document

- `[ASSUMPTION]` MILP solver = PuLP+CBC as the concrete choice, with OR-Tools CP-SAT as a documented drop-in alternative behind the same `decision.solve()` interface.
- `[ASSUMPTION]` Provenance implemented as a shared enum + optional note field per DOC 2's requirement, not a separate service.
- `[ASSUMPTION]` Chatbot's server-side key-holding role implemented as a small FastAPI `/chat` route, since a React SPA has no equivalent of the prior build's Streamlit-process trust boundary.
- `[ASSUMPTION]` `dashboard_update` implemented as shared client-side React state (chatbot and dashboard are siblings in one app) rather than a server push — worth confirming this reading of DOC 2 §3c is what's intended.
- `[ASSUMPTION]` TimescaleDB extension availability on Render should be confirmed at setup time for your chosen Postgres version — non-blocking, plain Postgres works for the full build either way (see §4).
- `[ASSUMPTION]` `PORT_HANDLING_DAY_RATE_USD`, `WAITING_COST_PER_DAY_USD`, and `TAX_RATE_PCT` are round placeholders (§2), tagged "assumed" via the provenance system — per DOC 2 §12's mock-data policy, these still need sourcing/defending separately, same status as `commitment_benchmark`. Bunker cost is no longer on this list — it's now real distance-based physics (DOC 2 Addendum v3 §A2).
- `[ASSUMPTION]` `DEFAULT_COMMITMENT_BENCHMARK_PCT = 10.0` — unchanged placeholder from the prior build, still explicitly UNVERIFIED, still needs sourcing independent of anything in this document (DOC 2 §11.8/§20).

**Deployment is no longer an open assumption** — decided in §4 (Render backend trio + Vercel frontend).

---

**Ready for a DOC 4 (Vibecoding Build Guide).** Build order, dependency-driven and
matching the section numbering above: ingestion + warehouse first (nothing else has real
data without them) -> forecasting -> constraint (carried over, fast to verify) ->
scenario generator -> cost terms (reinvented, testable in isolation, must exist before
the MILP can build its objective) -> decision engine/MILP (the highest-uncertainty,
highest-effort piece, and now the true load-bearing centerpiece of the system) ->
provenance -> API -> dashboard core form -> dashboard §5.10 sellable layer -> chatbot
last, since it's a thin wrapper over everything before it -> deployment (render.yaml +
Vercel project) wired up incrementally as each piece becomes demoable, not saved entirely
for the end.
