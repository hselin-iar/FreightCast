"""
api/main.py — FastAPI application entry point.

DOC3 §FEATURE: API Layer
DOC2 §15

DESIGN DECISIONS:
  - CORS: separate frontend origin (Vercel) needs explicit CORS allow-list.
    FRONTEND_ORIGINS env var controls this — defaults to localhost:5173 (Vite dev).
  - Exception handling: single handler per exception type; no raw tracebacks
    ever reach the frontend.  WarehouseUnavailableError → 503 specifically.
  - All six routes are thin pass-throughs registered here — no business logic
    in route handlers.
  - Startup: does NOT train or retrain forecasting models (DOC3 §0 decision —
    training only happens via the scheduled entrypoint).
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api.routes import (
    chat,
    compatible_vessels,
    fleet_schedule,
    forecast,
    health,
    port_status,
    recommendation,
    scenario,
    scope,
    vessels,
)
from backend.warehouse.db import WarehouseUnavailableError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup: log readiness, verify warehouse connection non-fatally.
    Shutdown: clean up.
    Note: forecasting models are NOT retrained here — only from scheduler.py.
    """
    logger.info("FrieghtCast API starting up.")

    # Non-fatal warehouse check at startup — API starts even if DB is unavailable
    # (so /health can still report the degraded state properly)
    try:
        from backend.warehouse import repository
        repository.get_valid_vessel_classes()
        logger.info("Warehouse connection verified on startup.")
    except Exception as exc:
        logger.warning("Warehouse unavailable at startup — /health will report 'error': %s", exc)

    yield  # app is running

    logger.info("FrieghtCast API shutting down.")


app = FastAPI(
    title="FrieghtCast — Intelligent Freight Forecasting & Chartering",
    description=(
        "SAIL PS3: Decision Engine + Forecasting + Provenance. "
        "POST /recommendation for a full chartering strategy. "
        "GET /health for readiness. "
        "GET /scope for live origin/port/vessel scope."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# CORS — allow Vercel frontend + local Vite dev server across any port
# ---------------------------------------------------------------------------

_default_origins = [
    "http://localhost:5173",
    "http://localhost:5174",
    "http://localhost:5175",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
    "http://127.0.0.1:5175",
    "http://127.0.0.1:3000",
]
_env_origins = [
    o.strip()
    for o in os.environ.get("FRONTEND_ORIGINS", "").split(",")
    if o.strip()
]
_allowed_origins = list(set(_default_origins + _env_origins))

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?|https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Exception handlers — no raw tracebacks to frontend
# ---------------------------------------------------------------------------

@app.exception_handler(WarehouseUnavailableError)
async def warehouse_unavailable_handler(
    request: Request, exc: WarehouseUnavailableError
) -> JSONResponse:
    """503 for warehouse connectivity issues — distinct from other 500s."""
    logger.error("WarehouseUnavailableError on %s: %s", request.url.path, exc)
    return JSONResponse(
        status_code=503,
        content={"detail": f"Warehouse unavailable: {exc}"},
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all: log full traceback, return generic 500 without exposing internals."""
    logger.exception("Unhandled exception on %s", request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal error occurred. Check server logs."},
    )


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------

app.include_router(recommendation.router, tags=["Recommendation"])
app.include_router(chat.router,           tags=["Chat"])
app.include_router(scenario.router,       tags=["Scenario"])
app.include_router(forecast.router,       tags=["Forecast"])
app.include_router(compatible_vessels.router, tags=["Compatible Vessels"])
app.include_router(port_status.router,    tags=["Port Status"])
app.include_router(scope.router,          tags=["Scope"])
app.include_router(health.router,         tags=["Health"])
app.include_router(fleet_schedule.router,  tags=["Fleet Schedule (Step 51V)"])
app.include_router(vessels.router,        tags=["Vessels"])
