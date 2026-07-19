"""
Dashboard support endpoints (SITEMAP "NEEDED" items):
  GET /stats/summary  — server-computed city snapshot: mean/max PM2.5, CPCB
                        category, 24h trend delta (the Overview page currently
                        averages the full readings payload client-side)
  GET /stations       — CAAQMS station locations + freshness for map markers
  GET /cities         — onboarded cities with headline stats (replaces the
                        frontend's hardcoded CITIES array)
"""

from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.aqi import cpcb_category
from app.core.db import get_db
from app.geospatial.models import GridReading
from app.ingestion.cities import CITIES, DEFAULT_CITY
from app.ingestion.models import CAAQMSReading
from app.models.inference import model_available

router = APIRouter(tags=["stats"])


def _snapshot(db: Session, city_slug: str, parameter: str = "pm25"):
    """(measured_at, mean, max, cells_reporting) of the latest gridded hour,
    or None when nothing has been materialized yet."""
    latest_ts = db.execute(
        select(func.max(GridReading.measured_at)).where(
            GridReading.city_slug == city_slug, GridReading.parameter == parameter
        )
    ).scalar_one_or_none()
    if latest_ts is None:
        return None
    mean, mx, count = db.execute(
        select(func.avg(GridReading.value), func.max(GridReading.value), func.count()).where(
            GridReading.city_slug == city_slug,
            GridReading.parameter == parameter,
            GridReading.measured_at == latest_ts,
        )
    ).one()
    return latest_ts, mean, mx, count


@router.get("/stats/summary")
def stats_summary(
    city_slug: str = DEFAULT_CITY, parameter: str = "pm25", db: Session = Depends(get_db)
):
    snap = _snapshot(db, city_slug, parameter)
    if snap is None:
        return {"city_slug": city_slug, "parameter": parameter, "measured_at": None}
    latest_ts, mean, mx, count = snap

    # Trend: compare against the newest snapshot at least 24h older. The
    # nearest-hour match may be missing (ingestion gaps), so take max() below
    # the cutoff rather than an exact timestamp equality.
    prev_ts = db.execute(
        select(func.max(GridReading.measured_at)).where(
            GridReading.city_slug == city_slug,
            GridReading.parameter == parameter,
            GridReading.measured_at <= latest_ts - timedelta(hours=24),
        )
    ).scalar_one_or_none()
    trend_delta = None
    if prev_ts is not None:
        prev_mean = db.execute(
            select(func.avg(GridReading.value)).where(
                GridReading.city_slug == city_slug,
                GridReading.parameter == parameter,
                GridReading.measured_at == prev_ts,
            )
        ).scalar_one()
        trend_delta = round(mean - prev_mean, 1)

    return {
        "city_slug": city_slug,
        "parameter": parameter,
        "measured_at": latest_ts.isoformat(),
        "mean": round(mean, 1),
        "max": round(mx, 1),
        "cells_reporting": count,
        "category": cpcb_category(mean) if parameter == "pm25" else None,
        "trend_delta_24h": trend_delta,
        "trend_compared_to": prev_ts.isoformat() if prev_ts else None,
    }


@router.get("/stations")
def stations(city_slug: str = DEFAULT_CITY, db: Session = Depends(get_db)):
    """One row per CAAQMS station (OpenAQ location) — for map markers."""
    rows = db.execute(
        select(
            CAAQMSReading.location_id,
            func.max(CAAQMSReading.station_name),
            func.max(CAAQMSReading.latitude),
            func.max(CAAQMSReading.longitude),
            func.max(CAAQMSReading.measured_at),
            func.count(func.distinct(CAAQMSReading.parameter)),
        )
        .where(CAAQMSReading.city_slug == city_slug)
        .group_by(CAAQMSReading.location_id)
        .order_by(CAAQMSReading.location_id)
    ).all()
    return {
        "city_slug": city_slug,
        "station_count": len(rows),
        "stations": [
            {
                "location_id": loc_id,
                "station_name": name,
                "latitude": lat,
                "longitude": lon,
                "last_measured_at": last_at.isoformat() if last_at else None,
                "parameter_count": param_count,
            }
            for loc_id, name, lat, lon, last_at, param_count in rows
        ],
    }


@router.get("/cities")
def cities_list(db: Session = Depends(get_db)):
    """Registered cities + headline stats. A city is 'live' once it has a
    materialized gridded snapshot; until then it's registered-but-onboarding."""
    out = []
    for slug, city in CITIES.items():
        snap = _snapshot(db, slug)
        entry = {
            "city_slug": slug,
            "display_name": city.display_name,
            "bbox": list(city.bbox),
            "live": snap is not None,
            "model_available": model_available(slug),
            "measured_at": None,
            "mean_pm25": None,
            "max_pm25": None,
            "cells_reporting": 0,
        }
        if snap is not None:
            ts, mean, mx, count = snap
            entry.update(
                measured_at=ts.isoformat(),
                mean_pm25=round(mean, 1),
                max_pm25=round(mx, 1),
                cells_reporting=count,
                category=cpcb_category(mean),
            )
        out.append(entry)
    return {"cities": out}
