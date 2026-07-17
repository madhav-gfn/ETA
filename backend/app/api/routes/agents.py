"""
Step 6 API surface:
  POST /agents/run              — run the full agent graph now (demo-friendly);
                                  pass synthetic_grid_id to stage an anomaly drill
  GET  /agents/recommendations  — latest stored enforcement runs
"""

import json

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.graph import WHO_PM25_THRESHOLD, run_agents
from app.agents.models import AgentRunRecord
from app.core.db import get_db
from app.ingestion.cities import DEFAULT_CITY

router = APIRouter(prefix="/agents", tags=["agents"])


@router.post("/run")
def trigger_agents(
    city_slug: str = DEFAULT_CITY,
    threshold: float = WHO_PM25_THRESHOLD,
    synthetic_grid_id: int | None = None,
    db: Session = Depends(get_db),
):
    result = run_agents(db, city_slug, threshold, synthetic_grid_id)
    if result is None:
        return {"anomaly_found": False, "message": f"No grid cell above {threshold} µg/m³ right now."}
    record = AgentRunRecord(
        city_slug=city_slug,
        payload=result.model_dump_json(),
        completed_at=result.completed_at,
    )
    db.add(record)
    db.commit()
    return {"anomaly_found": True, **result.model_dump(mode="json")}


@router.get("/recommendations")
def recommendations(city_slug: str = DEFAULT_CITY, limit: int = 5, db: Session = Depends(get_db)):
    rows = db.execute(
        select(AgentRunRecord)
        .where(AgentRunRecord.city_slug == city_slug)
        .order_by(AgentRunRecord.completed_at.desc())
        .limit(limit)
    ).scalars().all()
    return {
        "city_slug": city_slug,
        "runs": [json.loads(r.payload) for r in rows],
    }
