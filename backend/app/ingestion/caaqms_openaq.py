"""
CAAQMS ground-sensor ingestion via the OpenAQ v3 REST API (Section 1.1).

Strategy: fetch all locations in the city bbox in one paginated call, then
fetch measurements per location (not per sensor) — far fewer requests.
Uses httpx with explicit timeouts to avoid DNS/connect hangs.

WATCHED PARAMETERS: pm25, pm10, no2, so2, co, o3
"""

import logging
import time
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.ingestion.cities import CityBounds, get_city
from app.ingestion.common import Reading, gap_fill_under_3h
from app.ingestion.models import CAAQMSReading

logger = logging.getLogger(__name__)

WATCHED_PARAMETERS = {"pm25", "pm10", "no2", "so2", "co", "o3"}
BASE_URL = "https://api.openaq.org/v3"
TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=5.0)
PAGE_LIMIT = 100


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _get(client: httpx.Client, path: str, **params) -> dict:
    for attempt in range(3):
        resp = client.get(f"{BASE_URL}{path}", params=params)
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("retry-after", 60))
            logger.warning("Rate limited, waiting %ds", retry_after)
            time.sleep(retry_after)
            continue
        resp.raise_for_status()
        return resp.json()
    resp.raise_for_status()
    return {}


def _fetch_locations(client: httpx.Client, bbox: tuple) -> list[dict]:
    """Fetch all locations in bbox, paginating through results."""
    min_lon, min_lat, max_lon, max_lat = bbox
    locations = []
    page = 1
    while True:
        data = _get(client, "/locations", iso="IN",
                    bbox=f"{min_lon},{min_lat},{max_lon},{max_lat}",
                    limit=PAGE_LIMIT, page=page)
        results = data.get("results", [])
        locations.extend(results)
        if len(results) < PAGE_LIMIT:
            break
        page += 1
        time.sleep(0.5)
    return locations


def _fetch_location_latest(client: httpx.Client, location_id: int) -> list[dict]:
    """Latest value per sensor for a location (OpenAQ v3 /locations/{id}/latest)."""
    data = _get(client, f"/locations/{location_id}/latest", limit=1000)
    return data.get("results", [])


def _fetch_sensor_hours(
    client: httpx.Client, sensor_id: int, hours_back: int
) -> list[dict]:
    """Hourly history for one sensor (OpenAQ v3 /sensors/{id}/hours), paginated."""
    now = datetime.now(timezone.utc)
    results: list[dict] = []
    page = 1
    while True:
        data = _get(
            client, f"/sensors/{sensor_id}/hours",
            datetime_from=(now - timedelta(hours=hours_back)).isoformat(),
            datetime_to=now.isoformat(),
            limit=1000, page=page,
        )
        batch = data.get("results", [])
        results.extend(batch)
        if len(batch) < 1000:
            return results
        page += 1
        time.sleep(0.3)


