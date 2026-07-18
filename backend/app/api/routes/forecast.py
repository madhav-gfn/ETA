"""
Step 5 API surface:
  GET /forecast/grid            — full-grid PM2.5 forecast for the map + slider
  GET /forecast/cell/{grid_id}  — per-cell observed history + hourly forecast series
  GET /forecast/metrics         — RMSE-vs-persistence result from training
"""

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.geospatial.models import GridCell, GridReading
from app.ingestion.cities import DEFAULT_CITY
from app.models.inference import forecast_cell, forecast_grid, model_available

router = APIRouter(prefix="/forecast", tags=["forecast"])

CKPT_DIR = Path(__file__).resolve().parents[3] / "checkpoints"


@router.get("/grid")
def get_forecast(
    city_slug: str = DEFAULT_CITY, horizon_hours: int = 24, db: Session = Depends(get_db)
):
    if horizon_hours not in (24, 48, 72):
        raise HTTPException(status_code=422, detail="horizon_hours must be 24, 48 or 72")
    result = forecast_grid(db, city_slug, horizon_hours)
    if result is None:
        raise HTTPException(
            status_code=409,
            detail="No trained model or insufficient cube history for this city",
        )
    return result


@router.get("/cell/{grid_id}")
def get_cell_forecast(
    grid_id: int,
    city_slug: str = DEFAULT_CITY,
    horizon_hours: int = 24,
    history_hours: int = 24,
    db: Session = Depends(get_db),
):
    """Observed last-N-hours + hourly forecast for one cell — the trend-chart
    payload the /forecast page's cell drill-down consumes."""
    if horizon_hours not in (24, 48, 72):
        raise HTTPException(status_code=422, detail="horizon_hours must be 24, 48 or 72")
    if not model_available(city_slug):
        raise HTTPException(status_code=409, detail="No trained model for this city")

    cell = db.get(GridCell, grid_id)
    if cell is None or cell.city_slug != city_slug:
        raise HTTPException(status_code=404, detail=f"No grid cell {grid_id} in {city_slug}")

    result = forecast_cell(db, city_slug, cell.row_idx, cell.col_idx, horizon_hours)
    if result is None:
        raise HTTPException(status_code=409, detail="Insufficient cube history for this city")

    observed = db.execute(
        select(GridReading.measured_at, GridReading.value)
        .where(
            GridReading.grid_id == grid_id,
            GridReading.parameter == "pm25",
        )
        .order_by(GridReading.measured_at.desc())
        .limit(history_hours)
    ).all()
    return {
        "city_slug": city_slug,
        "grid_id": grid_id,
        "centroid_lat": cell.centroid_lat,
        "centroid_lon": cell.centroid_lon,
        "horizon_hours": horizon_hours,
        "history": [
            {"timestep": ts.isoformat(), "pm25": round(v, 2)} for ts, v in reversed(observed)
        ],
        **result,
    }


@router.get("/metrics")
def get_metrics(city_slug: str = DEFAULT_CITY):
    path = CKPT_DIR / f"metrics_{city_slug}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Model not trained yet")
    out = {"model_available": model_available(city_slug), **json.loads(path.read_text())}
    # Merge horizon-specific evaluations (e.g. the 24h-direct model — the PS
    # brief's judged horizon) when trained.
    for extra in CKPT_DIR.glob(f"metrics_{city_slug}_*h.json"):
        data = json.loads(extra.read_text())
        h = data.get("horizon_hours")
        for key in (f"model_rmse_{h}h", f"persistence_rmse_{h}h"):
            if key in data:
                out[key] = data[key]
        out[f"beats_persistence_{h}h"] = data.get("beats_persistence")
    return out
