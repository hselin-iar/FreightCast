# DOC 2 (v4, Final Production) — Comprehensive Technical Architecture
### Intelligent Freight Forecasting, Port Compatibility & Optimized Vessel Chartering (SAIL PS3)

This document is the comprehensive, authoritative technical architecture for the **FreightCast / SAIL PS3** system. It defines the production architecture uniting Mixed-Integer Linear Programming (MILP) optimization with a First-Principles Grounded Provenance & Telemetry Verification Engine. The architecture integrates OPEX-grounded 7-bucket voyage economics, Sail vs. Kill incremental value maximization, downside risk ratio constraints, dynamic multi-voyage capacity budgeting, real AIS vessel repositioning physics, dynamic recommendation-grounded situational empirical proofs, an interactive telemetry evidence inspector, dual-section parallel hypothesis auditing, universal AST mathematical preprocessing, and a 4-resource high-availability cloud deployment with automated keepalive resilience.

---

## 1. Problem Definition & Operational Tiers

The system solves steel and dry bulk maritime logistics problems across two distinct operational tiers:

### Tier 1: Single-Cargo Tender Optimization (Interactive / Real-Time)
A chartering manager evaluating a specific shipment request (*Cargo Quantity*, *Origin Port*, *Preferred Discharge Ports*, *Timing Flexibility*) requires an integrated, sub-50ms recommendation that solves four interconnected problems simultaneously:
1. **Freight Rate Econometric Forecasting:** Predict forward spot rate curves ($/MT and $/day) across multiple horizons (7, 14, 30, 60 days) under uncertainty.
2. **Berth Physical Compatibility:** Enforce physical draft limits, length overall (LOA), beam, handling discharge rates, tidal windows, and intermediate lightening feasibility.
3. **Chartering Commitment Optimization (Spot vs. Forward Locked):** Solve a Mixed-Integer Linear Program (MILP) deciding:
   - How many voyages to split the parcel into (up to 6 voyages for heavy parcels).
   - Which vessel class (`Capesize`, `Panamax/Kamsarmax`, `Supramax/Ultramax`) and discharge port each voyage uses.
   - When each voyage departs ($\tau$) and its commitment mode (*Spot* vs. *Locked* rate).
   - The resulting 7-bucket cost breakdown and net incremental margin vs. walk-away benchmark.
4. **First-Principles Empirical Verification & Audit Gate:** Deterministically prove *why* the optimal vessel, parcel split, and discharge port assignment dominates alternative combinations using hydrodynamic laws, channel draft restrictions, cubic speed-power fuel curves, Admiralty distance deltas, and laytime/demurrage exposure, grounded in verified warehouse telemetry (`/provenance/situations/active` and `/provenance/catalog`).

### Tier 2: Fleet-Wide Portfolio Scheduling (Batch / Multi-Contract)
For monthly fleet operations, desk reviews, and multi-parcel tenders across all tracked bulk carriers and an entire slate of pending contracts (`GET /fleet-schedule` and `POST /fleet-schedule/solve`):
- Evaluates a batch of 10–20 cargo inquiries simultaneously rather than in isolation.
- Constructs an interval-overlap **temporal conflict graph** across candidate vessels to guarantee physical feasibility ($x_a + x_b \le 1$ for overlapping voyages).
- Solves a global Mixed-Integer Linear Program (MILP) maximizing total portfolio worst-case incremental net margin while preserving downside risk protection floors.
- Dynamically partitions the contract slate into **SAIL** (accepted and scheduled with assigned vessel, departure date, and ETA) vs. **KILL** (rejected or left to float on the spot market).
- Grounds scheduling in real-time AIS vessel telemetry (positions, underway speed, and ballast repositioning time).

---

## 2. Decision Scope — Data-Driven Warehouse Catalog

Origins, destination ports, vessel classes, and operational parameters are **dynamically resolved from the warehouse**, never hardcoded:

- **Destination Ports:** Loaded from verified rows in `port_constraints` (draft limits, LOA, beam, handling rate TPD, tidal dependency). Added via ingestion with human sign-off (`pending_verification`), requiring zero code changes.
- **Origin Ports:** Loaded from `route_physics` and `rate_history`.
- **Vessel Classes:** Canonical dry bulk classes (`Capesize`, `Panamax/Kamsarmax`, `Supramax/Ultramax`) with verified DWT capacities, laden/ballast fuel consumption, draft, LOA, and beam dimensions in `vessel_specs`.
- **Scope API (`GET /scope`):** Backed by `warehouse/repository.py`, returns live lists of valid origins, ports, and vessel classes. Consumed by API request validation, frontend form dropdowns, and chatbot system prompt grounding.
- **Grounded Telemetry Catalog (`GET /provenance/catalog`):** Exposes 20+ verified operational parameters (e.g. Admiralty nautical distances, MAN B&W SFOC fuel curves, port handling rates, tidal allowances, and laytime/demurrage rates). Each entry carries a typed provenance classification (`measured`, `modeled`, `assumed`), source lineage, confidence rating, and mathematical equation.
- **Provenance Tagging:** Every output metric carries typed provenance metadata with UI badges, ensuring transparent data honesty.

---

## 3. System Walkthroughs

The system exposes two front-ends (React Dashboard and Decision Assistant Chatbot) sitting on the exact same FastAPI backend engine, structured around a 5-tab top navigation hierarchy: `Recommendation | Provenance | Forecast | Ports | Fleet`.

