# DOC 4 — Vibecoding Build Guide
### Intelligent Freight Forecasting & Chartering — Full Build

Synthesizes DOC 2 (system architecture) and DOC 3 v2 (module architecture) into an
ordered, executable build sequence. Written for both you and an AI coding agent to
follow directly.

---

## 4.0 — Project Context Snapshot

Copy-paste this block as the system prompt / context block at the start of any coding
session on this project.

```
PROJECT: Intelligent Freight Forecasting & Chartering (SAIL PS3)
TAGLINE: Jointly solves rate forecasting, port/vessel feasibility, and spot-vs-locked
         chartering strategy — instead of treating them as three separate tools.

WHAT WE'RE BUILDING:
  A system that takes a cargo request (quantity, origin, discharge ports, timing
  flexibility) and returns a ranked chartering strategy — how many voyages, which vessel
  and port each uses, when each is fixed, and spot vs. locked commitment mix — solved
  jointly via a MILP optimizer against forecast uncertainty, not picked from a fixed
  shortlist. Full pipeline built in one pass: data ingestion, forecasting, feasibility,
  MILP decision engine, React dashboard, and a tool-calling chatbot.

STACK:
  Backend:     FastAPI (Python), PuLP + CBC for the MILP solve
  Database:    PostgreSQL (TimescaleDB extension if available on the chosen host/version)
  Ingestion:   Scheduled batch ETL (BDI, bunker, port constraints, fleet/demand) +
               persistent AIS WebSocket listener
  Frontend:    React + Recharts (Vite + TypeScript)
  Chatbot:     Anthropic Claude API, tool-calling, server-side key
  Deployment:  Render (Web Service + Background Worker + Cron Job + managed Postgres,
               one render.yaml blueprint) for backend; Vercel for the React frontend

ARCHITECTURE IN ONE LINE:
  React dashboard + chatbot → FastAPI → {Constraint engine, Scenario Generator, MILP
  Decision Engine} reading from a Postgres warehouse that ingestion (scheduled batch +
  live AIS) and a weekly-retrained Forecasting engine keep populated.

CORE PRINCIPLES TO FOLLOW:
  - `engine/` never imports from `api/`, `ingestion/`, or `frontend/` — engine code only
    talks to the warehouse through `warehouse/repository.py`.
  - `api/routes/*.py` are thin pass-throughs — parse request, call one engine function,
    shape response. No business logic in a route handler.
  - `frontend/` never talks to the backend except through `src/lib/apiClient.ts`.
  - Every number the API returns carries a `provenance` tag (measured / modeled /
    assumed) — set where the number originates, never bolted on in the frontend.
  - The MILP's decision variables stay decomposed (q_i, x_iv, y_ip, z_iτ, w_im, ℓ_ip) —
    never fold them into one joint index; that's the combinatorial blowup DOC 2 §5.6
    explicitly designed around.
  - Cost coefficients (`engine/cost_terms.py`) are pure functions, precomputed before the
    solve — the MILP objective must stay linear.
  - Human overrides (`exclude_vessel`, `max_completion_day`, etc.) are expressed by
    fixing MILP variables before solving, never as a separate filter applied after.
  - `engine/constraint.py` (Rules 1–8) is carried over from the prior build and correct
    as-is — extend, don't rewrite.

MVP FEATURES / BUILD ORDER:
  1. Data Ingestion Layer           8. Decision Engine (MILP Optimizer)
  2. AIS Listener & Congestion      9. Provenance & Explainability Layer
  3. Data Warehouse                10. API Layer
  4. Forecasting Engine             11. Dashboard — core form
  5. Constraint / Feasibility       12. Dashboard — §5.10 sellable layer
  6. Scenario Generator             13. Chatbot
  7. Cost Terms Module              14. Deployment (Render + Vercel)
```

---

## 4.1 — Build Sequence

### BUILD STEP 1: Data Ingestion Layer
```
Reference:    DOC 3 → FEATURE: Data Ingestion Layer
              DOC 2 → §5.1, §6.1

What to build:
  batch/bdi_ingest.py, batch/bunker_ingest.py, batch/port_constraint_ingest.py,
  batch/fleet_demand_ingest.py — each exposes run() -> IngestResult. validation.py
  implementing the four checks (schema/type, freshness, gap-fill, plausibility).
  port_constraint_ingest.py writes new/changed values to a pending_verification table,
  not directly to the active table. No scheduler wiring yet, no warehouse writes beyond
  a stub — this step is "can we correctly parse and validate each source."

Folder/file targets:
  /backend/ingestion/batch/*.py, /backend/ingestion/validation.py

Agent prompt hint:
  "Implement the four ingestion sources and validation.py exactly per DOC 3's Data
  Ingestion Layer section. Each batch module exposes only run() -> IngestResult. Do not
  wire the scheduler or warehouse writes yet — that's Build Steps 2/3. Use fixture CSVs/
  sample PDFs for now if live sources aren't available."

Done when:
  Each batch/*.py's run() correctly parses a sample of its source, validation.py's four
  checks pass unit tests against known-good and known-bad fixture rows, and a malformed
  row is rejected with a logged reason rather than silently dropped or crashing the run.

Common drift to watch for:
  Agent wires ingestion straight to Postgres before Build Step 3 exists — keep this step
  scoped to parse+validate only, return the ValidatedBatch, don't reach for a DB
  connection yet.
```

### BUILD STEP 2: AIS Listener & Congestion Module
```
Reference:    DOC 3 → FEATURE: AIS Listener & Congestion Module
              DOC 2 → §5.4, §9 (AIS feed can drop)

What to build:
  ais_listener.py as its own long-lived process — connect(), on_message(), reconnect
  with exponential backoff. congestion.py's read path (get_congestion_snapshot) with the
  staleness check and seeded-fallback path. Can run against a stub/mock AIS feed until
  Build Step 3's warehouse write path exists.

Folder/file targets:
  /backend/ingestion/ais_listener.py, /backend/engine/congestion.py

Agent prompt hint:
  "Build ais_listener.py as an independent process, not a FastAPI route — it must run
  standalone via `python -m backend.ingestion.ais_listener`. congestion.py's read path
  must degrade gracefully (is_live=False, source_note explaining why) if the listener
  has never run or its data is stale — never a 500."

Done when:
  Listener connects to a mock/sandboxed AIS feed, reconnects automatically after a forced
  disconnect, and congestion.py's get_congestion_snapshot() returns a correctly-labelled
  fallback when no listener data exists yet.

Common drift to watch for:
  Agent tries to fold the listener into the FastAPI app as a background task decorator —
  resist; DOC 2 §7 and DOC 3 both require this as a separate persistent process so an AIS
  hiccup can never affect API request latency or uptime.
```

### BUILD STEP 3: Data Warehouse
```
Reference:    DOC 3 → FEATURE: Data Warehouse
              DOC 2 → §5.2

What to build:
  SQLAlchemy models (RateHistory, PortConstraint, VesselSpec, ForecastObject,
  CongestionSnapshot), db.py engine/session setup, initial alembic migration,
  repository.py's typed query functions. Wire Build Steps 1 and 2's outputs to actually
  write here now.

Folder/file targets:
  /backend/warehouse/models.py, db.py, migrations/, repository.py

Agent prompt hint:
  "Implement the warehouse layer per DOC 3's schema. repository.py is the ONLY module
  anywhere in the codebase allowed to construct a SQLAlchemy query — every other module
  calls a typed function from here. Index ForecastObject on
  (route, vessel_class, horizon_days, generated_at DESC)."

Done when:
  A full round trip works: batch ingestion writes validated rows, the AIS listener writes
  a congestion snapshot, and repository.py's read functions return them correctly typed.
  Migrations apply cleanly to a fresh local Postgres instance.

Common drift to watch for:
  Agent starts writing raw SQL or ad-hoc queries inside engine/ or api/ "just this once"
  — enforce the repository-only rule immediately, it's much cheaper to catch here than
  after the MILP layer depends on a dozen scattered queries.
```

### BUILD STEP 4: Forecasting Engine
```
Reference:    DOC 3 → FEATURE: Forecasting Engine
              DOC 2 → §5.3, §6.2

What to build:
  train_and_evaluate() (Naive/ARIMA/XGBoost/Prophet, walk-forward validation, the
  naive-baseline gate, ablation), ConditionsMonitor, damped_trend(), and get_forecast()
  as the sole read entrypoint. Not wired to the scheduler yet — call train_and_evaluate()
  manually/from a script for now.

Folder/file targets:
  /backend/engine/forecasting.py

Agent prompt hint:
  "Implement forecasting.py per DOC 3. train_and_evaluate() is a script-callable
  function, not yet scheduled. get_forecast() must raise ForecastUnavailableError, not
  return None or a default, when no gated ForecastObject exists for a pair. Conditions
  monitor runs on every get_forecast() call against live warehouse data, independent of
  when the stored forecast was generated."

Done when:
  train_and_evaluate() run against sample rate_history data produces gated ForecastObjects
  for at least one route × vessel-class pair, correctly falls back to ARIMA/naive below
  MIN_OBSERVATIONS_FOR_XGBOOST, and get_forecast() correctly switches to damped_trend when
  ConditionsMonitor trips on injected out-of-range test data.

Common drift to watch for:
  Agent trains models at FastAPI startup out of habit from the prior build — this is the
  one explicitly reversed decision (DOC 3 §0); keep training scheduler-invoked only.
```

### BUILD STEP 5: Constraint / Feasibility Engine
```
Reference:    DOC 3 → FEATURE: Constraint / Feasibility Engine (CARRIED OVER)
              DOC 2 → §5.5

What to build:
  If migrating an existing constraint.py: copy it in, extend DEST_PORTS to 4 ports
  (Vizag added), add the tidal_window_note field usage note, re-run the existing test
  file unmodified to confirm the carry-over is clean. If building fresh: implement Rules
  1–8 exactly per DOC 3's carried-over spec.

Folder/file targets:
  /backend/engine/constraint.py, /backend/tests/test_constraint_rules.py

Agent prompt hint:
  "This module is specified in full in DOC 3 as carried over from a prior build — do not
  re-derive the rules from DOC 2's prose from scratch. Implement exactly the 8 rules and
  the FeasibleOption shape as described, including Rule 4's 'inefficient fit' soft flag
  and Rule 7's lightening lookup."

Done when:
  test_constraint_rules.py passes, including the boundary cases (draft exactly at limit
  passes, one cm over fails) and both lightening branches (eligible deeper port
  available / none available).

Common drift to watch for:
  This is the fastest step in the whole sequence if scoped correctly — watch for an agent
  "improving" the rule set or adding unrequested soft-constraint scoring, which isn't in
  DOC 2 §5.5 and adds surface area to the one module that should be the most stable.
```

### BUILD STEP 6: Scenario Generator
```
Reference:    DOC 3 → FEATURE: Scenario Generator
              DOC 2 → §5.6 Step A

What to build:
  generate_scenarios(forecast) -> ScenarioPaths — Base/Optimistic/Pessimistic paths
  from a ForecastObject's trajectory + confidence band.

Folder/file targets:
  /backend/engine/scenario.py

Agent prompt hint:
  "Pure function per DOC 3 — no I/O. Confirm the Optimistic/Pessimistic direction is
  correct for a cost the requester pays (lower rate = favorable) and make that
  directionality an explicit named constant, not an inferred sign."

Done when:
  Unit tests confirm hand-calculated Optimistic/Pessimistic values against a known
  ForecastObject and confidence_band, including the degenerate zero-width-band case.

Common drift to watch for:
  None significant — this is a small, low-risk step. Move quickly.
```

### BUILD STEP 7: Cost Terms Module
```
Reference:    DOC 3 → FEATURE: Cost Terms Module (REINVENTED)
              DOC 2 → §5.6 (C_s definition)

What to build:
  spot_freight_cost, locked_freight_cost, bunker_cost, port_handling_cost, waiting_cost,
  tax_cost, lightening_penalty_cost, and build_cost_coefficient() orchestrating all of
  them into a CostBreakdown. Add the new constants (BUNKER_CONSUMPTION_TONNES_PER_DAY,
  PORT_HANDLING_DAY_RATE_USD, WAITING_COST_PER_DAY_USD, TAX_RATE_PCT) to constants.py.

Folder/file targets:
  /backend/engine/cost_terms.py, /backend/tests/test_cost_terms.py,
  /backend/config/constants.py (additions)

Agent prompt hint:
  "Implement cost_terms.py exactly per DOC 3's Cost Terms Module section — this replaces
  a prior build's pricing formulas, it is not extending them. Pay specific attention to
  locked_freight_cost: it must be computed from the Base scenario's rate regardless of
  which scenario s the caller is evaluating C_s for, and must be IDENTICAL across all
  three scenario evaluations for the same voyage. Write the test that asserts this
  before moving on."

Done when:
  test_cost_terms.py passes, INCLUDING the critical test asserting a locked voyage's
  cost is identical across Base/Optimistic/Pessimistic evaluations, and the 5-bucket
  breakdown sums to the same total as its parts summed independently.

Common drift to watch for:
  Agent varies locked-mode cost by scenario "for consistency" with spot pricing — this is
  the single highest-value bug to catch at this step, per DOC 3's explicit callout. Also
  watch for tax/waiting terms getting silently folded into the freight bucket instead of
  staying separately tagged "assumed" line items.
```

### BUILD STEP 8: Decision Engine (MILP Optimizer)
```
Reference:    DOC 3 → FEATURE: Decision Engine (MILP Optimizer)
              DOC 2 → §5.6 (full section — re-read before starting this step)

What to build:
  solve() and its helpers: _build_variables (decomposed q_i/x/y/z/w/ℓ), _build_constraints
  (cargo conservation, capacity, one-assignment, feasibility linking to constraint.py's
  output, lightening consistency, timing, human-override variable-fixing),
  _objective_min_max_cost (calling cost_terms.build_cost_coefficient per candidate),
  _solve_cbc with MILP_SOLVE_TIMEOUT_SECONDS, and _hybrid_fallback enumeration for
  timeout/failure. This is the highest-effort step in the sequence — budget accordingly,
  and don't let it slip into a second pass at the cost terms module instead.

Folder/file targets:
  /backend/engine/decision.py, /backend/tests/test_decision_engine_milp.py

Agent prompt hint:
  "Implement decision.py per DOC 3. Keep decision variables decomposed exactly as
  specified — do not fold vessel/port/time/mode into one joint index for 'simplicity,'
  that reintroduces the combinatorial blowup this design exists to avoid. Human overrides
  (constraints parameter) must be implemented as variable-fixing before the solve, not as
  a post-hoc filter or a parallel set of override binaries. If the CBC solve exceeds
  MILP_SOLVE_TIMEOUT_SECONDS, fall back to hybrid enumeration and set solved_via
  accordingly — never let a slow solve produce no response at all."

Done when:
  test_decision_engine_milp.py passes: feasibility-linking correctly excludes infeasible
  (v,p) pairs from the variable domain; the objective matches hand-calculated C_s for a
  small fixture; each HumanOverrides field correctly shrinks the feasible region without
  altering the objective; and forcing a timeout (mocked) correctly triggers
  _hybrid_fallback and still returns a valid scenario_comparison[].

Common drift to watch for:
  This step has the highest AI-agent risk in the whole build. Watch for: (a) the agent
  quietly reverting to a brute-force enumeration because it's "simpler to get working"
  and calling it done — check solved_via is actually "milp" in normal-path tests, not
  always "hybrid_fallback"; (b) re-deriving Constraint engine feasibility logic inside
  decision.py instead of calling constraint.check_feasibility(); (c) skipping the
  event-based time-point calculation and using a uniform daily grid instead, which
  quietly reintroduces the binary-count blowup DOC 2 §5.6 designed around.
```

### BUILD STEP 9: Provenance & Explainability Layer
```
Reference:    DOC 3 → FEATURE: Provenance & Explainability Layer
              DOC 2 → §5.10 (baseline panels)

What to build:
  provenance.py's Provenance type and tagging helpers. Thread `provenance` fields through
  ForecastObject (forecasting.py), CostBreakdown (cost_terms.py), and Strategy
  (decision.py) at their point of origin. compute_sensitivity() inside decision.py,
  reusing already-computed C_s terms — not a new solve per sensitivity bar.

Folder/file targets:
  /backend/engine/provenance.py; additive field changes to forecasting.py, cost_terms.py,
  decision.py's output types

Agent prompt hint:
  "Add provenance tagging at the point each value originates, per DOC 3. Do not add a
  separate provenance-computation pass over already-built responses — set the tag when
  the value is created. compute_sensitivity() must reuse decision.py's already-cached
  per-scenario cost terms from the same solve, not re-run the MILP."

Done when:
  Every ForecastObject, CostBreakdown, and Strategy returned by the engine layer carries
  a correctly-set provenance field (forecasts = modeled, commitment_benchmark-driven
  terms = assumed with a note, measured ingested values = measured), and
  compute_sensitivity() runs against a completed solve() result without triggering a
  second solve.

Common drift to watch for:
  Agent implements this as a frontend-only display concept, defeating the point — it must
  originate in the backend response, checked at this step, before Build Step 11 assumes
  it's already there.
```

### BUILD STEP 10: API Layer
```
Reference:    DOC 3 → FEATURE: API Layer
              DOC 2 → §5.7

What to build:
  main.py (app, CORS, /health reporting warehouse/listener/retrain status), all six
  routes as thin pass-throughs, schemas.py's request/response contracts including the new
  `constraints` object and its allow-list validation against ORIGINS/DEST_PORTS/
  VESSEL_CLASSES.

Folder/file targets:
  /backend/api/main.py, /backend/api/routes/*.py, /backend/api/schemas.py

Agent prompt hint:
  "Routes call exactly one engine function each and shape the response — no business
  logic in a route handler. Validate `constraints` fields against the same allow-lists as
  the core request fields before reaching decision.py, so a typo in exclude_vessel
  produces a clear 422, not a confusing empty-recommendation response."

Done when:
  All six endpoints work via the FastAPI /docs Swagger UI against real engine calls;
  /health correctly reports warehouse_reachable, models_loaded, last_retrain_at, and
  ais_listener_last_seen; an invalid constraints field returns 422 with a message naming
  the allowed set.

Common drift to watch for:
  Agent starts putting cost/feasibility logic directly in route handlers "just to glue
  things together faster" — this is the layer-violation anti-pattern most likely to show
  up here; redirect to the engine layer immediately if it appears.
```

### BUILD STEP 11: Dashboard — core form
```
Reference:    DOC 3 → FEATURE: Dashboard (React + Recharts) — form, StrategyTable,
              ForecastChart, ProvenanceBadge, apiClient.ts
              DOC 2 → §5.8

What to build:
  apiClient.ts, RecommendationPage.tsx with the 4-field form + collapsed
  commitment_benchmark control (exact DOC 2 §5.8 label text), StrategyTable.tsx,
  ForecastChart.tsx, ProvenanceBadge.tsx. NOT yet: WhatIfSliders, ScenarioFanChart,
  AISRouteMap, WhyNotComparator, ExecutiveBriefExport — those are Build Step 12.

Folder/file targets:
  /frontend/src/lib/apiClient.ts, pages/RecommendationPage.tsx,
  components/{StrategyTable,ForecastChart,ProvenanceBadge}.tsx

Agent prompt hint:
  "Build only the core 4-field form → submit → StrategyTable/ForecastChart render flow.
  Do not add the sliders, fan chart, map, or export button yet — those are a separate
  build step. RecommendationPage does no cost math itself, purely orchestrates state and
  renders children."

Done when:
  Submitting the form against a running backend renders a ranked StrategyTable and
  ForecastChart with correctly-displayed ProvenanceBadges; a backend-unreachable state on
  load shows a clean error, not a blank screen or unhandled exception.

Common drift to watch for:
  Agent jumps ahead to Build Step 12's polish features because they're visually
  satisfying — hold the line at "form works end to end" before adding anything else.
```

### BUILD STEP 12: Dashboard — §5.10 sellable layer
```
Reference:    DOC 3 → FEATURE: Dashboard — WhatIfSliders, ScenarioFanChart, AISRouteMap,
              SensitivityPanel, RobustnessReadout, WhyNotComparator, ExecutiveBriefExport
              DOC 2 → §5.10 items 1–5

What to build:
  In priority order (per DOC 2's own framing of WhatIfSliders as "the single most
  demo-persuasive feature"): WhatIfSliders.tsx (debounced ~400ms, cancels stale in-flight
  requests), ScenarioFanChart.tsx, SensitivityPanel.tsx + RobustnessReadout.tsx (reusing
  Build Step 9's compute_sensitivity endpoint data), AISRouteMap.tsx, WhyNotComparator.tsx,
  ExecutiveBriefExport.tsx.

Folder/file targets:
  /frontend/src/components/{WhatIfSliders,ScenarioFanChart,SensitivityPanel,
  RobustnessReadout,AISRouteMap,WhyNotComparator,ExecutiveBriefExport}.tsx

Agent prompt hint:
  "Build WhatIfSliders first and get it fully working (correct debounce, correct
  cancellation of stale requests) before starting the next component in this step — it's
  explicitly the highest-value single feature per DOC 2 §5.10. Each of the remaining five
  is a pure re-render of data the backend already returns — no new backend calls beyond
  what Build Steps 9–10 already expose."

Done when:
  Dragging a WhatIfSlider triggers a debounced re-solve and the UI updates without a full
  page reload or a stale-result race; each of the other five components renders correctly
  against a real recommendation_response.

Common drift to watch for:
  Agent treats one of these five as needing new backend compute — check against DOC 2's
  explicit claim that none of them need a new solve, new data source, or optimizer
  change; if an agent proposes backend work here, that's a signal something upstream was
  under-built, not that this step needs to grow.
```

### BUILD STEP 13: Chatbot
```
Reference:    DOC 3 → FEATURE: Chatbot
              DOC 2 → §5.9, §2b, §2c

What to build:
  Server-side /chat route (FastAPI, holds ANTHROPIC_API_KEY) proxying the Claude
  tool-calling loop, with the single get_recommendation tool now accepting the
  constraints object. ChatPanel.tsx in React, conversation_history in shared client
  state, and the dashboard_update mechanism (shared React state between ChatPanel and
  RecommendationPage, per DOC 3's assumption).

Folder/file targets:
  /backend/api/routes/chat.py (or similar), /frontend/src/chat/ChatPanel.tsx

Agent prompt hint:
  "The tool wrapper must call the exact same /recommendation logic the dashboard form
  uses — no second code path that could produce a different answer for the same inputs.
  System prompt must instruct: never state a number not returned by a tool call, and ask
  a follow-up rather than guessing a default for a missing field."

Done when:
  Each of DOC 2 §5.9's seven example query types works correctly and traces every number
  in the reply to an actual tool result; §2c's mid-conversation constraint-change flow
  (e.g. "what if I can't use a Capesize and need this in 12 days") triggers a genuine
  re-solve and updates the open dashboard view with a "changed because you asked" note,
  not just a chat reply.

Common drift to watch for:
  Agent lets the chatbot compute or estimate a number itself when a tool call is slow or
  ambiguous — this is exactly what DOC 2 §5.9/§9 flags as the risk to guard against; the
  chatbot must be strictly a wrapper.
```

### BUILD STEP 14: Deployment (Render + Vercel)
```
Reference:    DOC 3 → §4 Cross-cutting: Deployment & environment
              DOC 2 → §7 (tech stack, backend implicit in FastAPI/Postgres choices)

What to build:
  render.yaml declaring the four backend resources (web, worker, cron, Postgres), a
  Vercel project pointed at /frontend, environment variables wired per DOC 3 §4.

Folder/file targets:
  /render.yaml, Vercel project config (dashboard-side, or vercel.json if needed)

Agent prompt hint:
  "Write render.yaml exactly per DOC 3 §4's four-resource layout. Confirm TimescaleDB
  extension availability for the chosen Postgres version at this point — non-blocking if
  unavailable, per DOC 3's note, just proceed on plain Postgres."

Done when:
  A push to the connected branch deploys all four Render resources and the Vercel
  frontend without manual dashboard steps; /health returns 200 from the public Render
  URL; the deployed frontend successfully calls the deployed backend end to end.

Common drift to watch for:
  ANTHROPIC_API_KEY accidentally exposed to the Vercel/frontend build — it belongs only
  on the Render web service's /chat route. Double-check no VITE_-prefixed env var carries
  a secret (Vite exposes VITE_* vars to the client bundle by design).
```

---

## 4.2 — Agentic Coding Rules

```
ALWAYS:
  [ ] Route all warehouse access through /backend/warehouse/repository.py — no raw SQL
      or SQLAlchemy queries anywhere else in the codebase.
  [ ] Keep MILP decision variables decomposed (q_i, x_iv, y_ip, z_iτ, w_im, ℓ_ip) per
      DOC 2 §5.6 — never fold them into a single joint index.
  [ ] Express human-override constraints (exclude_vessel, max_completion_day, etc.) as
      MILP variable-fixing inside decision.py, never as a post-hoc filter.
  [ ] Set `provenance` on a value at the point it originates (forecasting.py,
      cost_terms.py, congestion.py) — never compute it later from the outside.
  [ ] Call constraint.check_feasibility() from decision.py for feasibility — never
      re-derive draft/LOA/beam/lightening logic anywhere else.
  [ ] Reuse cost_terms.build_cost_coefficient() for every MILP objective term — never
      hand-roll a cost calculation inline inside decision.py.
  [ ] Keep locked-voyage cost terms identical across Base/Optimistic/Pessimistic
      evaluations of the same voyage (see Build Step 7).
  [ ] Route every frontend→backend call through /frontend/src/lib/apiClient.ts.
  [ ] Type every request/response boundary — pydantic on the backend, TypeScript
      interfaces mirroring those schemas on the frontend.

NEVER:
  [ ] Never call engine/ functions from api/routes/*.py's request-parsing code without
      going through the typed schema validation first.
  [ ] Never train or retrain forecasting models inside a FastAPI request path or startup
      hook — only from the scheduled entrypoint (ingestion/scheduler.py).
  [ ] Never let the AIS listener's failure modes propagate into /recommendation's request
      path — congestion.py's staleness/fallback handling is mandatory, not optional.
  [ ] Never bypass the Constraint engine or Decision Engine from the chatbot — it must
      call the same /recommendation logic the dashboard uses, no second code path.
  [ ] Never expose ANTHROPIC_API_KEY, DATABASE_URL, or AISSTREAM_API_KEY to the
      React/Vercel build — secrets live only in the Render web service.
  [ ] Never revert to a uniform daily/weekly time grid in the MILP — event-based time
      points (today, week-ends within flexibility, flexibility-window end, trajectory
      local minima) are load-bearing for keeping the solve inside its timeout.

IF THE AGENT GOES OFF-TRACK:
  If the agent starts building a feature from a later build step while still on an
  earlier one (e.g. adding WhatIfSliders during Build Step 11), say: "Stop. We are only
  doing Build Step [N]. Finish [Done When condition] before anything else." If the agent
  proposes a design that contradicts a decision already locked in DOC 2 or DOC 3 §0
  (e.g. training at startup, a joint MILP index, Streamlit instead of React), point at
  the specific decision row and ask it to explain why it's deviating before proceeding —
  don't let a plausible-sounding rationale silently override an already-made decision.
```

---

## 4.3 — Integration Checkpoints

```
CHECKPOINT 1: After Build Steps 1–3 (Ingestion, AIS, Warehouse)
  What to verify: Real or fixture data flows from source → validation → Postgres, for
                   both batch sources and the AIS listener.
  How to test it: Run each batch ingest script manually, run the AIS listener against a
                   mock feed, then query repository.py's read functions directly and
                   confirm the rows match what was ingested.
  If it breaks:   Check validation.py's rejection logs first — a silently-rejected row
                   looks identical to "nothing ingested" without checking there.

CHECKPOINT 2: After Build Steps 4–5 (Forecasting, Constraint)
  What to verify: For one real route × vessel-class pair, get_forecast() returns a gated
                   ForecastObject and check_feasibility() returns a correct
                   FeasibleOption for a known cargo_quantity/port combination.
  How to test it: Manually run train_and_evaluate() for that one pair, then call
                   get_forecast() and check_feasibility() directly in a script.
  If it breaks:   If get_forecast() raises ForecastUnavailableError, check the walk-
                   forward gate — the model may be failing to beat the naive baseline,
                   which is a valid (if inconvenient) outcome, not necessarily a bug.

CHECKPOINT 3: After Build Steps 6–8 (Scenario, Cost Terms, Decision Engine)
  What to verify: decision.solve() returns a valid Strategy + scenario_comparison[] for
                   a real multi-voyage query, via CBC (not the fallback) under normal
                   conditions.
  How to test it: Call solve() directly with a real cargo_quantity/origin/discharge_ports
                   combination that Checkpoint 2 confirmed has data; inspect solved_via
                   (should be "milp"), the 5-bucket cost breakdown, and confirm locked-
                   voyage costs match across scenarios per Build Step 7's test.
  If it breaks:   If solve() always falls back to hybrid enumeration, check
                   MILP_SOLVE_TIMEOUT_SECONDS and the variable/constraint counts first —
                   a joint-index regression (see Agentic Coding Rules) is the most likely
                   cause of an unexpectedly slow solve.

CHECKPOINT 4: After Build Steps 9–10 (Provenance, API)
  What to verify: A full HTTP round trip through /recommendation returns the complete
                   contract (Strategy with provenance tags, scenario_comparison[],
                   5-bucket breakdown) matching DOC 3's schemas exactly.
  How to test it: Hit /recommendation via the FastAPI Swagger UI with a real payload;
                   confirm every field DOC 3's API Layer section lists is present and
                   correctly typed in the response.
  If it breaks:   Compare the actual response against schemas.py field-by-field — a
                   missing provenance field usually means Build Step 9's tagging wasn't
                   threaded all the way through decision.py's output construction.

CHECKPOINT 5: After Build Step 11 (Dashboard core)
  What to verify: The full user-facing loop — fill form, submit, see ranked strategies
                   and forecast chart — works end to end against the real (not mocked)
                   backend.
  How to test it: Run both frontend and backend locally, complete one full form
                   submission, confirm the render matches the API response.
  If it breaks:   Check apiClient.ts's fetch wrapper and CORS config in main.py first —
                   this is the first point where frontend and backend run as genuinely
                   separate origins.

CHECKPOINT 6: After Build Step 12 (Dashboard sellable layer)
  What to verify: WhatIfSliders' debounce actually cancels stale in-flight requests, not
                   just delays firing new ones.
  How to test it: Drag a slider rapidly through several values in under a second, confirm
                   the final rendered result matches the LAST value, not an
                   earlier-fired, later-arriving response.
  If it breaks:   This is a race condition, not a logic bug — look for a missing abort
                   controller / request-ID check in apiClient.ts or WhatIfSliders.tsx.

CHECKPOINT 7: After Build Step 13 (Chatbot)
  What to verify: DOC 2 §2c's mid-conversation constraint-change flow works exactly as
                   specified — a follow-up message re-solves and updates the open
                   dashboard, not just the chat reply.
  How to test it: Get a recommendation via the dashboard form, then in the chat panel
                   (same session) ask a constraint-changing follow-up, confirm
                   RecommendationPage's rendered plan updates with the "changed because
                   you asked" annotation.
  If it breaks:   Check the shared React state wiring between ChatPanel and
                   RecommendationPage first — this is the one piece of DOC 3 flagged as
                   an unconfirmed assumption about how dashboard_update is implemented.

CHECKPOINT 8: After Build Step 14 (Deployment)
  What to verify: The publicly deployed system works end to end, not just locally.
  How to test it: From a browser hitting the Vercel URL (not localhost), complete one
                   full recommendation flow and one chatbot query.
  If it breaks:   Check CORS on the Render web service against the actual Vercel origin,
                   and confirm VITE_API_BASE_URL was set at Vercel build time (Vite
                   env vars are baked in at build, not read at runtime).
```

---

## 4.4 — Deployment Checklist

```
[ ] render.yaml declares: web (api), worker (ais-listener), cron (retrain-and-ingest),
    postgres (freight-db) — per DOC 3 §4
[ ] Environment variables set on the Render web service: DATABASE_URL, AISSTREAM_API_KEY,
    ANTHROPIC_API_KEY
[ ] Environment variable set on the Render cron job: RETRAIN_SCHEDULE_CRON (if
    overriding the constants.py default)
[ ] TimescaleDB extension enabled if available for the chosen Postgres version;
    proceed on plain Postgres if not — non-blocking per DOC 3 §4
[ ] Database migrations (alembic) run against the Render-managed Postgres instance
[ ] Backend build passes locally (uvicorn boots, /health returns 200 with
    warehouse_reachable=true) before first deploy
[ ] Vercel project created, pointed at /frontend, VITE_API_BASE_URL set to the Render
    web service's public URL
[ ] Frontend build passes locally (`npm run build`) with no TypeScript errors before
    first deploy
[ ] Smoke test: hit the public Render /health endpoint directly — confirm
    models_loaded, warehouse_reachable, and ais_listener_last_seen are all healthy
[ ] Smoke test: from the public Vercel URL, complete one full recommendation flow and
    confirm CORS isn't blocking the cross-origin call
[ ] Smoke test: trigger the Render cron job manually from the dashboard once, confirm
    a retrain completes and at least one ForecastObject updates
```

---

**Confirm this build sequence before starting to code — it's the contract for the week.**
Deviations from the order or scope above should be conscious calls made mid-build, not
accidents an agent drifts into. If you want, the natural next artifact is
`AGENTS.md` — a short session-coordination file an AI coding agent re-reads at the
start of every session to know what build step it's on and what to watch for, pulling
from this guide and the two reference files (`vibe-antipatterns.md`,
`prompt-patterns.md`) without needing to re-read DOC 1–4 in full each time.