def pull_caaqms_readings(
    db: Session, city_slug: str = "delhi-ncr", hours_back: int = 1
) -> int:
    settings = get_settings()
    city: CityBounds = get_city(city_slug)
    headers = {"X-API-Key": settings.openaq_api_key}
    total_written = 0

    with httpx.Client(headers=headers, timeout=TIMEOUT) as client:
        locations = _fetch_locations(client, city.bbox)
        logger.info("CAAQMS: found %d locations for %s", len(locations), city_slug)

        # Build sensor_id -> location metadata map for upserts
        sensor_meta: dict[int, dict] = {}
        for loc in locations:
            for sensor in loc.get("sensors", []):
                param = sensor.get("parameter", {}).get("name", "")
                if param in WATCHED_PARAMETERS:
                    sensor_meta[sensor["id"]] = {
                        "location_id": loc["id"],
                        "station_name": loc["name"],
                        "latitude": loc["coordinates"]["latitude"],
                        "longitude": loc["coordinates"]["longitude"],
                        "parameter": param,
                        "unit": sensor["parameter"].get("units", ""),
                    }

        logger.info("CAAQMS: %d watched sensors across %d locations", len(sensor_meta), len(locations))

        # One request per location instead of one per sensor
        for i, loc in enumerate(locations):
            loc_sensors = {
                s["id"]: s for s in loc.get("sensors", [])
                if s.get("parameter", {}).get("name", "") in WATCHED_PARAMETERS
            }
            if not loc_sensors:
                continue

            logger.info("CAAQMS: fetching location %d/%d — %s", i + 1, len(locations), loc["name"])
            by_sensor: dict[int, list[Reading]] = {}
            if hours_back <= 2:
                # Hourly cadence: one /latest call per location covers every sensor.
                try:
                    latest = _fetch_location_latest(client, loc["id"])
                except httpx.HTTPError as exc:
                    logger.warning("CAAQMS: skipping location %d: %s", loc["id"], exc)
                    time.sleep(1.0)
                    continue
                cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back + 1)
                for m in latest:
                    sid = m.get("sensorsId")
                    if sid not in loc_sensors or m.get("value") is None:
                        continue
                    ts = m.get("datetime", {}).get("utc")
                    if not ts or _parse_iso(ts) < cutoff:
                        continue
                    by_sensor.setdefault(sid, []).append(
                        Reading(measured_at=_parse_iso(ts), value=m["value"])
                    )
            else:
                # Backfill: hourly series per sensor.
                for sid in loc_sensors:
                    try:
                        hours = _fetch_sensor_hours(client, sid, hours_back)
                    except httpx.HTTPError as exc:
                        logger.warning("CAAQMS: skipping sensor %d: %s", sid, exc)
                        time.sleep(1.0)
                        continue
                    for m in hours:
                        if m.get("value") is None:
                            continue
                        ts = m.get("period", {}).get("datetimeFrom", {}).get("utc")
                        if not ts:
                            continue
                        by_sensor.setdefault(sid, []).append(
                            Reading(measured_at=_parse_iso(ts), value=m["value"])
                        )
                    time.sleep(0.3)

            for sid, readings in by_sensor.items():
                readings.sort(key=lambda r: r.measured_at)
                filled = gap_fill_under_3h(readings)
                meta = sensor_meta[sid]
                for reading in filled:
                    _upsert_reading(db, city_slug=city.slug, sensor_id=sid,
                                    reading=reading, **meta)
                    total_written += 1

            time.sleep(0.5)  # stay under rate limit between location requests

    db.commit()
    logger.info("CAAQMS ingestion for %s wrote %d rows", city_slug, total_written)
    return total_written


def _upsert_reading(
    db: Session,
    *,
    city_slug: str,
    location_id: int,
    sensor_id: int,
    station_name: str,
    latitude: float,
    longitude: float,
    parameter: str,
    unit: str,
    reading: Reading,
) -> None:
    stmt = (
        pg_insert(CAAQMSReading)
        .values(
            city_slug=city_slug,
            location_id=location_id,
            sensor_id=sensor_id,
            station_name=station_name,
            latitude=latitude,
            longitude=longitude,
            parameter=parameter,
            value=reading.value,
            unit=unit,
            measured_at=reading.measured_at,
            is_interpolated=reading.is_interpolated,
        )
        .on_conflict_do_update(
            index_elements=[CAAQMSReading.sensor_id, CAAQMSReading.measured_at],
            set_={"value": reading.value, "is_interpolated": reading.is_interpolated},
        )
    )
    db.execute(stmt)


def latest_readings(db: Session, city_slug: str = "delhi-ncr", limit: int = 100):
    """Read-path helper backing GET /ingestion/caaqms/latest."""
    stmt = (
        select(CAAQMSReading)
        .where(CAAQMSReading.city_slug == city_slug)
        .order_by(CAAQMSReading.measured_at.desc())
        .limit(limit)
    )
    return db.execute(stmt).scalars().all()