### 3a. Via the Dashboard Form
1. **Manager Input:** Enters **Cargo Quantity** (e.g. 150,000 MT), **Origin Port** (Australia - Hay Point), **Discharge Ports** (Gangavaram, Paradip, Dhamra), and **Timing Flexibility** (30 days). Optional advanced input: *Locked-rate discount benchmark* (default 10%).
2. **API & Scope Validation:** Validates inputs against `GET /scope`.
3. **Constraint Feasibility:** Evaluates berth physical limits per port $\times$ vessel class. For instance, at Dhamra, Capesize LOA ($292\text{m} > 280\text{m}$) is strictly blocked; Panamax ($229\text{m} \le 280\text{m}$) passes.
4. **Forecast Retrieval:** Reads pre-computed `ForecastObject`s containing point estimates, confidence intervals, and scenario trajectories for each feasible route $\times$ vessel class.
5. **Cost Precomputation:** Computes 7-bucket cost coefficients across Base, Bull, and Bear scenarios for every candidate $(v, p, \tau, m)$.
6. **MILP Solve:** PuLP/CBC solves the downside incremental maximization problem in ~35ms.
7. **Response Rendering:** Renders winning plan, 7-bucket stacked cost bar, Base/Bull/Bear fan chart, AIS route map, sensitivity tornado chart, and why-not comparisons.
8. **Seamless Workflow Transition into Provenance:** Running a recommendation automatically populates the adjacent **Provenance Lab** tab with dynamic empirical proofs grounded specifically in the active cargo quantity, origin, selected port, and vessel draft.

### 3b. Via the Decision Assistant Chatbot
1. **Natural-Language Query:** User types: *"What's the best vessel for 70,000 tonnes from Australia to Paradip?"*
2. **Context & Tool Invocation:** Chatbot parses inputs from message and prior `cargo_context`, invoking `get_recommendation`.
3. **Identical Engine Execution:** Calls the exact same `/recommendation` solver path.
4. **Verbatim Grounded Response:** Formats response strictly using JSON fields returned by the tool (ocean freight, bunker, tax, net sail value).

### 3c. Mid-Conversation Constraint Change
1. **User Request:** *"What if I only use capemax and need this in 12 days?"*
2. **Contextual Mapping & Alias Normalization:**
   - Maps natural-language phrases to structured constraints: `allow_vessel = ["Capesize"]`, `max_completion_day = 12`.
   - `_normalize_constraints` maps `"capemax"` to canonical `"Capesize"`.
3. **Re-Solve:** Invokes `get_recommendation` with constraints fixed, executing a genuine MILP re-solve.
4. **Live Dashboard Update:** Chatbot replies in plain language and returns `updated_recommendation` with `constraint_note = "only Capesize, ≤12 days"`, automatically updating the dashboard UI.

### 3d. Via the Agentic Hypothesis Auditor
1. **Manager Question:** In the Provenance tab, user types any operational or physical question (e.g. *"Explain demurrage exposure, berth wait delay, and why Capesize is cheaper per tonne despite costing more overall"*).
2. **Dual-Section Concurrent Synthesis:** To prevent LLM rate limits and token-length timeouts, the query executes as two parallel requests:
   - **Section 1 (Physical & Operational Constraints):** First-principles breakdown of vessel draft, channel depth, LOA limits, handling duration, and queuing physics.
   - **Section 2 (Mathematical Cost Derivation & Economic Proof):** Display LaTeX formulas, parameter definitions, and a detailed cost comparison table.
3. **Interactive Evidence Inspector:** The output is scanned by `termHighlighter`, rendering dotted cyan underlines under maritime data terms (`demurrage`, `ocean freight`, `bunker`, `OPEX`, `MILP`, `draft`, `laytime`). Hovering reveals interactive cards with definitions, formulas, and telemetry sources.
4. **Universal Math Preprocessing:** All equations pass through `mathUtils.ts`, auto-healing delimiter brackets (`\left` / `\right`), eliminating empty display boxes, and ensuring crisp KaTeX rendering.

### 3e. Via Fleet Schedule & Portfolio Optimization
1. **Monthly Slate Review:** Chartering desk opens the **Fleet** tab (`GET /fleet-schedule` and `GET /fleet-status`). The executive banner immediately summarizes the portfolio bottom line: total contracts, expected incremental net margin above spot, worst-case floor, and active vessel commitments.
2. **Operational Constraint Tuning:**
   - **Max Sail Contracts:** Manager adjusts active capacity limit (e.g. throttling from 12 to 8 contracts due to letter-of-credit or bunker credit limits).
   - **Downside Risk Ratio:** Desk moves the risk tolerance slider ($0.0 \to 1.0$) to balance conservative downside floor protection vs. aggressive expected margin.
3. **Dynamic Re-Optimization (`POST /fleet-schedule/solve`):** Triggers an on-demand solve of the Step 51V PuLP CBC MILP formulation. Evaluates the batch against the interval-overlap conflict graph and returns the new optimal allocation in $<500\text{ms}$.
4. **Visual De-confliction (Schedule Gantt):** The Gantt timeline displays horizontal vessel lanes with distinct contract voyage blocks ($Departure \to ETA$), visually verifying that consecutive voyages on the same bulk carrier have collision-free turnaround intervals.
5. **Execution & Live Grounding (Decision Matrix & AIS Inspector):**
   - Filterable table isolates **SAIL** decisions (assigned vessel, laycan window, voyage cost, incremental margin) for broker fixing vs. **KILL** decisions (walk away or float unhedged on spot).
   - Live AIS Telemetry tab displays real-time Latitude/Longitude, underway speed (knots), and position pings of tracked bulk carriers to verify physical laycan feasibility.

---

