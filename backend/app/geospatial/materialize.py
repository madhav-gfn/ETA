"""
Hourly grid materialization (Step 3.4): project the latest hour of raw
CAAQMS sensor readings onto every grid centroid via IDW and persist to
`grid_readings`. First job in the pipeline that consumes Step 2 output
rather than an external API.
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.geospatial.grid import load_cells
from app.geospatial.idw import SensorSample, idw_estimate, leave_one_out_rmse
from app.geospatial.models import GridReading
from app.ingestion.caaqms_openaq import WATCHED_PARAMETERS
from app.ingestion.models import CAAQMSReading

logger = logging.getLogger(__name__)


def _sensor_samples(
    db: Session, city_slug: str, parameter: str, window_start: datetime, window_end: datetime
) -> tuple[list[SensorSample], datetime | None]:
    """Latest reading per sensor for `parameter` inside the window.
    Returns samples plus the most common measurement hour (used as the
    grid_readings timestamp)."""
    stmt = (
        select(CAAQMSReading)
        .where(
            CAAQMSReading.city_slug == city_slug,
            CAAQMSReading.parameter == parameter,
            CAAQMSReading.measured_at >= window_start,
            CAAQMSReading.measured_at <= window_end,
        )
        .order_by(CAAQMSReading.sensor_id, CAAQMSReading.measured_at.desc())
    )
    rows = db.execute(stmt).scalars().all()

    latest_by_sensor: dict[int, CAAQMSReading] = {}
    for r in rows:
        latest_by_sensor.setdefault(r.sensor_id, r)  # first seen = latest (desc order)

    if not latest_by_sensor:
        return [], None

    samples = [
        SensorSample(latitude=r.latitude, longitude=r.longitude, value=r.value)
        for r in latest_by_sensor.values()
    ]
    # Truncate the newest timestamp to the hour for a stable grid timestamp.
    newest = max(r.measured_at for r in latest_by_sensor.values())
    stamp = newest.replace(minute=0, second=0, microsecond=0)
    return samples, stamp


def materialize_grid_readings(
    db: Session, city_slug: str = "delhi-ncr", window_hours: int = 3
) -> dict:
    """Run IDW for every watched parameter over the last `window_hours` of
    sensor data. Returns per-parameter stats including leave-one-out RMSE."""
    cells = load_cells(db, city_slug)
    if not cells:
        raise ValueError(f"No grid cells for '{city_slug}' — run grid generation first")

    now = datetime.now(timezone.utc)
    window_start = now - timedelta(hours=window_hours)
    stats: dict[str, dict] = {}
    total_written = 0

    for parameter in sorted(WATCHED_PARAMETERS):
        samples, stamp = _sensor_samples(db, city_slug, parameter, window_start, now)
        if not samples or stamp is None:
            stats[parameter] = {"sensors": 0, "cells_covered": 0}
            continue

        covered = 0
        for cell in cells:
            est = idw_estimate(cell.centroid_lat, cell.centroid_lon, samples)
            if est is None:
                continue
            value, contributing = est
            stmt = (
                pg_insert(GridReading)
                .values(
                    grid_id=cell.grid_id,
                    city_slug=city_slug,
                    parameter=parameter,
                    value=round(value, 3),
                    measured_at=stamp,
                    interpolation_method="idw",
                    contributing_sensor_count=contributing,
                )
                .on_conflict_do_update(
                    index_elements=["grid_id", "parameter", "measured_at"],
                    set_={"value": round(value, 3), "contributing_sensor_count": contributing},
                )
            )
            db.execute(stmt)
            covered += 1
            total_written += 1

        loo = leave_one_out_rmse(samples)
        stats[parameter] = {
            "sensors": len(samples),
            "cells_covered": covered,
            "measured_at": stamp.isoformat(),
            "loo_rmse": round(loo[0], 3) if loo else None,
            "loo_evaluated": loo[1] if loo else 0,
        }

    db.commit()
    logger.info("Materialized %d grid readings for %s", total_written, city_slug)
    return {"city_slug": city_slug, "total_written": total_written, "parameters": stats}
