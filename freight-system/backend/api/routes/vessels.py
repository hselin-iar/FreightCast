"""
api/routes/vessels.py — GET /vessel-positions

Returns live vessel coordinates from the AIS listener.
"""
import logging
from typing import Dict, Any
from fastapi import APIRouter

from backend.ingestion import ais_listener

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/vessel-positions")
def get_vessel_positions() -> Dict[int, Dict[str, Any]]:
    """
    Return all in-memory vessel position snapshots keyed by IMO.
    """
    try:
        return ais_listener.get_latest_vessel_positions()
    except Exception as exc:
        logger.exception("Failed to fetch vessel positions")
        return {}
