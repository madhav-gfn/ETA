"""
Step 3 API surface:
  POST /grid/generate       — (re)generate the city grid (idempotent)
  POST /grid/materialize    — run IDW over the latest sensor hour now
  GET  /grid/cells          — cell geometries for the map
  GET  /grid/readings       — latest (or at=) gridded state for one parameter
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.geospatial.grid import generate_grid, load_cells
from app.geospatial.materialize import materialize_grid_readings
from app.geospatial.models import GridReading
from app.ingestion.cities import DEFAULT_CITY

router = APIRouter(prefix="/grid", tags=["grid"])


@router.post("/generate")
def trigger_generate(city_slug: str = DEFAULT_CITY, db: Session = Depends(get_db)):
    count = generate_grid(db, city_slug)
    return {"city_slug": city_slug, "cell_count": count}


@router.post("/materialize")
def trigger_materialize(
    city_slug: str = DEFAULT_CITY, window_hours: int = 3, db: Session = Depends(get_db)
):
    try:
        return materialize_grid_readings(db, city_slug, window_hours)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/cells")
def grid_cells(city_slug: str = DEFAULT_CITY, db: Session = Depends(get_db)):
    cells = load_cells(db, city_slug)
    return {
        "city_slug": city_slug,
        "cell_count": len(cells),
        "cells": [
            {
                "grid_id": c.grid_id,
                "row_idx": c.row_idx,
                "col_idx": c.col_idx,
                "centroid_lat": c.centroid_lat,
                "centroid_lon": c.centroid_lon,
            }
            for c in cells
        ],
    }


@router.get("/readings")
def grid_readings(
    city_slug: str = DEFAULT_CITY,
    parameter: str = "pm25",
    at: datetime | None = None,
    db: Session = Depends(get_db),
):
    """Full-grid snapshot for one parameter at one timestamp (default: the
    latest materialized hour)."""
    if at is None:
        at = db.execute(
            select(func.max(GridReading.measured_at)).where(
                GridReading.city_slug == city_slug,
                GridReading.parameter == parameter,
            )
        ).scalar_one_or_none()
        if at is None:
            return {"city_slug": city_slug, "parameter": parameter, "measured_at": None, "readings": []}

    rows = db.execute(
        select(GridReading).where(
            GridReading.city_slug == city_slug,
            GridReading.parameter == parameter,
            GridReading.measured_at == at,
        )
    ).scalars().all()
    return {
        "city_slug": city_slug,
        "parameter": parameter,
        "measured_at": at.isoformat(),
        "readings": [
            {
                "grid_id": r.grid_id,
                "value": r.value,
                "contributing_sensor_count": r.contributing_sensor_count,
            }
            for r in rows
        ],
    }
