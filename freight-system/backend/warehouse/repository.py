"""
warehouse/repository.py — the ONLY module in the codebase allowed to construct
SQLAlchemy queries.

DOC3 §FEATURE: Data Warehouse → repository.py
AGENTS.md Agentic Coding Rules:
  "Route all warehouse access through /backend/warehouse/repository.py —
   no raw SQL or SQLAlchemy queries anywhere else in the codebase."

Every other module calls a typed function from here. No exceptions.

Build Step 3: all functions implemented.
The three get_valid_*() scope functions are cached for SCOPE_CATALOG_CACHE_TTL_SECONDS.
"""
from __future__ import annotations

import json
import logging
import math
import time
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import desc, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from backend.config.constants import (
    DEFAULT_BALLAST_SPEED_KNOTS,
    SCOPE_CATALOG_CACHE_TTL_SECONDS,
)
from backend.ingestion.types import IngestResult
from backend.warehouse.db import get_session
from backend.warehouse.models import (
    CongestionSnapshot,
    ExogenousFeature,
    ForecastObject,
    OperationalEvidence,
    PortConstraint,
    RateHistory,
    RoutePhysics as RoutePhysicsModel,
    VesselPositionSnapshot,
    VesselSpec,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Scope Catalog cache (DOC2 Addendum v3 §A1)
# get_valid_*() are cheap distinct-value queries cached for TTL_SECONDS so they
# don't add a query to every request, but reflect new sign-offs within minutes.
# ---------------------------------------------------------------------------
_scope_cache: dict[str, tuple[list[str], float]] = {}   # key → (values, expires_at)


def _cached_scope(key: str, query_fn) -> list[str]:
    now = time.monotonic()
    if key in _scope_cache:
        values, expires = _scope_cache[key]
        if now < expires:
            return values
    values = query_fn()
    _scope_cache[key] = (values, now + SCOPE_CATALOG_CACHE_TTL_SECONDS)
    return values


def get_valid_origins() -> list[str]:
    """
    Return verified origin names from VesselPositionSnapshot loading regions.
    Falls back to DEV_FIXTURE_ORIGINS if warehouse is empty (cold start).
    DOC2 Addendum v3 §A1.
    """
    def _query() -> list[str]:
        from backend.config.constants import DEV_FIXTURE_ORIGINS
        with get_session() as session:
            rows = session.execute(
                select(PortConstraint.name)
                .where(PortConstraint.verified == True)  # noqa: E712
            ).scalars().all()
            # Origins come from the port_constraint table's source-port dimension
            # (verified port rows are both origins and destinations in this system).
            # For now return DEV_FIXTURE_ORIGINS if no verified rows exist.
            return list(rows) if rows else list(DEV_FIXTURE_ORIGINS)

    return _cached_scope("origins", _query)


def get_valid_dest_ports() -> list[str]:
    """
    Return verified destination port names (verified PortConstraint rows).
    Falls back to DEV_FIXTURE_PORTS if warehouse is empty (cold start).
    DOC2 Addendum v3 §A1.
    """
    def _query() -> list[str]:
        from backend.config.constants import DEV_FIXTURE_DEST_PORTS
        with get_session() as session:
            rows = session.execute(
                select(PortConstraint.name)
                .where(PortConstraint.verified == True)  # noqa: E712
            ).scalars().all()
            return list(rows) if rows else list(DEV_FIXTURE_DEST_PORTS)


    return _cached_scope("dest_ports", _query)


def get_valid_routes() -> list[str]:
    """
    Return all valid route strings (e.g. 'Australia (Hay Point)→Paradip') from RateHistory / RoutePhysics.
    """
    def _query() -> list[str]:
        with get_session() as session:
            rows = session.execute(
                select(RateHistory.route).distinct()
            ).scalars().all()
            if rows:
                return list(rows)
            rp_rows = session.execute(select(RoutePhysicsModel)).scalars().all()
            return [f"{r.origin}→{r.destination}" for r in rp_rows]

    return _cached_scope("trade_routes", _query)


def get_valid_vessel_classes() -> list[str]:
    """
    Return verified vessel class names from VesselSpec.
    DOC2 Addendum v3 §A1.
    """
    def _query() -> list[str]:
        from backend.config.constants import DEV_FIXTURE_VESSEL_CLASSES
        with get_session() as session:
            rows = session.execute(
                select(VesselSpec.class_name)
            ).scalars().all()
            return list(rows) if rows else list(DEV_FIXTURE_VESSEL_CLASSES)

    return _cached_scope("vessel_classes", _query)


def invalidate_scope_cache() -> None:
    """Force scope cache refresh on next call. Call after human sign-off on new port."""
    _scope_cache.clear()


# ---------------------------------------------------------------------------
# Write path — RateHistory
# ---------------------------------------------------------------------------

def upsert_rate_history(rows: list[dict[str, Any]]) -> IngestResult:
    """
    Upsert validated rate history rows.
    On conflict (route, vessel_class, date): update rate, tier, source.
    """
    if not rows:
        return IngestResult(source="rate_history", rows_ingested=0, rows_rejected=0)

    ingested = 0
    rejected = 0
    with get_session() as session:
        for row in rows:
            try:
                date_val = row.get("date")
                if isinstance(date_val, str):
                    date_val = datetime.fromisoformat(date_val)
                elif hasattr(date_val, "year") and not hasattr(date_val, "hour"):  # datetime.date instance
                    date_val = datetime.combine(date_val, datetime.min.time())
                if date_val and getattr(date_val, "tzinfo", None) is None:
                    date_val = date_val.replace(tzinfo=timezone.utc)

                existing = session.execute(
                    select(RateHistory).where(
                        RateHistory.route == str(row.get("route", "")),
                        RateHistory.vessel_class == str(row.get("vessel_class", "")),
                        RateHistory.date == date_val,
                    )
                ).scalar_one_or_none()

                if existing:
                    existing.rate = float(row["rate"])
                    existing.tier = row.get("tier")
                    existing.source = str(row.get("provenance", row.get("source", "measured")))
                else:
                    session.add(RateHistory(
                        route=str(row.get("route", "")),
                        vessel_class=str(row.get("vessel_class", "")),
                        date=date_val,
                        rate=float(row["rate"]),
                        tier=row.get("tier"),
                        source=str(row.get("provenance", row.get("source", "measured"))),
                    ))
                ingested += 1
            except Exception as exc:
                logger.warning("upsert_rate_history: skipped row (%s): %s", row, exc)
                rejected += 1

    return IngestResult(
        source="rate_history",
        rows_ingested=ingested,
        rows_rejected=rejected,
    )


# ---------------------------------------------------------------------------
# Write path — PortConstraint (pending verification)
# ---------------------------------------------------------------------------

def upsert_port_constraint_pending(rows: list[dict[str, Any]]) -> int:
    """
    Upsert port constraint rows with verified=False (pending human sign-off).
    Returns count of rows written to pending state.
    DOC3 hard requirement: never write verified=True from ingestion code.
    """
    written = 0
    with get_session() as session:
        for row in rows:
            name = str(row.get("port_name", ""))
            if not name:
                continue
            existing = session.execute(
                select(PortConstraint).where(PortConstraint.name == name)
            ).scalar_one_or_none()

            if existing:
                # Update physical values; keep verified status as-is
                existing.max_draft_m = float(row.get("max_draft_m", existing.max_draft_m))
                existing.max_loa_m = float(row.get("max_loa_m", existing.max_loa_m))
                existing.max_beam_m = float(row.get("max_beam_m", existing.max_beam_m))
                existing.handling_rate_tpd = float(row.get("handling_rate_tpd", existing.handling_rate_tpd))
                td = row.get("tidal_dependent", "false")
                existing.tidal_dependent = td in (True, "true", "True", 1)
                existing.updated_at = datetime.now(timezone.utc)
            else:
                td = row.get("tidal_dependent", "false")
                session.add(PortConstraint(
                    name=name,
                    max_draft_m=float(row.get("max_draft_m", 0)),
                    max_loa_m=float(row.get("max_loa_m", 0)),
                    max_beam_m=float(row.get("max_beam_m", 0)),
                    handling_rate_tpd=float(row.get("handling_rate_tpd", 0)),
                    tidal_dependent=td in (True, "true", "True", 1),
                    verified=False,   # ALWAYS false from ingestion
                    source="assumed",
                    updated_at=datetime.now(timezone.utc),
                ))
            written += 1
    return written


def approve_port_constraint(port_name: str) -> bool:
    """
    Human sign-off: flip verified=True for a pending port constraint.
    Invalidates the scope cache so get_valid_dest_ports() reflects the change.
    Returns True if the port was found and approved.
    """
    with get_session() as session:
        row = session.execute(
            select(PortConstraint).where(PortConstraint.name == port_name)
        ).scalar_one_or_none()
        if row is None:
            return False
        row.verified = True
        row.updated_at = datetime.now(timezone.utc)
    invalidate_scope_cache()
    logger.info("Port constraint approved: %s", port_name)
    return True


# ---------------------------------------------------------------------------
# Write path — VesselSpec
# ---------------------------------------------------------------------------

def upsert_vessel_spec(rows: list[dict[str, Any]]) -> int:
    """Upsert vessel class specs. Returns count written."""
    written = 0
    with get_session() as session:
        for row in rows:
            class_name = str(row.get("vessel_class", ""))
            if not class_name:
                continue
            existing = session.execute(
                select(VesselSpec).where(VesselSpec.class_name == class_name)
            ).scalar_one_or_none()
            if existing:
                existing.typical_capacity_tonnes = float(row.get("capacity_tonnes", existing.typical_capacity_tonnes))
                existing.draft_m = float(row.get("draft_m", existing.draft_m))
                existing.loa_m = float(row.get("loa_m", existing.loa_m))
                existing.beam_m = float(row.get("beam_m", existing.beam_m))
            else:
                session.add(VesselSpec(
                    class_name=class_name,
                    typical_capacity_tonnes=float(row.get("capacity_tonnes", 0)),
                    draft_m=float(row.get("draft_m", 0)),
                    loa_m=float(row.get("loa_m", 0)),
                    beam_m=float(row.get("beam_m", 0)),
                ))
            written += 1
            invalidate_scope_cache()
    return written


# ---------------------------------------------------------------------------
# Write path — ExogenousFeature
# ---------------------------------------------------------------------------

def upsert_exogenous_feature(rows: list[dict[str, Any]]) -> int:
    """Upsert macro feature rows keyed by (source, date). Returns count written."""
    written = 0
    with get_session() as session:
        for row in rows:
            source = str(row.get("source", ""))
            date_val = row.get("date")
            if not source or date_val is None:
                continue
            if isinstance(date_val, str):
                date_val = datetime.fromisoformat(date_val)
            elif hasattr(date_val, "year") and not hasattr(date_val, "hour"):
                date_val = datetime.combine(date_val, datetime.min.time())
            if date_val and getattr(date_val, "tzinfo", None) is None:
                date_val = date_val.replace(tzinfo=timezone.utc)

            existing = session.execute(
                select(ExogenousFeature).where(
                    ExogenousFeature.source == source,
                    ExogenousFeature.date == date_val,
                )
            ).scalar_one_or_none()
            if existing:
                existing.value = float(row["value"])
            else:
                session.add(ExogenousFeature(
                    source=source,
                    date=date_val,
                    value=float(row.get("value", 0)),
                ))
            written += 1
    return written


# ---------------------------------------------------------------------------
# Write path — OperationalEvidence
# ---------------------------------------------------------------------------

def upsert_operational_evidence(rows: list[dict[str, Any]]) -> int:
    """Upsert operational evidence rows. Returns count written."""
    written = 0
    with get_session() as session:
        for row in rows:
            route = str(row.get("route", ""))
            vessel_class = str(row.get("vessel_class", ""))
            observed_at = row.get("observed_at")
            if not route or not vessel_class or observed_at is None:
                continue
            if isinstance(observed_at, str):
                observed_at = datetime.fromisoformat(observed_at)
            if observed_at.tzinfo is None:
                observed_at = observed_at.replace(tzinfo=timezone.utc)

            session.add(OperationalEvidence(
                route=route,
                vessel_class=vessel_class,
                observed_at=observed_at,
                note=str(row.get("note", "")),
                confidence_score=None,  # computed by evidence.py in Step 9.5
            ))
            written += 1
    return written


# ---------------------------------------------------------------------------
# Write path — CongestionSnapshot
# ---------------------------------------------------------------------------

def write_congestion_snapshot(port: str, snapshot: dict[str, Any]) -> None:
    """
    Write a new CongestionSnapshot row for port.
    Called by ais_listener.py on each geofence event.
    The special port key 'bunker' is used to store the current VLSFO price
    (bunker_price_usd field); all other port keys record AIS congestion data.
    """
    recorded_at = snapshot.get("recorded_at") or datetime.now(timezone.utc)
    if isinstance(recorded_at, str):
        recorded_at = datetime.fromisoformat(recorded_at)
    if recorded_at.tzinfo is None:
        recorded_at = recorded_at.replace(tzinfo=timezone.utc)

    bunker_price = snapshot.get("bunker_price_usd")
    if bunker_price is not None:
        bunker_price = float(bunker_price)

    with get_session() as session:
        session.add(CongestionSnapshot(
            port=port,
            vessel_count=int(snapshot.get("vessel_count", 0)),
            avg_wait_hours=float(snapshot.get("avg_wait_hours", 0.0)),
            recorded_at=recorded_at,
            is_live=bool(snapshot.get("is_live", True)),
            source_note=str(snapshot.get("source_note", "live AIS stream")),
            bunker_price_usd=bunker_price,
        ))
    logger.debug("write_congestion_snapshot: port=%s, vessel_count=%d", port, snapshot.get("vessel_count", 0))


# ---------------------------------------------------------------------------
# Write path — VesselPositionSnapshot
# ---------------------------------------------------------------------------

def upsert_vessel_position_snapshot(snapshot: dict[str, Any]) -> None:
    """
    Upsert a VesselPositionSnapshot row keyed by IMO.
    Called by both ais_listener.py (continuous stream) and
    vessel_position_ingest.py (batch/backfill). Both write through here.
    DOC3 §FEATURE: Data Warehouse.
    """
    imo = int(snapshot.get("imo", 0))
    if not imo:
        return

    recorded_at = snapshot.get("recorded_at") or datetime.now(timezone.utc)
    if isinstance(recorded_at, str):
        recorded_at = datetime.fromisoformat(recorded_at)
    if recorded_at.tzinfo is None:
        recorded_at = recorded_at.replace(tzinfo=timezone.utc)

    with get_session() as session:
        existing = session.execute(
            select(VesselPositionSnapshot).where(VesselPositionSnapshot.imo == imo)
        ).scalar_one_or_none()

        if existing:
            existing.vessel_name = str(snapshot.get("vessel_name", existing.vessel_name))
            existing.vessel_class = str(snapshot.get("vessel_class", existing.vessel_class))
            existing.dwt = float(snapshot.get("dwt", existing.dwt))
            existing.current_lat = float(snapshot.get("current_lat", existing.current_lat))
            existing.current_lon = float(snapshot.get("current_lon", existing.current_lon))
            existing.speed_knots = float(snapshot.get("speed_knots", existing.speed_knots))
            existing.recorded_at = recorded_at
        else:
            session.add(VesselPositionSnapshot(
                imo=imo,
                vessel_name=str(snapshot.get("vessel_name", "")),
                vessel_class=str(snapshot.get("vessel_class", "")),
                dwt=float(snapshot.get("dwt", 0.0)),
                current_lat=float(snapshot.get("current_lat", 0.0)),
                current_lon=float(snapshot.get("current_lon", 0.0)),
                speed_knots=float(snapshot.get("speed_knots", 0.0)),
                recorded_at=recorded_at,
            ))


# ---------------------------------------------------------------------------
# Write path — ForecastObject
# ---------------------------------------------------------------------------

def write_forecast(obj: dict[str, Any]) -> None:
    """
    Persist a ForecastObject. Called by forecasting.py's train_and_evaluate().
    One row per (route, vessel_class, horizon_days, generated_at).
    """
    generated_at = obj.get("generated_at") or datetime.now(timezone.utc)
    if isinstance(generated_at, str):
        generated_at = datetime.fromisoformat(generated_at)
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=timezone.utc)

    with get_session() as session:
        session.add(ForecastObject(
            route=str(obj["route"]),
            vessel_class=str(obj["vessel_class"]),
            horizon_days=int(obj["horizon_days"]),
            generated_at=generated_at,
            point_estimate=float(obj["point_estimate"]),
            confidence_band=json.dumps(obj.get("confidence_band", {})),
            trajectory=json.dumps(obj.get("trajectory", [])),
            driver_explanation=obj.get("driver_explanation"),
            is_high_uncertainty=bool(obj.get("is_high_uncertainty", False)),
            model_used=str(obj.get("model_used", "naive")),
        ))
    logger.info(
        "write_forecast: route=%s, vessel_class=%s, horizon=%d, model=%s",
        obj["route"], obj["vessel_class"], obj["horizon_days"], obj.get("model_used"),
    )


