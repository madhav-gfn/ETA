"""Standalone OSM Overpass pull (tiled, mirror-failover). Long-running —
run outside the API server so it doesn't pin a uvicorn worker:

    python scripts/pull_osm.py [city_slug]
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.db import SessionLocal, init_db  # noqa: E402
from app.ingestion.osm_landuse import pull_osm_land_use  # noqa: E402

if __name__ == "__main__":
    city = sys.argv[1] if len(sys.argv) > 1 else "delhi-ncr"
    init_db()
    db = SessionLocal()
    try:
        n = asyncio.run(pull_osm_land_use(db, city))
        print(f"osm pull: {n} rows")
    finally:
        db.close()
