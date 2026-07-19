"""
Meteorology ingestion via Open-Meteo (free, keyless) — wind speed/direction,
temperature, humidity. Not one of the four Table-2 modalities, but required
by Step 4's feature cube and Step 6's upwind fire attribution.

One point per city (bbox center): meteorology varies smoothly at ~50km scale,
so a single hourly series is shared across all grid cells. The forecast API
serves recent + next-7-days; the archive API serves the historical backfill.
"""

import logging
from datetime import date, datetime, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.ingestion.cities import CityBounds, get_city
from app.ingestion.models import MeteoReading

logger = logging.getLogger(__name__)

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
HOURLY_VARS = "temperature_2m,relativehumidity_2m,windspeed_10m,winddirection_10m"


def _city_center(city: CityBounds) -> tuple[float, float]:
    min_lon, min_lat, max_lon, max_lat = city.bbox
    return (min_lat + max_lat) / 2, (min_lon + max_lon) / 2


def _parse_hourly(payload: dict) -> list[dict]:
    hourly = payload.get("hourly", {})
    times = hourly.get("time", [])
    rows = []
    for i, t in enumerate(times):
        temp = hourly.get("temperature_2m", [None] * len(times))[i]
        rh = hourly.get("relativehumidity_2m", [None] * len(times))[i]
        ws = hourly.get("windspeed_10m", [None] * len(times))[i]
        wd = hourly.get("winddirection_10m", [None] * len(times))[i]
        if temp is None and ws is None:
            continue  # archive rows beyond available history are all-null
        rows.append(
            {
                "measured_at": datetime.fromisoformat(t).replace(tzinfo=timezone.utc),
                "temperature_c": temp,
                "relative_humidity": rh,
                "wind_speed_kmh": ws,
                "wind_direction_deg": wd,
            }
        )
    return rows


async def pull_meteo(
    db: Session, city_slug: str = "delhi-ncr", past_days: int = 2, forecast_days: int = 3
) -> int:
    """Recent observations + short-term forecast from the forecast API."""
    city = get_city(city_slug)
    lat, lon = _city_center(city)
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            FORECAST_URL,
            params={
                "latitude": lat, "longitude": lon, "hourly": HOURLY_VARS,
                "past_days": past_days, "forecast_days": forecast_days,
                "timezone": "UTC",
            },
            timeout=60.0,
        )
        resp.raise_for_status()
        rows = _parse_hourly(resp.json())

    forecast_start = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    for row in rows:
        _upsert(db, city_slug=city.slug, is_forecast=row["measured_at"] > forecast_start, **row)
    db.commit()
    logger.info("Open-Meteo ingestion for %s wrote %d rows", city_slug, len(rows))
    return len(rows)


async def backfill_meteo(db: Session, city_slug: str = "delhi-ncr", days: int = 90) -> int:
    """Historical hourly meteorology from the archive API (one request)."""
    city = get_city(city_slug)
    lat, lon = _city_center(city)
    # The archive lags real time; the last couple of days come from the
    # forecast API's past_days window instead.
    end = date.today() - timedelta(days=2)
    start = end - timedelta(days=days)
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            ARCHIVE_URL,
            params={
                "latitude": lat, "longitude": lon, "hourly": HOURLY_VARS,
                "start_date": start.isoformat(), "end_date": end.isoformat(),
                "timezone": "UTC",
            },
            timeout=120.0,
        )
        resp.raise_for_status()
        rows = _parse_hourly(resp.json())

    for row in rows:
        _upsert(db, city_slug=city.slug, is_forecast=False, **row)
    db.commit()
    logger.info("Open-Meteo backfill for %s wrote %d rows (%d days)", city_slug, len(rows), days)
    return len(rows)


def _upsert(db: Session, *, city_slug: str, measured_at, is_forecast: bool, **fields) -> None:
    stmt = (
        pg_insert(MeteoReading)
        .values(city_slug=city_slug, measured_at=measured_at, is_forecast=is_forecast, **fields)
        .on_conflict_do_update(
            index_elements=["city_slug", "measured_at"],
            set_={**fields, "is_forecast": is_forecast},
        )
    )
    db.execute(stmt)


def latest_meteo(db: Session, city_slug: str = "delhi-ncr") -> MeteoReading | None:
    """Most recent non-forecast meteorology row — used by the attribution
    agent for current wind vectors."""
    stmt = (
        select(MeteoReading)
        .where(MeteoReading.city_slug == city_slug, MeteoReading.is_forecast.is_(False))
        .order_by(MeteoReading.measured_at.desc())
        .limit(1)
    )
    return db.execute(stmt).scalars().first()
