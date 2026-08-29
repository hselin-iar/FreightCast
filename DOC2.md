# DOC 2 (v4, Final Production) — Comprehensive Technical Architecture
### Intelligent Freight Forecasting, Port Compatibility & Optimized Vessel Chartering (SAIL PS3)

This document is the comprehensive, authoritative technical architecture for the **FreightCast / SAIL PS3** system. It bridges the foundational system specification with the live production codebase and research parity upgrades transplanted from the `freight-optimization` research pipeline (OPEX-integrated 7-bucket economics, Sail vs. Kill incremental value maximization, downside risk ratio constraints, dynamic multi-voyage capacity budgeting, real AIS vessel repositioning physics, live scope catalogs, resilient natural-language constraint normalization, and dual single-cargo + fleet portfolio optimization).

---

## 1. Problem Definition & Operational Tiers

The system solves steel and dry bulk maritime logistics problems across two distinct operational tiers:

### Tier 1: Single-Cargo Tender Optimization (Interactive / Real-Time)
A chartering manager evaluating a specific shipment request (*Cargo Quantity*, *Origin Port*, *Preferred Discharge Ports*, *Timing Flexibility*) requires an integrated, sub-50ms recommendation that solves three interconnected problems simultaneously:
1. **Freight Rate Econometric Forecasting:** Predict forward spot rate curves ($/MT and $/day) across multiple horizons (7, 14, 30, 60 days) under uncertainty.
2. **Berth Physical Compatibility:** Enforce physical draft limits, length overall (LOA), beam, handling discharge rates, tidal windows, and intermediate lightening feasibility.
3. **Chartering Commitment Optimization (Spot vs. Forward Locked):** Solve a Mixed-Integer Linear Program (MILP) deciding:
   - How many voyages to split the parcel into (up to 6 voyages for heavy parcels).
   - Which vessel class (`Capesize`, `Panamax/Kamsarmax`, `Supramax/Ultramax`) and discharge port each voyage uses.
   - When each voyage departs ($\tau$) and its commitment mode (*Spot* vs. *Locked* rate).
   - The resulting 7-bucket cost breakdown and net incremental margin vs. walk-away benchmark.

### Tier 2: Fleet-Wide Portfolio Scheduling (Batch / Multi-Contract)
For fleet operations and periodic reviews across all tracked bulk carriers and an entire slate of pending contracts (`GET /fleet-schedule`):
- Assigns real IMO-tracked vessels to candidate contracts.
- Enforces non-overlapping voyage windows across a temporal conflict graph (preventing double-booking).
- Ranks contracts and generates an optimal **SAIL vs. KILL** schedule maximizing portfolio net margin subject to vessel repositioning speed and ballast distance.

---

## 2. Decision Scope — Data-Driven Warehouse Catalog

Origins, destination ports, and vessel classes are **dynamically resolved from the warehouse**, never hardcoded:

- **Destination Ports:** Loaded from verified rows in `port_constraints` (draft limits, LOA, beam, handling rate TPD, tidal dependency). Added via ingestion with human sign-off (`pending_verification`), requiring zero code changes.
- **Origin Ports:** Loaded from `route_physics` and `rate_history`.
- **Vessel Classes:** Canonical dry bulk classes (`Capesize`, `Panamax/Kamsarmax`, `Supramax/Ultramax`) with verified DWT capacities, laden/ballast fuel consumption, draft, LOA, and beam dimensions in `vessel_specs`.
- **Scope API (`GET /scope`):** Backed by `warehouse/repository.py`, returns live lists of valid origins, ports, and vessel classes. Consumed by API request validation, frontend form dropdowns, and chatbot system prompt grounding.
- **Provenance Tagging:** Placeholders or default values are tagged `assumed` with UI badges, ensuring transparent data honesty.

---

## 3. System Walkthroughs

The system exposes two front-ends (React Dashboard and Decision Assistant Chatbot) sitting on the exact same FastAPI backend engine.

