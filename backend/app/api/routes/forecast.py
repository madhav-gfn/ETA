"""
Step 5 API surface:
  GET /forecast/grid     — full-grid PM2.5 forecast for the map + slider
  GET /forecast/metrics  — RMSE-vs-persistence result from training
"""

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.ingestion.cities import DEFAULT_CITY
from app.models.inference import forecast_grid, model_available

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


@router.get("/metrics")
def get_metrics(city_slug: str = DEFAULT_CITY):
    path = CKPT_DIR / f"metrics_{city_slug}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Model not trained yet")
    return {"model_available": model_available(city_slug), **json.loads(path.read_text())}
