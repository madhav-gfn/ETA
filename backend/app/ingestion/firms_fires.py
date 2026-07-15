"""
NASA FIRMS thermal-anomaly ingestion (Section 1.3) — monitors regional
agricultural residue burning (Indo-Gangetic Plain stubble burning) that
CAAQMS ground sensors can't attribute on their own.

API: https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/{SOURCE}/{AREA}/{DAY_RANGE}
  - MAP_KEY: free registration key (NASA_FIRMS_MAP_KEY)
  - SOURCE: e.g. VIIRS_SNPP_NRT, VIIRS_NOAA20_NRT, MODIS_NRT
  - AREA: "west,south,east,north" bbox, max 4 decimal places
  - DAY_RANGE: 1-10

Rate limit: 5,000 transactions / 10-minute window per MAP_KEY (Section 1.3).
Polling cadence: every 3 hours, aligned with satellite overpass latency.
"""

import csv
import io
import logging

import httpx

from app.core.config import get_settings
from app.ingestion.cities import CityBounds, get_city
from app.ingestion.models import FireDetection
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

FIRMS_BASE_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
DEFAULT_SOURCES = ["VIIRS_SNPP_NRT", "MODIS_NRT"]


def _format_area(bbox: tuple[float, float, float, float]) -> str:
    min_lon, min_lat, max_lon, max_lat = bbox
    return f"{min_lon:.4f},{min_lat:.4f},{max_lon:.4f},{max_lat:.4f}"


def _parse_firms_csv(raw_csv: str) -> list[dict]:
    """Parses either the MODIS or VIIRS column layout — both are handled
    since column names differ slightly (`brightness` vs `bright_ti4`) but
    the fields we need (lat/lon/confidence/frp/acq_date/acq_time) are common.
    """
    reader = csv.DictReader(io.StringIO(raw_csv))
    return list(reader)


async def _fetch_source(
    client: httpx.AsyncClient, map_key: str, source: str, bbox: tuple, day_range: int
) -> list[dict]:
    url = f"{FIRMS_BASE_URL}/{map_key}/{source}/{_format_area(bbox)}/{day_range}"
    resp = await client.get(url, timeout=30.0)
    resp.raise_for_status()

    # FIRMS returns a plain-text error body (not CSV) on bad MAP_KEY / no data.
    if "Invalid MAP_KEY" in resp.text or not resp.text.strip():
        logger.warning("FIRMS %s returned no usable data: %.100s", source, resp.text)
        return []

    return _parse_firms_csv(resp.text)


async def pull_fire_detections(
    db: Session,
    city_slug: str = "delhi-ncr",
    day_range: int = 1,
    sources: list[str] | None = None,
) -> int:
    """Fetch recent fire detections in the city bbox from each configured
    satellite source and upsert into `fire_detections`.
    """
    settings = get_settings()
    city: CityBounds = get_city(city_slug)
    sources = sources or DEFAULT_SOURCES

    total_written = 0
    async with httpx.AsyncClient() as client:
        for source in sources:
            rows = await _fetch_source(client, settings.nasa_firms_map_key, source, city.bbox, day_range)
            for row in rows:
                _upsert_detection(db, city_slug=city.slug, source=source, row=row)
                total_written += 1

    db.commit()
    logger.info("FIRMS ingestion for %s wrote %d rows", city_slug, total_written)
    return total_written


def _upsert_detection(db: Session, *, city_slug: str, source: str, row: dict) -> None:
    stmt = (
        pg_insert(FireDetection)
        .values(
            city_slug=city_slug,
            latitude=float(row["latitude"]),
            longitude=float(row["longitude"]),
            confidence=str(row.get("confidence", "")),
            frp=float(row["frp"]) if row.get("frp") not in (None, "") else None,
            acq_date=row["acq_date"],
            acq_time=row["acq_time"],
            satellite=row.get("satellite") or source,
            daynight=row.get("daynight"),
        )
        .on_conflict_do_nothing(
            index_elements=["latitude", "longitude", "acq_date", "acq_time", "satellite"]
        )
    )
    db.execute(stmt)