### 3a. Via the Dashboard Form
1. **Manager Input:** Enters **Cargo Quantity** (e.g. 150,000 MT), **Origin Port** (Australia - Hay Point), **Discharge Ports** (Gangavaram, Paradip, Dhamra), and **Timing Flexibility** (30 days). Optional advanced input: *Locked-rate discount benchmark* (default 10%).
2. **API & Scope Validation:** Validates inputs against `GET /scope`.
3. **Constraint Feasibility:** Evaluates berth physical limits per port $\times$ vessel class. For instance, at Dhamra, Capesize LOA ($292\text{m} > 280\text{m}$) is strictly blocked; Panamax ($229\text{m} \le 280\text{m}$) passes.
4. **Forecast Retrieval:** Reads pre-computed `ForecastObject`s containing point estimates, confidence intervals, and scenario trajectories for each feasible route $\times$ vessel class.
5. **Cost Precomputation:** Computes 7-bucket cost coefficients across Base, Bull, and Bear scenarios for every candidate $(v, p, \tau, m)$.
6. **MILP Solve:** PuLP/CBC solves the downside incremental maximization problem in ~35ms.
7. **Response Rendering:** Renders winning plan, 7-bucket stacked cost bar, Base/Bull/Bear fan chart, AIS route map, sensitivity tornado chart, and why-not comparisons.

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

---

## 4. High-Level Architecture

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                 FRONTEND CLIENT LAYER                                  │
│  React 19 + TypeScript + Vite + Recharts + Lucide Icons + apiClient.ts                 │
│  ├─ Dashboard (WhatIfSliders, Interactive Form, WinningPlanBanner, 7-Bucket Cost Grid) │
│  ├─ Scenario Lab (Base / Bull / Bear Fan Chart, Robustness & Regret Readouts)          │
│  ├─ Fleet Schedule (AIS Tracked Carrier Schedule, Repositioning Gantt, SAIL vs KILL)   │
│  ├─ Provenance Explorer & Sensitivity Tornado Panel                                   │
│  └─ Decision Assistant (Natural-Language Chat with Live Tool-Calling & Normalization)   │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │ HTTP JSON (stateless)
┌───────────────────────────────────────────▼────────────────────────────────────────────┐
│                                  FASTAPI BACKEND API                                   │
│  /recommendation   /scenario   /chat   /forecast   /compatible-vessels   /fleet-schedule│
│  ├─ Scope Validator & Natural Language Constraint Normalizer (_normalize_constraints)  │
│  └─ Chat Tool-Calling Proxy (Groq / Nvidia NIM / Anthropic Claude / OpenAI)           │
└─────────────────────┬─────────────────────┬────────────────────┬───────────────────────┘
                      │                     │                    │
┌─────────────────────▼───────┐ ┌───────────▼──────────┐ ┌───────▼───────────────────────┐
│     CONSTRAINT ENGINE       │ │  FORECASTING ENGINE  │ │         COST TERMS            │
│  Deterministic Pure Rules   │ │  Walk-Forward Gated  │ │  7-Bucket OPEX Economics      │
│  ├─ 1. Draft limit          │ │  ├─ Enriched XGBoost │ │  ├─ 1. Ocean Freight (Disc.) │
│  ├─ 2. LOA berth limit      │ │  ├─ Auto-ARIMA       │ │  ├─ 2. Bunker (Physics Dist.) │
│  ├─ 3. Beam limit           │ │  ├─ Naive Baseline   │ │  ├─ 3. OPEX (Daily Vessel)    │
│  ├─ 4. Parcel-fit ratio     │ │  ├─ Damped Fallback  │ │  ├─ 4. Other Voyage (Dues)    │
│  ├─ 5. Handling rate days   │ │  └─ Prophet Additive │ │  ├─ 5. Port Handling          │
│  ├─ 6. Tidal arrival window │ │     Decomposition    │ │  ├─ 6. Lightening Penalty     │
│  ├─ 7. Lightening en-route  │ └───────────┬──────────┘ │  ├─ 7. Tax (Effective 5%)     │
│  └─ 8. Vessel size rank     │             │            └───────┬───────────────────────┘
└─────────────────────┬───────┘             │                    │
                      │                     │                    │
                      └──────────────┬──────┴────────────────────┘
                                     │
┌────────────────────────────────────▼───────────────────────────────────────────────────┐
│                     DECISION OPTIMIZER (MILP via PuLP / CBC)                           │
│  Objective: Maximize Worst-Case Incremental Value  max Σ x * worst_incremental         │
│  Downside Risk Constraint: Σ x * (worst_incremental - 0.60 * base_incremental) >= 0   │
│  Decomposed Variables: q_i (tonnes), x_iv (vessel), y_ip (port), z_it (tau), w_im(mode)│
│  Dynamic Capacity Budgeting: Multi-voyage splits clamped to physical vessel limits     │
│  Fast Fallback: Hybrid Enumeration (<50ms solver timeout safety net)                   │
└────────────────────────────────────┬───────────────────────────────────────────────────┘
                                     │
