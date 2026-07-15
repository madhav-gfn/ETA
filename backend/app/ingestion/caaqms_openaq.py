"""
CAAQMS ground-sensor ingestion via the OpenAQ v3 API (Section 1.1).

The native CPCB portals are unreliable for high-frequency extraction, so the
official `openaq` Python SDK is used as a proxy — this matches the research
report's recommendation and its noted need for pagination-safe polling.

Requires OPENAQ_API_KEY (v3 of the OpenAQ API requires a key; there is no
anonymous tier). Polling cadence: hourly, per Section 1.1's "Polling Logic".

WATCHED PARAMETERS: pm25, pm10, no2, so2, co, o3 — the exact set called out
in Section 1.1's "Schema & Parameters".
"""

import logging
from datetime import datetime, timedelta, timezone

from openaq import OpenAQ
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.ingestion.cities import CityBounds, get_city
from app.ingestion.common import Reading, gap_fill_under_3h
from app.ingestion.models import CAAQMSReading

logger = logging.getLogger(__name__)

WATCHED_PARAMETERS = {"pm25", "pm10", "no2", "so2", "co", "o3"}


def _fetch_sensor_history(
    client: OpenAQ, sensor_id: int, hours_back: int
) -> list[Reading]:
    """Pull hourly-rollup measurements for one sensor over the lookback window."""
    now = datetime.now(timezone.utc)
    resp = client.measurements.list(
        sensors_id=sensor_id,
        data="hours",
        datetime_from=now - timedelta(hours=hours_back),
        datetime_to=now,
        limit=1000,
    )
    readings = [
        Reading(measured_at=_parse_iso(m.period.datetime_from.utc), value=m.value)
        for m in resp.results
    ]
    readings.sort(key=lambda r: r.measured_at)
    return readings


def _parse_iso(value: str) -> datetime:
    # OpenAQ returns e.g. "2026-07-15T09:00:00+00:00" or with a trailing "Z"
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def pull_caaqms_readings(
    db: Session, city_slug: str = "delhi-ncr", hours_back: int = 6
) -> int:
    """Discover CAAQMS stations in the city bbox, pull recent hourly readings
    for the watched parameters, gap-fill sub-3-hour dropouts, and upsert.

    Returns the number of rows written (including gap-filled rows).
    """
    settings = get_settings()
    city: CityBounds = get_city(city_slug)

    client = OpenAQ(api_key=settings.openaq_api_key)
    total_written = 0

    try:
        locations_resp = client.locations.list(iso="IN", bbox=city.bbox, limit=1000)

        for location in locations_resp.results:
            for sensor in location.sensors:
                if sensor.parameter.name not in WATCHED_PARAMETERS:
                    continue

                raw_readings = _fetch_sensor_history(client, sensor.id, hours_back)
                filled_readings = gap_fill_under_3h(raw_readings)

                for reading in filled_readings:
                    _upsert_reading(
                        db,
                        city_slug=city.slug,
                        location_id=location.id,
                        sensor_id=sensor.id,
                        station_name=location.name,
                        latitude=location.coordinates.latitude,
                        longitude=location.coordinates.longitude,
                        parameter=sensor.parameter.name,
                        unit=sensor.parameter.units,
                        reading=reading,
                    )
                    total_written += 1
    finally:
        client.close()

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