## 4. High-Level Architecture

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                 FRONTEND CLIENT LAYER                                  │
│  React 19 + TypeScript + Vite + Recharts + Lucide Icons + apiClient.ts                 │
│  ├─ Top Navigation Bar (Recommendation | Provenance | Forecast | Ports | Fleet)        │
│  ├─ Dashboard (WhatIfSliders, Interactive Form, WinningPlanBanner, 7-Bucket Cost Grid) │
│  ├─ Provenance Lab (SituationalProofLab, Evidence Inspector, Hypothesis Auditor)       │
│  ├─ Scenario Lab (Base / Bull / Bear Fan Chart, Robustness & Regret Readouts)          │
│  ├─ Fleet Schedule (Gantt Timeline, Portfolio Optimizer Sliders, Decision Matrix, AIS) │
│  ├─ AST Mathematical & Currency Preprocessor (mathUtils.ts, rehypeUnescapeCurrency)    │
│  └─ Decision Assistant (Natural-Language Chat with Live Tool-Calling & Normalization)   │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │ HTTP JSON (stateless) + Auto-Failover
┌───────────────────────────────────────────▼────────────────────────────────────────────┐
│                                  FASTAPI BACKEND API                                   │
│  /recommendation   /scenario   /chat   /forecast   /compatible-vessels   /port-status  │
│  /fleet-schedule   /fleet-schedule/solve   /fleet-status   /api/ping   /health  /scope │
│  /provenance/situations   /provenance/situations/active   /provenance/catalog          │
│  ├─ Scope Validator & Natural Language Constraint Normalizer (_normalize_constraints)  │
│  ├─ Telemetry Citation & Grounded Scenario Builder (build_grounded_scenarios)          │
│  ├─ Fleet Portfolio Engine (Step 51V MILP Conflict Graph Solver: fleet_optimizer.py)   │
│  └─ Chat Tool-Calling Proxy (Groq / Nvidia NIM / Anthropic Claude / OpenAI)           │
└───────┬─────────────────────┬─────────────────────┬────────────────────┬───────────────┘
        │                     │                     │                    │
┌───────▼─────────────┐ ┌─────▼─────────────┐ ┌─────▼──────────────────┐ ┌▼──────────────┐
│  CONSTRAINT ENGINE  │ │ FORECASTING ENGINE│ │      COST TERMS        │ │  PROVENANCE & │
│  Deterministic Rules│ │ Walk-Forward Gated│ │7-Bucket OPEX Economics │ │CITATION ENGINE│
│  ├─ 1. Draft limit  │ │ ├─ Enriched XGBoost│ ├─ 1. Ocean Freight     │ │├─ Grounded    │
│  ├─ 2. LOA limit    │ │ ├─ Auto-ARIMA     │ │  (Effective Post-Disc.)│ │   Situations  │
│  ├─ 3. Beam limit   │ │ ├─ Naive Baseline │ ├─ 2. Bunker (Physics)   │ │├─ Telemetry   │
│  ├─ 4. Parcel-fit   │ │ ├─ Damped Fallback│ ├─ 3. OPEX (Daily Vessel)│ │   Catalog     │
│  ├─ 5. Handling rate│ │ └─ Prophet Addit. │ ├─ 4. Other Voyage (Dues)│ │├─ Sensitivity │
│  ├─ 6. Tidal window │ │    Decomposition  │ ├─ 5. Port Handling      │ │   Tornado     │
│  ├─ 7. Lightening   │ └─────────┬─────────┘ ├─ 6. Lightening Penalty │ │└─ Citation    │
│  └─ 8. Vessel rank  │           │           │ ├─ 7. Tax (Exact 5.0%) │ │   Registry    │
└───────┬─────────────┘           │           └─────┬──────────────────┘ └┬──────────────┘
        │                         │                 │                     │
        └─────────────────────────┼─────────────────┴─────────────────────┘
                                  │
┌─────────────────────────────────▼──────────────────────────────────────────────────────┐
│                     DECISION OPTIMIZER (MILP via PuLP / CBC)                           │
│  Objective: Maximize Worst-Case Incremental Value  max Σ x * worst_incremental         │
│  Downside Risk Constraint: Σ x * (worst_incremental - 0.60 * base_incremental) >= 0   │
│  Decomposed Variables: q_i (tonnes), x_iv (vessel), y_ip (port), z_it (tau), w_im(mode)│
│  Dynamic Capacity Budgeting: Needed = max(1, ceil(Q/Cap)), max 6 voyages with clamping │
│  Fast Fallback: Hybrid Enumeration (<50ms solver timeout safety net)                   │
└─────────────────────────────────┬──────────────────────────────────────────────────────┘
                                  │
┌─────────────────────────────────▼──────────────────────────────────────────────────────┐
│                 SQLITE / POSTGRES WAREHOUSE & CLOUD DEPLOYMENT                         │
│  Tables: rate_history, port_constraint, vessel_spec, forecast_object, route_physics,   │
│          exogenous_feature, telemetry_catalog, congestion, ais_position                │
│  Render 4-Resource Blueprint: Web Service + AIS Worker + Retrain Cron + Postgres DB   │
│  Vercel SPA Frontend + Automated GitHub Actions Keepalive Cron Workflow (/api/ping)   │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Data Sources & Ingestion Pipeline

| Source | Cadence | Feeds | Description |
|---|---|---|---|
| Baltic Dry Index (BDI) | Daily close | Exogenous feature | Historical daily BDI close (2,900+ points). |
| Bunker Prices (VLSFO / MGO) | Daily | Cost terms & exogenous | Live via OilPriceAPI / synthetic market series. |
| Port Constraints | Monthly / On Change | Constraint Engine | PDF/port handbook extraction, `pending_verification` gate. |
| Vessel Specs | Monthly | Constraint & Decision | Verified DWT, draft, LOA, beam, and fuel consumption specs. |
| AIS Vessel Positions | Continuous | Repositioning & Fleet Schedule | Real IMO-tracked bulk carriers via MyShipTracking feed. |
| Route Rate Assessments (5TC) | Daily / Weekly | Rate History | Benchmark Capesize, Panamax, Supramax route rates. |
| Macro Features | Daily | Forecasting models | Brent, WTI, Iron Ore 62% Fe, BDRY ETF, GSCPI index. |
| Route Physics & Distances | Static / Refreshed | Cost terms & Provenance | Nautical distances (NM), laden/ballast fuel burn, daily OPEX. |
| Admiralty Distance Tables | Navigational verified| Provenance Lab | Geodetic distance deltas between competing discharge ports. |
| Engine SFOC Sea Trials | Manufacturer verified| Cost terms & Provenance | MAN B&W speed-power cubic fuel curves for vessel classes. |
| Telemetry Parameter Registry| Continuous | Provenance Catalog | Grounded registry of 20+ operational parameters with equations. |
| Operational Evidence | Weekly | Advisory layer | Broker fixture evidence, charterer matching. |