# ---------------------------------------------------------------------------
# Read path — ForecastObject
# ---------------------------------------------------------------------------

def get_latest_forecast(
    route: str,
    vessel_class: str,
    horizon_days: int,
) -> Optional[ForecastObject]:
    """
    Return the most recently generated ForecastObject for (route, vessel_class,
    horizon_days), or None if no gated forecast exists yet.

    Falls back to the closest available horizon_days when an exact match is
    unavailable (e.g. DB seeded with 30-day forecasts, caller passes 45).
    Hot read path — uses the composite index on (route, vessel_class, horizon_days,
    generated_at DESC).
    DOC3: get_forecast() raises ForecastUnavailableError when this returns None.
    """
    with get_session() as session:
        # 1. Try exact horizon_days match first
        row = session.execute(
            select(ForecastObject)
            .where(
                ForecastObject.route == route,
                ForecastObject.vessel_class == vessel_class,
                ForecastObject.horizon_days == horizon_days,
            )
            .order_by(desc(ForecastObject.generated_at))
            .limit(1)
        ).scalar_one_or_none()
        if row is not None:
            return row

        # 2. Fuzzy fallback: pick the row with the closest horizon_days
        #    (prefer the largest available horizon that is ≤ requested, then
        #    the smallest available horizon > requested)
        rows = session.execute(
            select(ForecastObject)
            .where(
                ForecastObject.route == route,
                ForecastObject.vessel_class == vessel_class,
            )
            .order_by(desc(ForecastObject.generated_at))
        ).scalars().all()
        if not rows:
            return None

        # Deduplicate by horizon_days — keep the latest generated for each
        seen: dict = {}
        for r in rows:
            if r.horizon_days not in seen:
                seen[r.horizon_days] = r

        # Pick closest horizon
        best = min(seen.values(), key=lambda r: abs(r.horizon_days - horizon_days))
        return best


