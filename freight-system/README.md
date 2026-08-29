# FrieghtCast — Intelligent Freight Forecasting & Chartering (SAIL PS3)

Jointly solves rate forecasting, port/vessel feasibility, and spot-vs-locked chartering
strategy — instead of treating them as three separate tools.

## What this system does

Takes a cargo request (quantity, origin, discharge ports, timing flexibility) and returns
a ranked chartering strategy — how many voyages, which vessel and port each uses, when
each is fixed, and spot vs. locked commitment mix — solved jointly via a MILP optimizer
against forecast uncertainty.

## Stack

| Layer | Technology |
|---|---|
| Backend API | FastAPI (Python) |
| MILP Solver | PuLP + CBC |
| Database | PostgreSQL (TimescaleDB extension) |
| Ingestion | APScheduler (batch) + persistent AIS WebSocket |
| Frontend | React + Recharts (Vite + TypeScript) |
| Chatbot | Anthropic Claude API, tool-calling |
| Deployment | Render (backend) + Vercel (frontend) |

## Project structure

See `DOC3.md §1` for the full annotated folder tree.

## Architecture

```
React dashboard + chatbot
  → FastAPI (/recommendation, /forecast, /scenario, …)
    → {Constraint engine, Scenario Generator, MILP Decision Engine}
      → warehouse/repository.py
        → PostgreSQL (populated by scheduled batch + live AIS ingestion)
```

## Core rules

- `engine/` never imports from `api/`, `ingestion/`, or `frontend/`.
- All warehouse access routes through `warehouse/repository.py` — no raw SQL elsewhere.
- All frontend → backend calls go through `frontend/src/lib/apiClient.ts`.
- Every number the API returns carries a `provenance` tag (measured / modeled / assumed).
- MILP decision variables stay decomposed: `q_i, x_iv, y_ip, z_iτ, w_im, ℓ_ip` — never
  folded into one joint index.

## Getting started

```bash
cp .env.example .env
# fill in DATABASE_URL, AISSTREAM_API_KEY, ANTHROPIC_API_KEY, MYSHIPTRACKING_API_KEY, OILPRICEAPI_API_KEY

# Backend
pip install -r requirements.txt
uvicorn backend.api.main:app --reload

# Frontend
cd frontend
npm install
npm run dev
```

## Build order

See `DOC4.md §4.1` for the full 15-step build sequence.
