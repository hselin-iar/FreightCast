"""
warehouse/models.py — SQLAlchemy ORM models.

Nine models per DOC3 §FEATURE: Data Warehouse.
ALL queries against these models live exclusively in repository.py.

DOC3 §FEATURE: Data Warehouse → models.py
DOC2 §5.2
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# RateHistory
# DOC3: (route, vessel_class, date, rate, tier: str | None, source: Provenance)
# Primary source: rate_5tc_ingest.py (Capesize 5TC), tagged provenance="measured"
# ---------------------------------------------------------------------------
class RateHistory(Base):
    __tablename__ = "rate_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    route: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    vessel_class: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    rate: Mapped[float] = mapped_column(Float, nullable=False)
    # tier: "A" or "B" from 5TC dataset — preserved, not collapsed (DOC3)
    tier: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    # provenance: "measured" | "modeled" | "assumed"
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="measured")

    __table_args__ = (
        UniqueConstraint("route", "vessel_class", "date", name="uq_rate_history_route_class_date"),
        Index("ix_rate_history_route_class_date", "route", "vessel_class", "date"),
    )

    def __repr__(self) -> str:
        return (
            f"RateHistory(route={self.route!r}, vessel_class={self.vessel_class!r}, "
            f"date={self.date}, rate={self.rate}, tier={self.tier!r})"
        )


# ---------------------------------------------------------------------------
# PortConstraint
# DOC3: (name, max_draft_m, max_loa_m, max_beam_m, handling_rate_tpd,
#         tidal_dependent, verified, source)
# Human sign-off (verified=True) required before this row enters the active scope.
# Port-scope growth mechanism (DOC2 Addendum v3 §A1): add a verified row here,
# nothing else changes.
# ---------------------------------------------------------------------------
class PortConstraint(Base):
    __tablename__ = "port_constraint"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True, index=True)
    max_draft_m: Mapped[float] = mapped_column(Float, nullable=False)
    max_loa_m: Mapped[float] = mapped_column(Float, nullable=False)
    max_beam_m: Mapped[float] = mapped_column(Float, nullable=False)
    handling_rate_tpd: Mapped[float] = mapped_column(Float, nullable=False)
    tidal_dependent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # verified=False → pending human sign-off (DOC3 hard requirement)
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="assumed")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=datetime.utcnow, onupdate=datetime.utcnow,
    )

    def __repr__(self) -> str:
        return (
            f"PortConstraint(name={self.name!r}, max_draft_m={self.max_draft_m}, "
            f"verified={self.verified})"
        )


# ---------------------------------------------------------------------------
# VesselSpec
# DOC3: (class_name, typical_capacity_tonnes, draft_m, loa_m, beam_m)
# Decision variables are at vessel-CLASS level — never per-IMO (DOC3 §0).
# ---------------------------------------------------------------------------
class VesselSpec(Base):
    __tablename__ = "vessel_spec"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    class_name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    typical_capacity_tonnes: Mapped[float] = mapped_column(Float, nullable=False)
    draft_m: Mapped[float] = mapped_column(Float, nullable=False)
    loa_m: Mapped[float] = mapped_column(Float, nullable=False)
    beam_m: Mapped[float] = mapped_column(Float, nullable=False)

    def __repr__(self) -> str:
        return (
            f"VesselSpec(class_name={self.class_name!r}, "
            f"capacity={self.typical_capacity_tonnes}t)"
        )


# ---------------------------------------------------------------------------
# ForecastObject
# DOC3: (route, vessel_class, horizon_days, generated_at, point_estimate,
#         confidence_band, trajectory: JSON, driver_explanation,
#         is_high_uncertainty, model_used)
# One row per (route × vessel_class × horizon × generation_date).
# Hot read path — indexed on (route, vessel_class, horizon_days, generated_at DESC).
# ---------------------------------------------------------------------------
class ForecastObject(Base):
    __tablename__ = "forecast_object"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    route: Mapped[str] = mapped_column(String(100), nullable=False)
    vessel_class: Mapped[str] = mapped_column(String(100), nullable=False)
    horizon_days: Mapped[int] = mapped_column(Integer, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    point_estimate: Mapped[float] = mapped_column(Float, nullable=False)
    # confidence_band stored as JSON: {"lower": float, "upper": float}
    confidence_band: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    # trajectory: JSON list of {date, value} dicts
    trajectory: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    driver_explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_high_uncertainty: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    model_used: Mapped[str] = mapped_column(String(50), nullable=False, default="naive")
    # provenance tag — always "modeled" for forecasts (set by forecasting.py at write time)
    # DOC3 §FEATURE: Provenance & Explainability Layer
    provenance: Mapped[str] = mapped_column(String(20), nullable=False, default="modeled")

    __table_args__ = (
        # Hot read: latest forecast per (route, vessel_class, horizon_days)
        Index(
            "ix_forecast_object_route_class_horizon_generated",
            "route", "vessel_class", "horizon_days", "generated_at",
        ),
    )

    def confidence_band_dict(self) -> dict:
        try:
            return json.loads(self.confidence_band)
        except (json.JSONDecodeError, TypeError):
            return {}

    def trajectory_list(self) -> list:
        try:
            return json.loads(self.trajectory)
        except (json.JSONDecodeError, TypeError):
            return []

    def __repr__(self) -> str:
        return (
            f"ForecastObject(route={self.route!r}, vessel_class={self.vessel_class!r}, "
            f"horizon_days={self.horizon_days}, point_estimate={self.point_estimate}, "
            f"model_used={self.model_used!r})"
        )


# ---------------------------------------------------------------------------
# CongestionSnapshot
# DOC3: (port, vessel_count, avg_wait_hours, recorded_at, is_live)
# Written by ais_listener; read by congestion.py and decision.py.
# Shape extended with bunker_price_usd (nullable): the 'bunker' port key row
# stores current VLSFO price. decision.py reads it via get_latest_congestion_snapshot('bunker').
# ---------------------------------------------------------------------------
class CongestionSnapshot(Base):
    __tablename__ = "congestion_snapshot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    port: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    vessel_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_wait_hours: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_live: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    source_note: Mapped[str] = mapped_column(String(500), nullable=False, default="live AIS stream")
    # VLSFO bunker price in USD/mt. Only populated on the 'bunker' port key row.
    # Nullable so existing congestion rows (real ports) never need a value here.
    bunker_price_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True, default=None)

    __table_args__ = (
        Index("ix_congestion_snapshot_port_recorded", "port", "recorded_at"),
    )

    def __repr__(self) -> str:
        return (
            f"CongestionSnapshot(port={self.port!r}, vessel_count={self.vessel_count}, "
            f"avg_wait_hours={self.avg_wait_hours}, is_live={self.is_live})"
        )


# ---------------------------------------------------------------------------
# ExogenousFeature
# NEW — DOC2 Addendum v3 §A2
# (source: str, date, value) — keyed by (source, date)
# Sources: Brent, WTI, Iron Ore, BDRY, GSCPI, bunker_vlsfo, bunker_mgo
# Kept separate from RateHistory (model inputs, not freight rates).
# ---------------------------------------------------------------------------
class ExogenousFeature(Base):
    __tablename__ = "exogenous_feature"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)

    __table_args__ = (
        UniqueConstraint("source", "date", name="uq_exogenous_feature_source_date"),
        Index("ix_exogenous_feature_source_date", "source", "date"),
    )

    def __repr__(self) -> str:
        return f"ExogenousFeature(source={self.source!r}, date={self.date}, value={self.value})"


# ---------------------------------------------------------------------------
# RoutePhysics
# NEW — DOC2 Addendum v3 §A2
# Real distance-based bunker consumption (laden/ballast) — replaces flat assumed constant.
# Feeds cost_terms.py's bunker cost calculation (Build Step 7).
# ---------------------------------------------------------------------------
class RoutePhysics(Base):
    __tablename__ = "route_physics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    origin: Mapped[str] = mapped_column(String(200), nullable=False)
    destination: Mapped[str] = mapped_column(String(200), nullable=False)
    distance_nm: Mapped[float] = mapped_column(Float, nullable=False)
    # tonnes per day at sea — real physics from handoff dataset
    laden_consumption_tpd: Mapped[float] = mapped_column(Float, nullable=False)
    ballast_consumption_tpd: Mapped[float] = mapped_column(Float, nullable=False)
    # ── Research pipeline step50b additions ──────────────────────────────────
    # Daily vessel operating expense (crew, maintenance, insurance) in USD/day.
    # Per-class benchmarks: Capesize ~8500, Panamax ~7200, Supramax ~6500.
    # Nullable so rows seeded before this column exist still load cleanly.
    daily_opex_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True, default=8500.0)
    # Other voyage costs: port dues, canal tolls, pilotage. Per-route, USD total.
    other_voyage_cost_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True, default=0.0)

    __table_args__ = (
        UniqueConstraint("origin", "destination", name="uq_route_physics_origin_dest"),
        Index("ix_route_physics_origin_dest", "origin", "destination"),
    )

    def __repr__(self) -> str:
        return (
            f"RoutePhysics(origin={self.origin!r}, destination={self.destination!r}, "
            f"distance_nm={self.distance_nm})"
        )



# ---------------------------------------------------------------------------
# OperationalEvidence
# NEW — DOC2 Addendum v3 §A3
# ShipOffer broker fixture/position reports.
# Feeds engine/evidence.py (confidence score computed there, NOT here).
# ---------------------------------------------------------------------------
class OperationalEvidence(Base):
    __tablename__ = "operational_evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    route: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    vessel_class: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # confidence_score is computed in evidence.py, not here
    confidence_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")

    __table_args__ = (
        Index("ix_operational_evidence_route_class", "route", "vessel_class"),
    )

    def __repr__(self) -> str:
        return (
            f"OperationalEvidence(route={self.route!r}, vessel_class={self.vessel_class!r}, "
            f"observed_at={self.observed_at})"
        )


# ---------------------------------------------------------------------------
# VesselPositionSnapshot
# NEW — DOC2 §5/§11.2 v3 Final, handoff Step 49G
# Real candidate bulk-carrier telemetry from MyShipTracking / aisstream.io.
# Feeds decision.py's repositioning-aware τ generation (§11.2).
# Decision variables remain at vessel-CLASS level — this is enrichment, not
# a per-IMO assignment problem (DOC3 §0).
# ORM definition verbatim from DOC3 §FEATURE: Data Warehouse.
# ---------------------------------------------------------------------------
class VesselPositionSnapshot(Base):
    __tablename__ = "vessel_position_snapshot"

    imo: Mapped[int] = mapped_column(Integer, primary_key=True)
    vessel_name: Mapped[str] = mapped_column(String(100), nullable=False)
    vessel_class: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    dwt: Mapped[float] = mapped_column(Float, nullable=False)
    current_lat: Mapped[float] = mapped_column(Float, nullable=False)
    current_lon: Mapped[float] = mapped_column(Float, nullable=False)
    speed_knots: Mapped[float] = mapped_column(Float, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    def __repr__(self) -> str:
        return (
            f"VesselPositionSnapshot(imo={self.imo}, vessel_name={self.vessel_name!r}, "
            f"vessel_class={self.vessel_class!r}, "
            f"pos=({self.current_lat:.4f}, {self.current_lon:.4f}))"
        )