# ---------------------------------------------------------------------------
# Read path — RateHistory
# ---------------------------------------------------------------------------

def get_rate_history(
    route: str,
    vessel_class: str,
    limit: int = 180,
) -> list[dict[str, Any]]:
    """
    Return recent RateHistory rows for (route, vessel_class) in descending date order.
    Returns list of dicts with keys: id, route, vessel_class, date, rate.
    """
    with get_session() as session:
        rows = session.execute(
            select(RateHistory)
            .where(
                RateHistory.route == route,
                RateHistory.vessel_class == vessel_class,
            )
            .order_by(desc(RateHistory.date))
            .limit(limit)
        ).scalars().all()
        return [
            {
                "id": r.id,
                "route": r.route,
                "vessel_class": r.vessel_class,
                "date": r.date,
                "rate": float(r.rate),
            }
            for r in rows
        ]


# ---------------------------------------------------------------------------
# Read path — PortConstraint
# ---------------------------------------------------------------------------

def get_port_constraints(verified_only: bool = True) -> dict[str, PortConstraint]:
    """
    Return port constraints keyed by port name.
    verified_only=True (default): only human-approved rows.
    """
    with get_session() as session:
        query = select(PortConstraint)
        if verified_only:
            query = query.where(PortConstraint.verified == True)  # noqa: E712
        rows = session.execute(query).scalars().all()
        # Detach from session so callers can use objects after session closes
        result = {}
        for row in rows:
            session.expunge(row)
            result[row.name] = row
        return result