┌────────────────────────────────────▼───────────────────────────────────────────────────┐
│                           SQLITE / POSTGRES WAREHOUSE                                  │
│  Tables: rate_history, port_constraint, vessel_spec, forecast_object, route_physics,   │
│          exogenous_feature (BDI, Brent, WTI, Iron Ore, BDRY, GSCPI), congestion        │
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
| Route Physics & Distances | Static / Refreshed | Cost terms | Nautical distances (NM), laden/ballast fuel burn, daily OPEX. |
| Operational Evidence | Weekly | Advisory layer | Broker fixture evidence, charterer matching. |

---

## 6. Parameter Usage Map

| Parameter | Originates At | Consumed By | Architectural Role |
|---|---|---|---|
| `cargo_quantity` | Form / Chat / API | Constraint Engine | Evaluated against vessel capacity bands (Rule 4). |
| | | Decision Optimizer | Sized into voyage parcels $\sum q_i = \text{cargo\_quantity}$. |
| `origin_port` | Form / Chat / API | Decision Optimizer | Combined with discharge ports to look up route physics & forecasts. |
| `discharge_ports[]` | Form / Chat / API | Constraint Engine | Checked against berth limits; validated via `GET /scope`. |
| `timing_flexibility_days` | Form / Chat / API | Decision Optimizer | Bounds the fix-date search window $[0, \text{flexibility}]$. |
| `commitment_benchmark_pct` | Form (Advanced) / Chat | Cost Terms | Discount applied to spot rate for locked forward commitments (default 10%). |
| `bunker_price_usd` | Ingestion / DB | Cost Terms | Multiplied by distance fuel consumption to price bunker cost. |
| `daily_opex_usd` | Route Physics / DB | Cost Terms | Multiplied by voyage days to compute operating expenses. |
| `vessel_positions` | AIS Feed / DB | Fleet Schedule | Determines ballast repositioning feasibility and earliest departure. |

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
2. **Bunker Cost (Physics):**
   - $\text{Voyage Days} = \frac{\text{Distance NM}}{24 \times \text{Speed Knots}} + \text{Discharge Days} + \text{Lightening Days}$.
   - $\text{Bunker Cost} = (\text{Laden Consumption TPD} \times \text{Voyage Days}) \times \text{Bunker Price USD/MT}$.
3. **OPEX Cost:** $\text{Daily OPEX USD} \times \text{Voyage Days}$ ($\$8,500/\text{day}$ Capesize, $\$7,200/\text{day}$ Panamax, $\$6,500/\text{day}$ Supramax).
4. **Other Voyage Costs:** Port dues, canal tolls, pilotage from `RoutePhysics`.
5. **Port Handling:** Port handling tariff $\times \text{Cargo Quantity}$.
6. **Lightening Extra:** Added anchorage and port charges when lightening is required.
7. **Tax Cost:** Exact $5.0\%$ applied to the **effective post-discount ocean freight cost**.

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
- Needed voyages: $\text{Needed} = \max\left(1, \lceil \frac{\text{Cargo Quantity}}{\text{Max Feasible Vessel Capacity}} \rceil\right)$.
- Max voyages allowed: $\min(6, \text{Needed})$.
- Handles heavy parcels at restricted ports (e.g., 300,000 MT at Dhamra solves as 4 Panamax voyages: $60\text{k} + 80\text{k} + 80\text{k} + 80\text{k}$).

### 11.5 Human Overrides & Alias Normalization
Supports:
- `allow_vessel: ["Capesize"]` / `require_vessel: "Capesize"`
- `exclude_vessel: ["Panamax/Kamsarmax"]`
- `require_port: "Gangavaram"`
- `force_mode: "locked"`
- `min_fix_day: 14`, `max_completion_day: 30`

---

## 12. Provenance & Explainability Layer

