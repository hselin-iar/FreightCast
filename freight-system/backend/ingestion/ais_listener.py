"""
ingestion/ais_listener.py — persistent AIS WebSocket listener.

DUAL CONCERN (DOC3 §FEATURE: AIS Listener & Congestion Module, DOC2 §4 v3 Final):
  (a) Port congestion: geofenced port bounding boxes → CongestionSnapshot
  (b) Vessel fleet tracking: bulk-carrier positions in loading regions
      (Queensland, Richards Bay, Kalimantan) → VesselPositionSnapshot

ARCHITECTURE RULE (DOC2 §7, DOC3 §0):
  This module runs as its OWN long-lived process — NOT as a FastAPI route,
  NOT as a background task decorator on the FastAPI app. An AIS hiccup must
  never affect API request latency or uptime.

Run standalone:
  python -m backend.ingestion.ais_listener

Reconnect: exponential backoff on disconnect — self-heals without manual restart.
Warehouse writes: stubbed as in-memory dicts for Build Step 2; wired to
  repository.py in Build Step 3.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import signal
import sys
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_AISSTREAM_API_KEY = os.environ.get("AISSTREAM_API_KEY", "")
_AISSTREAM_URL = "wss://stream.aisstream.io/v0/stream"

# Reconnect backoff: start at 2s, double each attempt, cap at 60s
_BACKOFF_BASE_S = 2.0
_BACKOFF_MAX_S = 60.0
_BACKOFF_FACTOR = 2.0

# ---------------------------------------------------------------------------
# In-memory stores (Build Step 2 stub — replaced by repository writes in Step 3)
# ---------------------------------------------------------------------------

# port_name → latest congestion snapshot dict
_congestion_store: dict[str, dict[str, Any]] = {}

# imo → latest vessel position dict
_vessel_position_store: dict[int, dict[str, Any]] = {}

# port_name → set of IMOs currently inside the geofence
_port_vessel_map: dict[str, set[int]] = {}

# imo → datetime of last position report (used for TTL departure eviction)
_vessel_last_seen: dict[int, datetime] = {}


# ---------------------------------------------------------------------------
# Subscription builder
# ---------------------------------------------------------------------------


def _build_subscription(bounding_boxes: dict[str, dict]) -> dict:
    """
    Build the AIS stream subscription payload.

    Subscribes to:
      (a) All port bounding boxes for congestion tracking
      (b) Loading-region bounding boxes for vessel fleet tracking

    AISStream v0 BoundingBoxes format: list of [[minLat, minLon], [maxLat, maxLon]]
    """
    # Loading regions for fleet tracking (DOC3 §FEATURE: AIS Listener)
    loading_regions = {
        "Queensland_loading":   {"min_lat": -24.0, "max_lat": -18.0, "min_lon": 148.0, "max_lon": 153.0},
        "Richards_Bay_loading": {"min_lat": -29.0, "max_lat": -27.0, "min_lon":  31.0, "max_lon":  33.0},
        "Kalimantan_loading":   {"min_lat":  -4.0, "max_lat":   2.0, "min_lon": 115.0, "max_lon": 119.0},
    }

    all_boxes = {**bounding_boxes, **loading_regions}

    # aisstream.io v0 format: each box is [[minLat, minLon], [maxLat, maxLon]]
    bboxes = []
    for region_name, bb in all_boxes.items():
        if isinstance(bb, dict) and bb:  # skip placeholder empty dicts
            bboxes.append([
                [bb.get("min_lat", -90), bb.get("min_lon", -180)],
                [bb.get("max_lat",  90), bb.get("max_lon",  180)],
            ])

    return {
        "APIKey": _AISSTREAM_API_KEY,
        "BoundingBoxes": bboxes if bboxes else [
            [[-90, -180], [90, 180]]   # global fallback
        ],
        "FilterMessageTypes": ["PositionReport", "ShipStaticData"],
    }


# ---------------------------------------------------------------------------
# Message routing
# ---------------------------------------------------------------------------

def _is_in_bounding_box(lat: float, lon: float, bb: dict) -> bool:
    """Return True if (lat, lon) falls inside bounding box dict."""
    return (
        bb.get("min_lat", -90) <= lat <= bb.get("max_lat", 90)
        and bb.get("min_lon", -180) <= lon <= bb.get("max_lon", 180)
    )


def _classify_message(
    imo: int,
    lat: float,
    lon: float,
    vessel_class: str,
    bounding_boxes: dict[str, dict],
) -> tuple[list[str], bool]:
    """
    Classify a position message by concern:
      - Returns (matched_ports, is_loading_region)
    """
    loading_regions = {
        "Queensland_loading": {"min_lat": -24.0, "max_lat": -18.0, "min_lon": 148.0, "max_lon": 153.0},
        "Richards_Bay_loading": {"min_lat": -29.0, "max_lat": -27.0, "min_lon": 31.0,  "max_lon": 33.0},
        "Kalimantan_loading": {"min_lat": -4.0,  "max_lat": 2.0,   "min_lon": 115.0, "max_lon": 119.0},
    }

    matched_ports = [
        port for port, bb in bounding_boxes.items()
        if bb and _is_in_bounding_box(lat, lon, bb)
    ]
    is_loading = any(
        _is_in_bounding_box(lat, lon, bb) for bb in loading_regions.values()
    )
    return matched_ports, is_loading


def _on_position_message(
    msg: dict[str, Any],
    bounding_boxes: dict[str, dict],
    metadata: dict[str, Any] | None = None,
) -> None:
    """
    Process a PositionReport message.

    Routes to:
      (a) Port congestion: update _port_vessel_map → recompute CongestionSnapshot
      (b) Vessel fleet: update _vessel_position_store
    """
    position = msg.get("Message", {}).get("PositionReport", {})
    imo = msg.get("MetaData", {}).get("MMSI") or 0
    lat = float(position.get("Latitude", 0))
    lon = float(position.get("Longitude", 0))
    speed = float(position.get("Sog", 0))   # speed-over-ground in knots
    vessel_name = msg.get("MetaData", {}).get("ShipName", "").strip()
    vessel_class = (metadata or {}).get("vessel_class", "Unknown")
    recorded_at = datetime.now(timezone.utc)

    matched_ports, is_loading = _classify_message(imo, lat, lon, vessel_class, bounding_boxes)

    # (a) Port congestion — geofence enter/exit bookkeeping
    for port in bounding_boxes:
        if not bounding_boxes[port]:
            continue
        was_in = imo in _port_vessel_map.get(port, set())
        now_in = port in matched_ports

        if now_in and not was_in:
            _port_vessel_map.setdefault(port, set()).add(imo)
            logger.debug("AIS: vessel %d entered %s geofence.", imo, port)

        elif was_in and not now_in:
            _port_vessel_map.get(port, set()).discard(imo)
            logger.debug("AIS: vessel %d exited %s geofence.", imo, port)

        if now_in or was_in:
            _update_congestion_snapshot(port, recorded_at)

    # (b) Vessel fleet tracking — write position snapshot
    if imo:
        _vessel_last_seen[imo] = recorded_at
        pos = {
            "imo": imo,
            "vessel_name": vessel_name,
            "vessel_class": vessel_class,
            "dwt": 0.0,   # filled from ShipStaticData in Step 3+
            "current_lat": lat,
            "current_lon": lon,
            "speed_knots": speed,
            "recorded_at": recorded_at,
        }
        # Always update in-memory store
        _vessel_position_store[imo] = pos

        # Write to warehouse if available (Step 3 wiring)
        try:
            from backend.warehouse import repository
            repository.upsert_vessel_position_snapshot(pos)
        except Exception as exc:
            logger.debug("AIS: vessel position warehouse write skipped: %s", exc)

        logger.debug(
            "AIS fleet: updated position for IMO %d (%s) at (%.4f, %.4f)",
            imo, vessel_name, lat, lon,
        )


# Port handling & berth capacities for first-principles M/G/c terminal queuing
PORT_CAPACITIES: dict[str, dict[str, float]] = {
    "Paradip": {"berths": 4, "handling_tpd": 40000.0},
    "Gangavaram": {"berths": 5, "handling_tpd": 60000.0},
    "Dhamra": {"berths": 3, "handling_tpd": 50000.0},
    "Visakhapatnam": {"berths": 4, "handling_tpd": 55000.0},
    "Haldia": {"berths": 2, "handling_tpd": 18000.0},
    "Kamarajar (Ennore)": {"berths": 3, "handling_tpd": 45000.0},
}


def _compute_queuing_delay_hours(port: str, vessel_count: int) -> float:
    """
    First-principles M/G/c terminal queuing delay estimation.
    Computes expected anchorage wait from backlog tonnage, berth count, and handling rate TPD.
    """
    cap = PORT_CAPACITIES.get(port, {"berths": 3, "handling_tpd": 40000.0})
    berths = int(cap["berths"])
    handling_tpd = cap["handling_tpd"]

    if vessel_count <= 0:
        return 0.0
    if vessel_count <= berths:
        # Immediate berth availability — pilotage & berthing turn time (2.0 - 4.0 hrs)
        return round(2.0 + (vessel_count * 0.5), 2)

    # Queue backlog beyond available berths
    excess_vessels = vessel_count - berths
    avg_parcel_mt = 75000.0  # standard commercial bulk consignment
    backlog_tonnes = excess_vessels * avg_parcel_mt
    service_rate_tpd = berths * handling_tpd
    queue_days = backlog_tonnes / max(service_rate_tpd, 1.0)
    return round(2.0 + (queue_days * 24.0), 2)


def _evict_stale_vessels(cutoff_seconds: float = 21600.0) -> None:
    """Evict vessels whose last AIS position report is older than cutoff (default 6 hours)."""
    now = datetime.now(timezone.utc)
    stale_imos = [
        imo for imo, last_seen in _vessel_last_seen.items()
        if (now - last_seen).total_seconds() > cutoff_seconds
    ]
    for imo in stale_imos:
        for port, imos in _port_vessel_map.items():
            if imo in imos:
                imos.discard(imo)
                logger.info("AIS: evicted departed/stale vessel %d from %s", imo, port)
        _vessel_last_seen.pop(imo, None)


def _update_congestion_snapshot(port: str, recorded_at: datetime) -> None:
    """
    Recompute and store a CongestionSnapshot for port using M/G/c queue model.
    Writes to repository with in-memory fallback for cold start.
    """
    _evict_stale_vessels()
    vessel_count = len(_port_vessel_map.get(port, set()))
    avg_wait_hours = _compute_queuing_delay_hours(port, vessel_count)

    snapshot = {
        "port": port,
        "vessel_count": vessel_count,
        "avg_wait_hours": avg_wait_hours,
        "recorded_at": recorded_at,
        "is_live": True,
        "source_note": "live AIS stream (M/G/c model)",
    }
    # Always update in-memory store
    _congestion_store[port] = snapshot

    # Write to warehouse if available (Step 3 wiring)
    try:
        from backend.warehouse import repository
        repository.write_congestion_snapshot(port, snapshot)
    except Exception as exc:
        logger.debug("AIS: warehouse write skipped (not yet available): %s", exc)

    logger.info(
        "AIS congestion: %s — %d vessels, %.1fh expected wait (M/G/c)",
        port, vessel_count, avg_wait_hours,
    )


# ---------------------------------------------------------------------------
# Mock AIS feed (for Build Step 2 — no real AISSTREAM_API_KEY needed)
# ---------------------------------------------------------------------------

async def _mock_ais_feed(bounding_boxes: dict[str, dict], stop_event: asyncio.Event) -> None:
    """
    Simulates an AIS feed by emitting synthetic PositionReport messages.
    Used when AISSTREAM_API_KEY is not set (development / CI).

    Emits a vessel entering the Paradip bounding box (if defined),
    then one in the Queensland loading region.
    """
    import random

    logger.info("AIS: no API key — running MOCK feed for development.")

    # Port bounding boxes for mock (use actual boxes if configured, else defaults)
    paradip_bb = bounding_boxes.get("Paradip") or {
        "min_lat": 20.2, "max_lat": 20.4, "min_lon": 86.6, "max_lon": 86.8
    }

    fake_vessels = [
        # (imo, lat, lon, name, vessel_class, note)
        (9100001, 20.32, 86.70, "MOCK CAPESIZE ONE",  "Capesize",         "inside Paradip"),
        (9100002, 20.29, 86.65, "MOCK CAPESIZE TWO",  "Capesize",         "inside Paradip"),
        (9200001, -20.5, 150.2, "MOCK CAPE QLD",      "Capesize",         "Queensland loading"),
        (9300001,  20.0,  86.5, "MOCK PANAMAX ONE",   "Panamax/Kamsarmax","Paradip approach"),
    ]

    tick = 0
    while not stop_event.is_set():
        tick += 1
        for imo, lat, lon, name, vclass, note in fake_vessels:
            # Drift vessel slightly each tick
            lat += random.uniform(-0.01, 0.01)
            lon += random.uniform(-0.01, 0.01)
            speed = round(random.uniform(0.0, 3.5), 1)

            msg = {
                "MessageType": "PositionReport",
                "MetaData": {"MMSI": imo, "ShipName": name},
                "Message": {
                    "PositionReport": {
                        "Latitude": lat, "Longitude": lon, "Sog": speed,
                    }
                },
            }
            _on_position_message(msg, bounding_boxes, metadata={"vessel_class": vclass})

        if tick % 5 == 0:
            logger.info(
                "AIS mock tick %d — congestion store: %s",
                tick,
                {p: v["vessel_count"] for p, v in _congestion_store.items()},
            )
        await asyncio.sleep(2.0)


# ---------------------------------------------------------------------------
# Live AIS WebSocket connection
# ---------------------------------------------------------------------------

async def _live_ais_feed(bounding_boxes: dict[str, dict], stop_event: asyncio.Event) -> None:
    """Connect to aisstream.io and process messages until stop_event."""
    try:
        import websockets
    except ImportError:
        logger.error("websockets package not installed. Run: pip install websockets")
        return

    subscription = _build_subscription(bounding_boxes)
    backoff = _BACKOFF_BASE_S

    while not stop_event.is_set():
        try:
            logger.info("AIS: connecting to %s", _AISSTREAM_URL)
            async with websockets.connect(_AISSTREAM_URL) as ws:
                await ws.send(json.dumps(subscription))
                logger.info("AIS: connected and subscribed.")
                backoff = _BACKOFF_BASE_S  # reset on successful connect

                async for raw in ws:
                    if stop_event.is_set():
                        break
                    try:
                        msg = json.loads(raw)
                        msg_type = msg.get("MessageType", "")
                        if msg_type == "PositionReport":
                            _on_position_message(msg, bounding_boxes)
                        # ShipStaticData: could enrich vessel_class — deferred to Step 3
                    except json.JSONDecodeError as exc:
                        logger.warning("AIS: bad JSON: %s", exc)
                    except Exception as exc:
                        logger.warning("AIS: message processing error: %s", exc)

        except Exception as exc:
            if stop_event.is_set():
                break
            logger.warning(
                "AIS: connection lost (%s) — reconnecting in %.0fs", exc, backoff
            )
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=backoff)
            except asyncio.TimeoutError:
                pass
            backoff = min(backoff * _BACKOFF_FACTOR, _BACKOFF_MAX_S)


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------

async def connect(
    bounding_boxes: dict[str, dict] | None = None,
    stop_event: asyncio.Event | None = None,
) -> None:
    """
    Main entrypoint — runs the AIS listener indefinitely.

    Uses the live aisstream.io feed when AISSTREAM_API_KEY is set;
    falls back to the mock feed for development/CI.

    bounding_boxes: port → {min_lat, max_lat, min_lon, max_lon}
                    Defaults to AIS_BOUNDING_BOXES from constants.py.
    stop_event:     set to terminate cleanly (used in tests).
    """
    from backend.config.constants import AIS_BOUNDING_BOXES

    if bounding_boxes is None:
        bounding_boxes = AIS_BOUNDING_BOXES

    if stop_event is None:
        stop_event = asyncio.Event()

    if _AISSTREAM_API_KEY:
        await _live_ais_feed(bounding_boxes, stop_event)
    else:
        await _mock_ais_feed(bounding_boxes, stop_event)


# ---------------------------------------------------------------------------
# Read-path accessors (consumed by congestion.py in Build Step 2)
# ---------------------------------------------------------------------------

def get_latest_congestion_snapshot(port: str) -> dict[str, Any] | None:
    """Return the latest in-memory congestion snapshot for port, or None."""
    return _congestion_store.get(port)


def get_latest_vessel_positions() -> dict[int, dict[str, Any]]:
    """Return all in-memory vessel position snapshots keyed by IMO."""
    return dict(_vessel_position_store)


# ---------------------------------------------------------------------------
# __main__ — standalone process entrypoint
# ---------------------------------------------------------------------------

def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


async def _main() -> None:
    _setup_logging()
    logger.info("AIS listener starting as standalone process.")

    stop_event = asyncio.Event()

    # Graceful shutdown on SIGINT / SIGTERM
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass  # Windows

    await connect(stop_event=stop_event)
    logger.info("AIS listener stopped.")


if __name__ == "__main__":
    asyncio.run(_main())