# ---------------------------------------------------------------------------
# Read path — VesselSpec (used by decision.py to get vessel dimensions)
# ---------------------------------------------------------------------------

def get_vessel_specs(vessel_class: str | None = None) -> dict[str, VesselSpec]:
    """
    Return VesselSpec rows keyed by class_name (=vessel_class).
    If vessel_class is given, return only that class (or empty dict if not found).
    DOC3 §FEATURE: Decision Engine — called by decision.py to build port_constraints/vessel_specs
    dicts for constraint.check_feasibility(); never raw-queried outside this module.
    """
    with get_session() as session:
        query = select(VesselSpec)
        if vessel_class is not None:
            query = query.where(VesselSpec.class_name == vessel_class)
        rows = session.execute(query).scalars().all()
        result = {}
        for row in rows:
            session.expunge(row)
            result[row.class_name] = row
        return result


# ---------------------------------------------------------------------------
# Read path — RoutePhysics
# ---------------------------------------------------------------------------

def get_route_physics(origin: str, destination: str):
    """
    Return RoutePhysics for (origin, destination), or None.
    DOC3 edge case: None → cost_terms.py raises a clear error (not a silent fallback).

    Maps DB row → cost_terms.RoutePhysics dataclass (not the ORM model).
    Includes step50b additions: daily_opex_usd, other_voyage_cost_usd.
    """
    with get_session() as session:
        row = session.execute(
            select(RoutePhysicsModel).where(
                RoutePhysicsModel.origin == origin,
                RoutePhysicsModel.destination == destination,
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        # Map to cost_terms.RoutePhysics dataclass
        from backend.engine.cost_terms import RoutePhysics as RoutePhysicsDataclass
        return RoutePhysicsDataclass(
            origin=row.origin,
            destination=row.destination,
            distance_nm=row.distance_nm,
            laden_consumption_tpd=row.laden_consumption_tpd,
            ballast_consumption_tpd=row.ballast_consumption_tpd,
            speed_knots=DEFAULT_BALLAST_SPEED_KNOTS,
            daily_opex_usd=row.daily_opex_usd if row.daily_opex_usd is not None else 8_500.0,
            other_voyage_cost_usd=row.other_voyage_cost_usd if row.other_voyage_cost_usd is not None else 0.0,
        )


# ---------------------------------------------------------------------------
# Read path — OperationalEvidence
# ---------------------------------------------------------------------------

def get_operational_evidence(route: str, vessel_class: str) -> list[OperationalEvidence]:
    """
    Return operational evidence rows for (route, vessel_class).
    Feeds engine/evidence.py (Step 9.5).
    """
    with get_session() as session:
        rows = session.execute(
            select(OperationalEvidence)
            .where(
                OperationalEvidence.route == route,
                OperationalEvidence.vessel_class == vessel_class,
            )
            .order_by(desc(OperationalEvidence.observed_at))
        ).scalars().all()
        for row in rows:
            session.expunge(row)
        return list(rows)


# ---------------------------------------------------------------------------
# Read path — CongestionSnapshot
# ---------------------------------------------------------------------------

def get_latest_congestion_snapshot(port: str) -> Optional[dict[str, Any]]:
    """
    Return the latest CongestionSnapshot row for port as a plain dict, or None.
    Called by congestion.py's _read_snapshot() and decision.py's bunker price lookup.
    The 'bunker' port key row carries bunker_price_usd (VLSFO USD/mt).
    """
    with get_session() as session:
        row = session.execute(
            select(CongestionSnapshot)
            .where(CongestionSnapshot.port == port)
            .order_by(desc(CongestionSnapshot.recorded_at))
            .limit(1)
        ).scalar_one_or_none()
        if row is None:
            return None
        return {
            "port":             row.port,
            "vessel_count":     row.vessel_count,
            "avg_wait_hours":   row.avg_wait_hours,
            "recorded_at":      row.recorded_at,
            "is_live":          row.is_live,
            "source_note":      row.source_note,
            "bunker_price_usd": row.bunker_price_usd,  # None for real port rows
        }


# ---------------------------------------------------------------------------
# Read path — VesselPositionSnapshot (for decision.py τ generation)
# ---------------------------------------------------------------------------

def get_candidate_vessels_by_class(vessel_class: str) -> list[VesselPositionSnapshot]:
    """
    Return all tracked vessel positions for vessel_class.
    Used by decision.py's repositioning-aware τ generation (§11.2).
    Empty list if no AIS coverage → graceful calendar-only τ fallback.
    """
    with get_session() as session:
        rows = session.execute(
            select(VesselPositionSnapshot)
            .where(VesselPositionSnapshot.vessel_class == vessel_class)
            .order_by(desc(VesselPositionSnapshot.recorded_at))
        ).scalars().all()
        for row in rows:
            session.expunge(row)
        return list(rows)


def get_all_candidate_vessels() -> list[VesselPositionSnapshot]:
    """
    Return all tracked vessel positions.
    Used by the Fleet Portfolio dashboard for live visibility.
    """
    with get_session() as session:
        rows = session.execute(
            select(VesselPositionSnapshot)
            .order_by(desc(VesselPositionSnapshot.recorded_at))
        ).scalars().all()
        for row in rows:
            session.expunge(row)
        return list(rows)


def get_earliest_repositioning_days(
    vessel_class: str,
    origin_port: str,
) -> Optional[float]:
    """
    Return the ballast transit days from the nearest/earliest candidate vessel's
    current position to origin_port, or None if no AIS coverage exists for
    that class (graceful calendar-only τ fallback per DOC3 §11.2).

    Uses haversine distance + DEFAULT_BALLAST_SPEED_KNOTS for the estimate.
    Origin port position is approximated from a small built-in lookup;
    real coordinates come from RoutePhysics once that table is seeded.
    """
    candidates = get_candidate_vessels_by_class(vessel_class)
    if not candidates:
        return None

    # Approximate port coordinates (seeded; RoutePhysics table is the authoritative
    # source once Build Step 3's data is fully loaded)
    _PORT_COORDS: dict[str, tuple[float, float]] = {
        "Paradip":    (20.32, 86.70),
        "Gangavaram": (17.68, 83.28),
        "Dhamra":     (20.78, 86.99),
    }
    port_lat, port_lon = _PORT_COORDS.get(origin_port, (0.0, 0.0))
    if port_lat == 0.0 and port_lon == 0.0:
        return None  # Unknown port — fall back to calendar-only

    def _haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        R_NM = 3440.065
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (math.sin(dlat / 2) ** 2
             + math.cos(math.radians(lat1))
             * math.cos(math.radians(lat2))
             * math.sin(dlon / 2) ** 2)
        return R_NM * 2 * math.asin(math.sqrt(a))

    min_days: float | None = None
    for vessel in candidates:
        dist_nm = _haversine_nm(
            vessel.current_lat, vessel.current_lon, port_lat, port_lon
        )
        days = dist_nm / (DEFAULT_BALLAST_SPEED_KNOTS * 24.0)
        if min_days is None or days < min_days:
            min_days = days

    return round(min_days, 2) if min_days is not None else None


# ---------------------------------------------------------------------------
# Health-check helpers — used by GET /health (API Layer, Build Step 10)
# ---------------------------------------------------------------------------

def get_latest_retrain_timestamp() -> Optional[datetime]:
    """
    Return the generated_at of the most-recently written ForecastObject, or None
    if no forecasts have been trained yet.  Used by /health to report models_loaded.
    DOC3 §FEATURE: API Layer — health check.
    """
    try:
        with get_session() as session:
            row = session.execute(
                select(ForecastObject.generated_at)
                .order_by(desc(ForecastObject.generated_at))
                .limit(1)
            ).scalar_one_or_none()
            return row
    except Exception as exc:
        logger.debug("get_latest_retrain_timestamp failed: %s", exc)
        return None


def get_latest_ais_timestamp() -> Optional[datetime]:
    """
    Return the recorded_at of the most-recently written live VesselPositionSnapshot
    or CongestionSnapshot, indicating the AIS listener is actively writing data.
    Used by /health to report ais_listener_last_seen.
    """
    try:
        with get_session() as session:
            # Check VesselPositionSnapshot first (updated constantly by moving ships)
            vessel_row = session.execute(
                select(VesselPositionSnapshot.recorded_at)
                .order_by(desc(VesselPositionSnapshot.recorded_at))
                .limit(1)
            ).scalar_one_or_none()

            # Check CongestionSnapshot as well (updated on geofence enter/exit)
            cong_row = session.execute(
                select(CongestionSnapshot.recorded_at)
                .where(CongestionSnapshot.is_live == True)  # noqa: E712
                .order_by(desc(CongestionSnapshot.recorded_at))
                .limit(1)
            ).scalar_one_or_none()

            timestamps = [t for t in (vessel_row, cong_row) if t is not None]
            if not timestamps:
                return None
            latest = max(timestamps)
            if latest and latest.tzinfo is None:
                latest = latest.replace(tzinfo=timezone.utc)
            return latest
    except Exception as exc:
        logger.debug("get_latest_ais_timestamp failed: %s", exc)
        return None


def get_latest_bunker_timestamp() -> Optional[datetime]:
    """
    Return the recorded_at of the most-recently written bunker price.
    Used by /health to report bunker_last_updated.
    """
    try:
        with get_session() as session:
            row = session.execute(
                select(CongestionSnapshot.recorded_at)
                .where(CongestionSnapshot.port == "bunker")
                .order_by(desc(CongestionSnapshot.recorded_at))
                .limit(1)
            ).scalar_one_or_none()
            if row and row.tzinfo is None:
                row = row.replace(tzinfo=timezone.utc)
            return row
    except Exception as exc:
        logger.debug("get_latest_bunker_timestamp failed: %s", exc)
        return None