- Every figure returned by the API carries a typed `provenance` tag (`measured`, `modeled`, `assumed`).
- **Sensitivity Tornado Analysis:** Perturbs assumptions ($\pm 10\%$ commitment discount, bunker prices, port handling rates) to compute impact on total cost without re-solving the MILP.
- **Robustness Score:** Measures spread between Base and Worst-case scenario costs.

---

## 13. Fleet Portfolio Scheduling (Step 51V)

Available via `GET /fleet-schedule`:
- Solves multi-contract, multi-vessel temporal assignments across tracked bulk carriers.
- Builds a temporal conflict graph ($10,890$ potential collision edges) preventing overlapping fixtures.
- Generates a visual Gantt schedule classifying contracts as **SAIL** (accepted) vs. **KILL** (rejected).

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
| `GET` | `/fleet-schedule` | Multi-vessel fleet schedule and Gantt data. |
| `GET` | `/scope` | Live valid origins, discharge ports, and vessel classes. |
| `GET` | `/health` | Warehouse reachability and model freshness. |

---

## 16. Frontend Presentation Components

1. **WhatIfSliders:** Reactive sliders for cargo quantity, timing flexibility, and discount benchmark.
2. **WinningPlanBanner:** Summary of optimal voyage count, ports, vessels, and worst-case cost.
3. **7-Bucket Cost Breakdown Grid:** Interactive visual bar and table detailing Ocean Freight, Bunker, OPEX, Other Costs, Port Handling, Lightening, and Tax.
4. **Scenario Fan Chart:** Recharts visualization of Base, Bull, and Bear forecast curves with marked fix dates ($\tau$).
5. **AIS Route & Repositioning Map:** Map displaying load/discharge ports, vessel positions, and congestion status.
6. **WhyNotComparator:** Side-by-side diagnostic comparison between winning plan and alternative candidate options.
7. **Executive Brief Export:** One-page summary export for chartering executives.

---

## 17. Non-Functional Performance Standards

- **Solver Latency:** $<50\text{ms}$ for standard MILP solves (timeout threshold: $4.0\text{s}$).
- **Database Query Latency:** $<10\text{ms}$ via indexed SQLite / PostgreSQL.
- **Stateless API:** Zero server-side session state for chat and recommendation requests.
- **Frontend Responsiveness:** $<300\text{ms}$ debounced re-render during slider adjustments.

---

## 18. Data Quality & Model Gating Checklist

- **Schema Validation:** Strict Pydantic models for all API payloads.
- **Port Safety Sign-off:** Changes to berth draft or LOA limits require verified human sign-off.
- **Walk-Forward Out-of-Sample Gate:** Models must beat naive random-walk on rolling tests.
- **Freshness Alerts:** Stale AIS congestion data ($>48\text{h}$) is flagged explicitly.

---

## 19. Risk Register & Mitigations

| Risk | Mitigation |
|---|---|
| Berth draft/LOA inaccuracies causing grounding | Strict deterministic rules; physical hard-blocks on LOA/draft; manual verification gate. |
| Freight market volatility & geopolitical shocks | 3-scenario fan bands; downside risk ratio constraint; Damped-trend fallback. |
| Large parcel infeasibility at restricted ports | Dynamic capacity budgeting splitting up to 6 voyages; physical capacity clamping. |
| Chatbot hallucination of rates or ship names | System prompt live scope injection; fuzzy constraint normalizer; strict verbatim tool grounding. |
| AIS data feed disruption | Graceful degradation to calendar-based $\tau$ points; UI alerts for stale congestion. |

---

## 20. System Constants & Defaults

- `TAX_RATE_PCT = 5.0%` (computed on effective post-discount ocean freight).
- `DEFAULT_COMMITMENT_BENCHMARK_PCT = 10.0%` (locked discount vs. spot).
- `MILP_RISK_RATIO = 0.60` (minimum acceptable worst-to-base incremental ratio).
- `LIGHTENING_PENALTY_DAYS = 2.5` & `LIGHTENING_PENALTY_COST_USD = $75,000`.
- `DEFAULT_BALLAST_SPEED_KTS = 12.0` & `DEFAULT_SAFETY_BUFFER_HOURS = 6.0`.
- Typical Capacities: Capesize ($180\text{k}\text{ MT}$), Panamax/Kamsarmax ($75\text{k}$–$80\text{k}\text{ MT}$), Supramax/Ultramax ($58\text{k}\text{ MT}$).