---

## 6. Parameter Usage Map

| Parameter | Originates At | Consumed By | Architectural Role |
|---|---|---|---|
| `cargo_quantity` | Form / Chat / API | Constraint Engine | Evaluated against vessel capacity bands (Rule 4). |
| | | Decision Optimizer | Sized into voyage parcels $\sum q_i = \text{cargo\_quantity}$. |
| | | Provenance Engine | Evaluates draft limits and parcel splitting proofs. |
| `origin_port` | Form / Chat / API | Decision Optimizer | Combined with discharge ports to look up route physics & forecasts. |
| `discharge_ports[]` | Form / Chat / API | Constraint Engine | Checked against berth limits; validated via `GET /scope`. |
| `timing_flexibility_days` | Form / Chat / API | Decision Optimizer | Bounds the fix-date search window $[0, \text{flexibility}]$. |
| `commitment_benchmark_pct`| Form (Advanced) / Chat | Cost Terms | Discount applied to spot rate for locked forward commitments (default 10%). |
| `bunker_price_usd` | Ingestion / DB | Cost Terms | Multiplied by distance fuel consumption to price bunker cost. |
| `daily_opex_usd` | Route Physics / DB | Cost Terms | Multiplied by voyage days to compute operating expenses. |
| `vessel_positions` | AIS Feed / DB | Fleet Schedule | Determines ballast repositioning feasibility and earliest departure. |
| `active_recommendation` | Solver Output | Provenance Lab | Binds dynamic situational proofs to actual cargo and vessel allocations. |
| `admiralty_distance_delta`| Route Physics / DB | Provenance Engine | Computes fuel savings from hydrodynamic distance differentials. |
| `laytime_hours` & `demurrage_rate`| Port Constraints / DB | Cost Terms & Provenance | Quantifies congestion delay exposure and demurrage penalties. |

---

## 7. Forecasting Engine

The forecasting engine implements a walk-forward validated model ladder with multi-feature macroeconomic enrichment:

### Models in Ladder
1. **Enriched XGBoost (Primary):** Gradient-boosted decision trees trained on historical rates, 7/14-day lags, rolling volatility, BDI momentum, Brent, Iron Ore, and bunker prices. Minimum training threshold: 80 observations.
2. **Auto-ARIMA (Statistical Baseline):** Automated $(p,d,q)$ order selection minimizing AIC.
3. **Prophet (Explainability Decomposition):** Isolates macroeconomic trend, weekly/annual seasonality, and exogenous shock drivers for human explainability.
4. **Damped-Trend Fallback:** Activated by `ConditionsMonitor` if input features breach historical percentile bands.

### Walk-Forward Validation Gate
Before a model can write `ForecastObject` records to the warehouse, it must beat the naive random-walk baseline on rolling out-of-sample backtests (MAE, RMSE, MAPE, Directional Accuracy).

---

## 8. Deterministic Constraint / Feasibility Engine

Pure deterministic rules over typed `PortConstraint` and `VesselSpec` records:

1. **Rule 1 (Draft Limit):** $\text{Vessel Draft} \le \text{Port Max Draft}$. If exceeded, checks Rule 7.
2. **Rule 2 (LOA Berth Limit):** $\text{Vessel LOA} \le \text{Port Max LOA}$. Hard block (e.g. Capesize $292\text{m} > 280\text{m}$ max at Dhamra is blocked).
3. **Rule 3 (Beam Berth Limit):** $\text{Vessel Beam} \le \text{Port Max Beam}$. Hard block.
4. **Rule 4 (Parcel Fit Heuristic):** Flagged `is_inefficient_fit = True` if cargo is $<40\%$ of vessel capacity.
5. **Rule 5 (Handling Rate & Duration):** $\text{Discharge Days} = \frac{\text{Cargo Quantity}}{\text{Handling Rate TPD}}$.
6. **Rule 6 (Tidal Window Arrival):** Produces `tidal_window_note` for tide-dependent ports.
7. **Rule 7 (Lightening Routing):** If draft exceeds limit but deeper-draft intermediate ports exist (e.g. Gangavaram/Dhamra before Paradip), marks `requires_lightening = True` with $\$75,000$ penalty and $2.5\text{ days}$ added.
8. **Rule 8 (Vessel Size Ordering):** Proposes larger classes first for economy-of-scale hints.

---

## 9. Scenario Generator

Given a `ForecastObject`, generates three continuous market trajectories across the timing flexibility horizon:
- **Base Scenario:** Expected point estimate trajectory.
- **Bull Scenario (Optimistic for Charterer):** Favorable market curve shifting toward lower rate bounds.
- **Bear Scenario (Pessimistic for Charterer):** Rising freight rate curve shifting toward upper confidence bounds.

---

## 10. Cost Terms & 7-Bucket Economic Model

Total cost is calculated per candidate $(v, p, \tau, m, s)$ as:

$$\text{Total Cost} = \text{Ocean Freight} + \text{Bunker} + \text{OPEX} + \text{Other Voyage} + \text{Port Handling} + \text{Lightening} + \text{Tax}$$

