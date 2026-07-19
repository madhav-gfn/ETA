"""
Step 4 API surface:
  POST /features/build   — assemble cubes for a time range (defaults: all
                           hours we have sensor data for)
  GET  /features/cubes   — manifest listing
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.features.cube import build_cubes
from app.features.models import FeatureCubeManifest
from app.ingestion.cities import DEFAULT_CITY
from app.ingestion.models import CAAQMSReading

router = APIRouter(prefix="/features", tags=["features"])


@router.post("/build")
def trigger_build(
    city_slug: str = DEFAULT_CITY,
    start: datetime | None = None,
    end: datetime | None = None,
    db: Session = Depends(get_db),
):
    if start is None or end is None:
        lo, hi = db.execute(
            select(func.min(CAAQMSReading.measured_at), func.max(CAAQMSReading.measured_at))
            .where(CAAQMSReading.city_slug == city_slug)
        ).one()
        if lo is None:
            raise HTTPException(status_code=409, detail="No sensor data ingested yet")
        start = start or lo
        end = end or hi
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    try:
        return build_cubes(db, city_slug, start, end)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/cubes")
def list_cubes(city_slug: str = DEFAULT_CITY, limit: int = 50, db: Session = Depends(get_db)):
    rows = db.execute(
        select(FeatureCubeManifest)
        .where(FeatureCubeManifest.city_slug == city_slug)
        .order_by(FeatureCubeManifest.timestep.desc())
        .limit(limit)
    ).scalars().all()
    total = db.execute(
        select(func.count()).select_from(FeatureCubeManifest)
        .where(FeatureCubeManifest.city_slug == city_slug)
    ).scalar_one()
    return {
        "city_slug": city_slug,
        "total_cubes": total,
        "cubes": [
            {
                "timestep": r.timestep.isoformat(),
                "shape": [r.n_rows, r.n_cols, len(r.channels.split(","))],
                "storage_path": r.storage_path,
            }
            for r in rows
        ],
    }
