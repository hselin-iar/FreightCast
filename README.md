# FreightCast — Intelligent Freight Forecasting & Chartering (SAIL PS3)

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688.svg)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-19-61DAFB.svg)](https://react.dev)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.0+-3178C6.svg)](https://www.typescriptlang.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**FreightCast** is an end-to-end maritime intelligence and chartering optimization platform built for dry bulk steelmaking supply chains (e.g. SAIL PS3). It unifies econometric freight rate forecasting, physical berth compatibility rules, 7-bucket vessel operating cost economics, and a mixed-integer linear programming (MILP) optimization engine with sub-50ms latency.

---

## Key Features

1. **Integrated Tender Optimization (MILP):**
   - Solves for optimal voyage count splits, vessel class allocations (`Capesize`, `Panamax/Kamsarmax`, `Supramax/Ultramax`), discharge port selection, and fixture dates ($\tau$).
   - Formulates a **Sail vs. Kill** incremental value objective with a $60\%$ downside portfolio risk constraint.
   - Recommends the optimal Spot vs. Locked commitment mix against market uncertainty.

2. **Berth Physical Compatibility Engine:**
   - 8 deterministic rules enforcing draft limits, LOA, beam, handling discharge rates, tidal windows, and intermediate lightening routing.

3. **7-Bucket OPEX-Integrated Cost Model:**
   - Evaluates Ocean Freight (post-discount), Bunker Fuel physics, Daily Vessel OPEX, Port Dues/Tolls, Port Handling Tariffs, Lightening Charges, and Tax ($5.0\%$).

4. **Multi-Model Econometric Forecasting:**
   - Enriched XGBoost with macroeconomic features (BDI, Brent, WTI, Iron Ore 62% Fe, BDRY, GSCPI, Bunker VLSFO/MGO) + Auto-ARIMA baseline + Prophet additive decomposition for trend and seasonal explainability.
   - Walk-forward rolling backtest gating.

5. **Decision Assistant (Chatbot):**
   - Natural-language conversational proxy with live database scope injection and automatic alias normalization (`"Cape Max"` $\to$ `"Capesize"`).
   - Zero-hallucination policy with strict tool-calling grounding.

6. **Batch Fleet Portfolio Scheduling:**
   - Solves multi-contract, multi-vessel temporal assignments across AIS-tracked bulk carriers with collision avoidance ($10,890$ temporal conflict edges).

---

## System Architecture

```
┌──────────────────────────────────────────────────────────┐
│                   React 19 + Vite Frontend               │
│  Interactive Sliders · 7-Bucket Cost Grid · Fan Chart    │
│  AIS Route Map · Sensitivity Tornado · Decision Assistant│
└────────────────────────────┬─────────────────────────────┘
                             │ HTTP JSON
┌────────────────────────────▼─────────────────────────────┐
│                   FastAPI Backend API                    │
│  /recommendation  /scenario  /chat  /forecast  /schedule │
└──────────────┬─────────────────────────────┬─────────────┘
               │                             │
┌──────────────▼─────────────┐ ┌─────────────▼─────────────┐
│      Constraint Engine     │ │   Forecasting Engine      │
│  8 Deterministic Rules     │ │   XGBoost + Auto-ARIMA    │
└──────────────┬─────────────┘ └─────────────┬─────────────┘
               │                             │
               └──────────────┬──────────────┘
                              │
┌─────────────────────────────▼────────────────────────────┐
│              Decision Engine (MILP via PuLP/CBC)         │
│  Objective: Maximize Downside Worst-Case Incremental     │
│  Downside Risk Ratio: worst >= 0.60 * base               │
└─────────────────────────────┬────────────────────────────┘
                              │
┌─────────────────────────────▼────────────────────────────┐
│                    Database Warehouse                    │
│  SQLite / PostgreSQL (Rate History, Port Specs, AIS)     │
└──────────────────────────────────────────────────────────┘
```

---

## Directory Structure

```
.
├── DOC2.md                # Technical Architecture & Formulations (v4 Production)
├── DOC3.md                # System Interfaces, Data Models & Deployment Spec
├── DOC4.md                # Build Steps & Verification Protocol
├── AGENTS.md              # Agent Session State & Rules
├── freight-system/        # Production Web Application
│   ├── backend/           # FastAPI Application & Engines
│   │   ├── api/           # REST Routes & Pydantic Schemas
│   │   ├── engine/        # Constraint, Cost Terms, Decision (MILP), Scenario
│   │   ├── forecasting/   # Econometric Models & Pipelines
│   │   ├── ingestion/     # Market & AIS Data Ingestion
│   │   ├── warehouse/     # SQLAlchemy ORM Models & Repository
│   │   └── tests/         # Complete 277-Test Regression Suite
│   ├── frontend/          # React 19 + TypeScript + Vite UI
│   │   ├── src/           # Components, Pages, State, API Client
│   │   └── package.json   # Node Dependencies
│   ├── scripts/           # Integration & Benchmarking Scripts
│   ├── requirements.txt   # Python Dependencies
│   ├── freight_dev.db     # Seeded SQLite Development Database
│   └── .env.example       # Environment Configuration Template
└── freight_optimization/  # Offline Research & Mathematical Proofs
```

---

## Quickstart Guide

### 1. Prerequisites
- Python 3.9+
- Node.js 18+ and npm

### 2. Backend Setup
```bash
cd freight-system

# Create environment configuration
cp .env.example .env

# Install Python dependencies
pip install -r requirements.txt

# Start FastAPI server
uvicorn backend.api.main:app --host 127.0.0.1 --port 8000 --reload
```
The API is live at `http://localhost:8000` (Swagger docs at `http://localhost:8000/docs`).

### 3. Frontend Setup
```bash
cd freight-system/frontend

# Install dependencies
npm install

# Start Vite dev server
npm run dev
```
The application is live at `http://localhost:5173`.

### 4. Running the Test Suite
```bash
cd freight-system
pytest backend/tests/
```
All **277 unit and integration tests** should pass.

---

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