1. **Ocean Freight:**
   - *Spot:* $\text{Quantity} \times \text{Forecast Rate}(\tau, s)$.
   - *Locked:* $\text{Quantity} \times \text{Base Rate}(\tau=0) \times (1 - \text{Discount Benchmark})$. Identical across all scenario evaluations.
2. **Bunker Cost (Physics & Cubic Steaming Law):**
   - $\text{Voyage Days} = \frac{\text{Distance NM}}{24 \times \text{Speed Knots}} + \text{Discharge Days} + \text{Lightening Days}$.
   - Evaluates three distinct operational steaming speed regimes governed by the cubic Admiralty law ($P \propto V^3$, daily fuel burn $\propto V^3$):
     * **Eco Mode ($11.5\text{ kn}$):** Slow steaming reduces fuel burn by $22.15\%$ ($\left(11.5/12.5\right)^3 \approx 0.7785$), saving $\approx \$49,000$ in bunker expenses per voyage for flexible laycans.
     * **Base Mode ($12.5\text{ kn}$):** Canonical commercial charter party service speed establishing the contract baseline.
     * **Fast Mode ($14.0\text{ kn}$):** High-speed transit for tight laycan deadlines, accelerating arrival by $\approx 1.2\text{ days}$ at an added $+40.5\%$ fuel burn cost ($\left(14.0/12.5\right)^3 \approx 1.405$).
   - $\text{Bunker Cost} = (\text{Laden Consumption TPD}(\text{Speed}) \times \text{Voyage Days}) \times \text{Bunker Price USD/MT}$.
3. **OPEX Cost:** $\text{Daily OPEX USD} \times \text{Voyage Days}$ ($\$8,500/\text{day}$ Capesize, $\$7,200/\text{day}$ Panamax, $\$6,500/\text{day}$ Supramax).
4. **Other Voyage Costs:** Port dues, canal tolls, pilotage from `RoutePhysics`.
5. **Port Handling:** Port handling tariff $\times \text{Cargo Quantity}$.
6. **Lightening Extra:** Added anchorage and port charges when lightening is required.
7. **Tax Cost:** Exact $5.0\%$ applied strictly to the **effective post-discount ocean freight cost**:
   $$\text{Tax Cost} = \text{Ocean Freight}_{\text{effective}} \times 0.05$$
   Ensures accurate commercial accounting matching Indian withholding tax standards.

---

## 11. Decision Engine (MILP Optimizer)

### 11.1 Decomposed Decision Variables
To ensure solve latency remains $<50\text{ms}$, variables are decomposed rather than indexed jointly:

| Variable | Type | Definition |
|---|---|---|
| $q_i \ge 0$ | Continuous | Cargo tonnage allocated to voyage $i$. |
| $x_{i,v} \in \{0,1\}$ | Binary | 1 if voyage $i$ uses vessel class $v$. |
| $y_{i,p} \in \{0,1\}$ | Binary | 1 if voyage $i$ discharges at port $p$. |
| $z_{i,\tau} \in \{0,1\}$ | Binary | 1 if voyage $i$ fixes at departure day $\tau$. |
| $w_{i,m} \in \{0,1\}$ | Binary | 1 if voyage $i$ uses commitment mode $m \in \{\text{spot}, \text{locked}\}$. |
| $\ell_{i,p} \in \{0,1\}$ | Binary | 1 if voyage $i$ requires lightening at port $p$. |

### 11.2 Sail vs. Kill Incremental Objective Formulation
Framed around maximizing downside net margin over the walk-away opportunity benchmark:

$$\max_{x, y, z, w, q, \ell} \sum_{i} \sum_{c} x_{i,c} \cdot \text{Worst Incremental}_c$$

Where:
- $\text{Freight Revenue} = \text{Cargo Quantity} \times \text{Base Spot Rate}$
- $\text{Sail Value}(s) = \text{Freight Revenue} - \text{Total Voyage Cost}(s)$
- $\text{Kill Value} = \text{Cargo Quantity} \times \text{Base Spot Rate} \times \text{Benchmark Factor}$
- $\text{Incremental Value}(s) = \text{Sail Value}(s) - \text{Kill Value}$
- $\text{Worst Incremental} = \min_{s \in \{\text{Bear, Base, Bull}\}} \text{Incremental Value}(s)$

### 11.3 Downside Risk Ratio Constraint
Guarantees that selected strategies do not suffer severe downside deterioration:

$$\sum_{i} \sum_{c} x_{i,c} \cdot (\text{Worst Incremental}_c - 0.60 \cdot \text{Base Incremental}_c) \ge 0$$

### 11.4 Dynamic Multi-Voyage Capacity Budgeting
The solver dynamically determines the required voyage count and strictly clamps individual voyage tonnages to vessel physical capacities:

$$\text{Needed Voyages} = \max\left(1, \left\lceil \frac{\text{Cargo Quantity}}{\text{Max Feasible Vessel Capacity}} \right\rceil\right), \quad \text{Max Voyages Allowed} = \min(6, \text{Needed Voyages})$$

Individual voyage parcel tonnages satisfy:
$$q_i \le \sum_v x_{i,v} \cdot \text{Capacity}_v \quad \forall i, \quad \sum_{i} q_i = \text{Cargo Quantity}$$

This ensures physical feasibility for large parcels calling at draft-restricted ports (e.g. 300,000 MT at Dhamra, where Capesize is blocked by draft, cleanly solves as 4 Panamax voyages: $60\text{k} + 80\text{k} + 80\text{k} + 80\text{k}$ MT without capacity violation).

### 11.5 Human Overrides & Alias Normalization
Supports:
- `allow_vessel: ["Capesize"]` / `require_vessel: "Capesize"`
- `exclude_vessel: ["Panamax/Kamsarmax"]`
- `require_port: "Gangavaram"`
- `force_mode: "locked"`
- `min_fix_day: 14`, `max_completion_day: 30`
- Fuzzy natural language alias normalization (`_normalize_constraints` maps `"Cape Max"`, `"Super Max"`, `"Panamax"` to canonical warehouse classes).

