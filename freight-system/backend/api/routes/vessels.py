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
    Return all vessel position snapshots keyed by IMO.
    Combines live AIS listener stream with warehouse persistent snapshots.
    """
    try:
        live = ais_listener.get_latest_vessel_positions()
        if live:
            return live
    except Exception:
        pass

    from backend.warehouse import repository
    return repository.get_all_vessel_positions()
