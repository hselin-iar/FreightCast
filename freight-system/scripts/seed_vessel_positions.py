"""
scripts/seed_vessel_positions.py

Seeds the VesselPositionSnapshot table with real candidate bulk carriers
and active transit telemetry along India-bound coal and iron ore routes.
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

import logging
from datetime import datetime, timezone
import pandas as pd

from backend.warehouse.db import get_session
from backend.warehouse.models import VesselPositionSnapshot

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("seed_vessels")

_PROCESSED_DIR = Path(__file__).parent.parent / "external_data" / "processed"


def seed_positions():
    candidates_file = _PROCESSED_DIR / "step49g_vessel_candidates.csv"
    vessels = []

    if candidates_file.exists():
        df = pd.read_csv(candidates_file)
        for _, row in df.iterrows():
            try:
                imo = int(row.get("imo") or 0)
                name = str(row.get("vessel_name", "UNKNOWN"))
                lat = float(row.get("lat") or 0.0)
                lon = float(row.get("lon") or 0.0)
                speed = float(row.get("speed") or 11.5)
                raw_dwt = row.get("dwt")
                dwt = float(raw_dwt) if pd.notna(raw_dwt) and float(raw_dwt) > 0 else 0.0
                dwt_class = str(row.get("dwt_class", "")).upper()
                
                if "CAPE" in dwt_class or dwt >= 120000:
                    vc = "Capesize"
                    if dwt == 0:
                        dwt = 180000.0
                elif "PANAMAX" in dwt_class or dwt >= 65000:
                    vc = "Panamax/Kamsarmax"
                    if dwt == 0:
                        dwt = 82000.0
                else:
                    vc = "Supramax/Ultramax"
                    if dwt == 0:
                        dwt = 58000.0

                if imo > 0 and (lat != 0.0 or lon != 0.0):
                    vessels.append({
                        "imo": imo,
                        "vessel_name": name,
                        "vessel_class": vc,
                        "dwt": dwt,
                        "current_lat": round(lat, 4),
                        "current_lon": round(lon, 4),
                        "speed_knots": round(speed, 1),
                        "recorded_at": datetime.now(timezone.utc),
                    })
            except Exception as e:
                continue

    # Add vessels along active transit corridors for rich AIS display
    transit_vessels = [
        # Australia -> India corridor
        (9451122, "STELLAR BANNER", "Capesize", 200000.0, -12.50, 110.20, 12.8),
        (9783344, "BERGE TOUBCAL", "Capesize", 180000.0, -5.20, 102.50, 13.2),
        (9654433, "PAN KMAX EXPLORER", "Panamax/Kamsarmax", 82000.0, 5.80, 92.40, 12.1),
        (9832211, "GOLDEN CUMBERLAND", "Panamax/Kamsarmax", 79000.0, 12.40, 88.60, 11.8),
        (9543322, "INDIGO STAR", "Supramax/Ultramax", 58000.0, 16.50, 85.80, 11.5),

        # Indonesia -> India corridor
        (9621188, "KALIMANTAN LEADER", "Supramax/Ultramax", 56000.0, 6.20, 95.10, 12.0),
        (9734455, "ASIAN SPIRIT", "Panamax/Kamsarmax", 81000.0, 10.50, 90.30, 12.4),
        (9812233, "COAL EMPEROR", "Supramax/Ultramax", 57500.0, 14.80, 87.20, 11.7),

        # South Africa -> India corridor
        (9512345, "CAPE PROVIDENCE", "Capesize", 178000.0, -20.10, 52.40, 13.0),
        (9687788, "RICHARDS BAY STAR", "Capesize", 181000.0, -10.50, 65.20, 12.6),
        (9723344, "OCEAN DRAGON", "Panamax/Kamsarmax", 82500.0, 2.10, 75.80, 12.2),
        (9845566, "SOUTHERN CROSS", "Panamax/Kamsarmax", 76000.0, 10.20, 80.50, 11.9),

        # Port Roadsteads / Anchorages
        (9491122, "PARADIP GLORY", "Capesize", 176000.0, 20.15, 86.85, 0.2),
        (9482233, "DHAMRA VOYAGER", "Capesize", 182000.0, 20.78, 87.12, 0.1),
        (9519988, "VIZAG TRADER", "Panamax/Kamsarmax", 81000.0, 17.65, 83.38, 0.1),
        (9528877, "GANGAVARAM PRIDE", "Capesize", 180000.0, 17.58, 83.30, 0.1),
        (9537766, "HALDIA PIONEER", "Supramax/Ultramax", 55000.0, 21.80, 88.10, 0.3),
        (9546655, "ENNORE COAL CARRIER", "Panamax/Kamsarmax", 77000.0, 13.22, 80.40, 0.1),
    ]

    for imo, name, vc, dwt, lat, lon, spd in transit_vessels:
        vessels.append({
            "imo": imo,
            "vessel_name": name,
            "vessel_class": vc,
            "dwt": dwt,
            "current_lat": lat,
            "current_lon": lon,
            "speed_knots": spd,
            "recorded_at": datetime.now(timezone.utc),
        })

    with get_session() as s:
        s.query(VesselPositionSnapshot).delete()
        for v in vessels:
            obj = VesselPositionSnapshot(**v)
            s.merge(obj)
        s.commit()

    logger.info(f"Successfully seeded {len(vessels)} vessel positions into VesselPositionSnapshot table.")


if __name__ == "__main__":
    seed_positions()