---

## 12. Provenance, Explainability & Grounded Telemetry Layer

The Provenance layer transforms optimization outputs from opaque mathematical solutions into fully auditable, empirical first-principles proofs.

### 12.0 Typed Provenance Classification & Lineage Tracking
Every data point, forecast, cost coefficient, and recommendation carries an immutable typed provenance classification tagged at the point of origin:
- **`measured`:** Directly captured empirical telemetry from verified physical sensors, navigational publications, or market feeds (e.g. live AIS coordinates, underway speed over ground, daily BDI close, published bunker spot prices, verified berth limits, Admiralty geodetic distances).
- **`modeled`:** Algorithmic outputs derived from statistical forecasts, econometric models, or deterministic operations research (e.g. walk-forward XGBoost rate forecasts, 7-bucket voyage cost breakdowns, Admiralty cubic speed-power fuel curves, interval-overlap conflict graphs, and MILP optimal allocations).
- **`assumed`:** Operational baselines, contractual defaults, or user-configured parameters set by the chartering manager (e.g. locked-rate discount benchmark, timing flexibility bounds, daily demurrage penalties).

Tagged values originate via typed helpers (`tag_measured()`, `tag_modeled()`, `tag_assumed()`) in `warehouse/repository.py`, `forecasting.py`, `cost_terms.py`, and `decision.py`, propagating to the UI via interactive `ProvenanceBadge` tokens and hover popovers.

### 12.1 Dynamic Recommendation-Grounded Empirical Proofs
Rather than displaying static boilerplate, `POST /provenance/situations/active` binds the active cargo recommendation (Quantity, Origin, Selected Port, Vessel Class, Voyage Count, Cost Breakdown) with warehouse telemetry to construct four grounded situational proofs:
1. **Port Hydrodynamics & Draft Physics:** Proves why port draft limits (e.g. Dhamra 14.0m) physically block Capesize ($18.2\text{m}$ draft) and force parcel splitting into multiple Panamax voyages, calculating exact overhead and pilotage deltas.
2. **Hydrodynamic Distance & Bunker Volatility:** Uses the cubic speed-power law to demonstrate how nautical mile distance deltas (e.g. Gangavaram saving $270\text{ NM}$ over Paradip) translate to fuel savings under market fuel shocks.
3. **Forward Curve Arbitrage & Commitment Mode:** Quantifies the insurance premium vs. volatility savings of locked forward commitments vs. spot exposure across the timing horizon.
4. **Berth Congestion, Laytime & Demurrage Exposure:** Formulates expected demurrage cost $\mathbb{E}[C^{\text{dem}}_v] = r^{\text{dem}} \cdot \mathbb{E}[D_v]$, demonstrating how queue times and laytime allowances drive port selection.

### 12.2 Interactive Evidence Inspector & Grounded Data Term Highlighting
The `termHighlighter` and `DataTermToken` components scan all proof narratives and audit text, identifying maritime economic and physical terms (`ocean freight`, `bunker`, `OPEX`, `port handling`, `demurrage`, `tax`, `MILP`, `draft`, `laytime`, `deadweight`).
- Terms receive a non-intrusive dotted cyan underline.
- Hovering opens an interactive card displaying the formal definition, mathematical formula, telemetry source, provenance classification (`measured`, `modeled`, `assumed`), and verification status.
- Replaces distracting inline bracketed variable tags with an on-demand audit trail.

### 12.3 Agentic Hypothesis Auditor
Embedded in the Provenance Lab, the Hypothesis Auditor allows chartering managers to explore arbitrary operational "what-if" hypotheses via natural language.
- **Dual-Section Concurrent Synthesis:** Solves LLM rate limits and token-length timeouts by executing two parallel requests:
  - *Section 1:* Physical and operational constraints (hydrodynamics, channel depth, LOA limits, handling duration).
  - *Section 2:* Mathematical cost derivation, display LaTeX formulas, parameter definitions, and comparative economic tables.
- **Multi-Provider Failover:** Proxies requests across Groq, Nvidia NIM, Anthropic Claude, and OpenAI to ensure zero downtime.

### 12.4 Universal AST Mathematical & Currency Preprocessor
The `mathUtils.ts` preprocessor immunizes frontend KaTeX rendering against common LLM formatting anomalies:
- **Early Display Block Stashing:** Stashes `$$ ... $$` blocks and collapses internal blank lines prior to heuristic line matching, preventing the double-wrapping empty box bug.
- **Delimiter Auto-Healing:** Matches bare `\right` tokens at line or equation ends to their opening brackets (`\mathbb{E}\left[D_v\right` $\rightarrow$ `\mathbb{E}\left[D_v\right]`) and auto-closes unclosed `\left` with `\right.`.
- **Punctuation & Syntax Repair:** Normalizes operator spacing (`;=;` $\rightarrow$ `\;=\;`, `;\times;` $\rightarrow$ `\;\times\;`), cleans stripped negative spaces (`\mathbb{E}!\left` $\rightarrow$ `\mathbb{E}\left`), and restores subscript underscores (`D{v}` $\rightarrow$ `D_{v}`).
- **Bullet-Point Math Auto-Wrapping:** Automatically wraps variables preceding `=` in bullet points into `$ ... $` (`• $r^{\text{dem}}$ = ...`).
- **AST-Level Currency Sanitization:** Converts currency in math mode to `\text{USD } num`, and unescapes dollar signs in prose at the AST level (`rehypeUnescapeCurrency`).

### 12.5 Sensitivity Tornado Analysis & Robustness Scoring
- Perturbs key assumptions ($\pm 10\%$ commitment discount, bunker prices, port handling rates) to compute sensitivity bars without re-solving the MILP.
- Computes a Robustness Score based on the spread between Base and Worst-case scenario costs.

---

## 13. Fleet Portfolio Scheduling & Temporal Conflict Optimization (Step 51V)

The Fleet Portfolio Engine (`backend/engine/fleet_optimizer.py`, `POST /fleet-schedule/solve`, and `GET /fleet-schedule`) provides global, multi-contract batch scheduling across all active bulk carriers, replacing manual spreadsheets with an integer programming model.

### 13.1 Production Problem Definition
In dry bulk chartering operations, a desk handles a monthly slate of $C$ candidate contracts ($10$–$20$ inquiries) across $V$ available bulk carriers. Each candidate voyage $k = (c, v)$ possesses:
- Specific departure date $D_k$ and estimated arrival $\text{ETA}_k$.
- 3-scenario market rates: $\text{Bear}_k$, $\text{Base}_k$, $\text{Bull}_k$.
- Voyage economics: $\text{Bunker Cost}_k$, $\text{Daily OPEX}_k$, and $\text{Port Handling}_k$.
- Incremental margin over walk-away benchmark: $\text{Worst Incremental}_k = \min_{s} \text{Incremental}_k(s)$.

### 13.2 Interval-Overlap Temporal Conflict Graph
To eliminate voyage collisions and double-booking, the engine builds a temporal conflict graph $G = (\mathcal{K}, \mathcal{E})$. For any two candidate voyages $a, b \in \mathcal{K}$ assigned to the same physical vessel $\text{IMO}_a = \text{IMO}_b$:
$$(a, b) \in \mathcal{E} \iff D_a < \text{ETA}_b \quad \text{and} \quad D_b < \text{ETA}_a$$

Every collision edge yields a hard mutual-exclusion packing constraint:
$$x_a + x_b \le 1 \quad \forall (a, b) \in \mathcal{E}$$

### 13.3 Global MILP Mathematical Formulation
The problem is formulated in PuLP and solved via CBC ($<500\text{ms}$ solve time):

$$\max_{x} \sum_{k \in \mathcal{K}} x_k \cdot \text{Worst Incremental}_k$$

Subject to:
1. **Single Assignment per Contract:** At most one vessel is assigned to each contract inquiry:
   $$\sum_{k \in \mathcal{K}(c)} x_k \le 1 \quad \forall c \in \mathcal{C}$$
2. **Fleet Capacity Budgeting:** Limits total simultaneous commitments to manageable operational limits:
   $$\sum_{k \in \mathcal{K}} x_k \le \text{MaxSail} \quad (\text{user-controlled, default: } 12)$$
3. **Zero-Collision Temporal Feasibility:**
   $$x_a + x_b \le 1 \quad \forall (a, b) \in \mathcal{E}$$
4. **Downside Risk Protection Floor:** Guarantees that the accepted portfolio preserves downside safety relative to base expectations:
   $$\sum_{k \in \mathcal{K}} x_k \cdot \text{Worst Incremental}_k \ge \text{RiskRatio} \cdot \sum_{k \in \mathcal{K}} x_k \cdot \text{Base Incremental}_k \quad (\text{default: } 0.60)$$

### 13.4 Decision Partitioning & Output Architecture
The solution dynamically partitions contracts:
- **`SAIL`:** High-yielding, risk-protected contracts accepted for chartering with a specific vessel assignment, departure date, and ETA window.
- **`KILL`:** Contracts rejected or deferred to spot execution due to negative incremental margins, vessel calendar conflicts, or downside risk violations.

### 13.5 Live AIS Fleet Telemetry & Grounding
Via `GET /fleet-status`, the fleet schedule is validated against real-world AIS telemetry:
- Live Latitude/Longitude, underway speed in knots, and latest satellite pings for each tracked vessel.
- Canonical physical specifications (`VesselSpec`: summer draft, LOA, beam, typical DWT) confirming berth compatibility.

---

## 14. Operational Evidence Layer

Post-solve advisory layer matching candidate fixtures against real-world broker fixture records (ShipOffer), displayed as visual alignment badges on the dashboard.

---

## 15. API Route Specifications

| Method | Route | Description |
|---|---|---|
| `POST` | `/recommendation` | Single-cargo tender optimization solve. |
| `POST` | `/scenario` | Pinned what-if scenario comparison. |
| `POST` | `/chat` | Natural-language assistant with tool-calling. |
| `GET` | `/forecast` | Forward rate forecast and confidence bands. |
| `GET` | `/compatible-vessels`| Physical berth rule checks. |
| `GET` | `/port-status` | Port congestion and queue wait times. |
| `GET` | `/fleet-schedule` | Multi-vessel fleet schedule, assignments, and Gantt data. |
| `POST` | `/fleet-schedule/solve` | On-demand Step 51V multi-contract fleet portfolio MILP solve. |
| `GET` | `/fleet-status` | Live tracked AIS vessel telemetry and canonical vessel classes. |
| `GET` | `/provenance/situations` | Baseline first-principles situational proofs. |
| `POST` | `/provenance/situations/active`| Dynamic recommendation-grounded empirical proofs. |
| `GET` | `/provenance/catalog` | Grounded telemetry and parameter registry. |
| `GET` | `/scope` | Live valid origins, discharge ports, and vessel classes. |
| `GET` | `/health` | Warehouse reachability and model freshness. |
| `GET` | `/api/ping` | High-availability keepalive health probe. |

---

## 16. Frontend Presentation Components

1. **Top Navigation Bar:** 5-tab persistent navigation: `Recommendation | Provenance | Forecast | Ports | Fleet`.
2. **WhatIfSliders:** Reactive sliders for cargo quantity, timing flexibility, and discount benchmark.
3. **WinningPlanBanner:** Summary of optimal voyage count, ports, vessels, and worst-case cost.
4. **7-Bucket Cost Breakdown Grid:** Interactive visual bar and table detailing Ocean Freight, Bunker, OPEX, Other Costs, Port Handling, Lightening, and Tax.
5. **SituationalProofLab:** Dynamic empirical proof cards displaying hydrodynamics, distance physics, and laytime metrics with on-hover telemetry citations.
6. **DataTermToken & CitationToken:** Interactive hover popover components rendering formulas, definitions, and verified warehouse sources.
7. **HypothesisAuditor:** Embedded conversational auditor with dual-section concurrent rendering and AST math protection.
8. **Scenario Fan Chart:** Recharts visualization of Base, Bull, and Bear forecast curves with marked fix dates ($\tau$).
9. **AIS Route & Repositioning Map:** Map displaying load/discharge ports, vessel positions, and congestion status.
10. **WhyNotComparator:** Side-by-side diagnostic comparison between winning plan and alternative candidate options.
11. **FleetSchedulePage & ScheduleGantt:** Zero-collision Gantt deployment timeline, reactive `Max Sail` and `Risk Ratio` sliders, contract decision matrix with `SAIL`/`KILL` filtering, and real-time tracked AIS fleet inspector.
12. **Executive Brief Export:** One-page summary export for chartering executives.

---

## 17. Non-Functional Performance & High-Availability Standards

- **Solver Latency:** $<50\text{ms}$ for standard MILP solves (timeout threshold: $4.0\text{s}$); $<500\text{ms}$ for global multi-contract fleet portfolio MILP solves.
- **Database Query Latency:** $<10\text{ms}$ via indexed SQLite / PostgreSQL.
- **Stateless API:** Zero server-side session state for chat and recommendation requests.
- **Frontend Responsiveness:** $<300\text{ms}$ debounced re-render during slider adjustments.
- **Cloud Architecture & Keepalive Resilience:**
  - Deployed across a 4-resource Render Blueprint (FastAPI Web API, Background AIS Worker, Retrain Cron, and Managed PostgreSQL).
  - Automated GitHub Actions keepalive cron workflow (`keepalive.yml`) pinging `/api/ping` every 10 minutes to eliminate free-tier cold-boot spin-downs.
  - Frontend auto-polls `/health` with fast 3-second retries during boot, providing animated warmup feedback and preventing premature submissions.
  - Production API routing with automatic fallback in `apiClient.ts` when hosted on Vercel.

---

## 18. Data Quality & Model Gating Checklist

- **Schema Validation:** Strict Pydantic models for all API payloads.
- **Port Safety Sign-off:** Changes to berth draft or LOA limits require verified human sign-off.
- **Walk-Forward Out-of-Sample Gate:** Models must beat naive random-walk on rolling tests.
- **Freshness Alerts:** Stale AIS congestion data ($>48\text{h}$) is flagged explicitly.
- **Telemetry Parameter Integrity:** All 20+ parameters in `GET /provenance/catalog` verified against Admiralty tables and engine manufacturer specifications.

---

## 19. Risk Register & Mitigations

| Risk | Mitigation |
|---|---|
| Berth draft/LOA inaccuracies causing grounding | Strict deterministic rules; physical hard-blocks on LOA/draft; manual verification gate. |
| Freight market volatility & geopolitical shocks | 3-scenario fan bands; downside risk ratio constraint; Damped-trend fallback. |
| Large parcel infeasibility at restricted ports | Dynamic capacity budgeting splitting up to 6 voyages; physical vessel capacity clamping. |
| Multi-contract voyage collisions / double-booking | Interval-overlap temporal conflict graph generating hard mutual-exclusion constraints ($x_a + x_b \le 1$). |
| Chatbot hallucination of rates or ship names | System prompt live scope injection; fuzzy constraint normalizer; strict verbatim tool grounding. |
| LLM rate-limit or timeout on complex proofs | Dual-section concurrent synthesis splitting physical and mathematical derivations; multi-provider failover. |
| Malformed LaTeX or empty display boxes | Universal AST preprocessor with early block stashing, delimiter auto-healing, and currency escaping. |
| Cloud cold-boot spin-down | Automated 10-minute GitHub Actions keepalive ping; client-side animated warmup polling. |
| AIS data feed disruption | Graceful degradation to calendar-based $\tau$ points; UI alerts for stale congestion. |

---

## 20. System Constants & Defaults

- `TAX_RATE_PCT = 5.0%` (computed strictly on effective post-discount ocean freight).
- `DEFAULT_COMMITMENT_BENCHMARK_PCT = 10.0%` (locked discount vs. spot).
- `MILP_RISK_RATIO = 0.60` (minimum acceptable worst-to-base incremental ratio).
- `DEFAULT_MAX_SAIL_CONTRACTS = 12` (fleet portfolio capacity ceiling).
- `MAX_VOYAGE_SPLITS = 6` (maximum parcel voyages for dynamic capacity budgeting).
- `LIGHTENING_PENALTY_DAYS = 2.5` & `LIGHTENING_PENALTY_COST_USD = $75,000`.
- `DEFAULT_BALLAST_SPEED_KTS = 12.0` & `DEFAULT_SAFETY_BUFFER_HOURS = 6.0`.
- Steaming Speed Modes: `Base = 12.5 kn`, `Eco = 11.5 kn` (-22.15% fuel burn), `Fast = 14.0 kn` (+40.5% fuel burn).
- `KEEP_ALIVE_INTERVAL_MINUTES = 10` (GitHub Actions keepalive frequency).
- Typical Capacities: Capesize ($180\text{k}\text{ MT}$), Panamax/Kamsarmax ($75\text{k}$–$80\text{k}\text{ MT}$), Supramax/Ultramax ($58\text{k}\text{ MT}$).
