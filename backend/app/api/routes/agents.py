"""
Step 6 API surface:
  POST /agents/run                 — run the full agent graph now (demo-friendly);
                                     pass synthetic_grid_id to stage an anomaly drill
  GET  /agents/recommendations     — latest stored enforcement runs
  GET  /agents/runs                — paginated persisted run history + dispatch state
  POST /agents/runs/{id}/status    — dispatch lifecycle: new → dispatched →
                                     inspected → closed (stamps each transition,
                                     backing the signal-to-intervention metric)
"""

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.graph import WHO_PM25_THRESHOLD, run_agents
from app.agents.models import AgentRunRecord
from app.core.db import get_db
from app.ingestion.cities import DEFAULT_CITY

router = APIRouter(prefix="/agents", tags=["agents"])

# valid current status -> allowed next status
TRANSITIONS = {"new": "dispatched", "dispatched": "inspected", "inspected": "closed"}
STATUS_STAMPS = {"dispatched": "dispatched_at", "inspected": "inspected_at", "closed": "closed_at"}


def _minutes(later: datetime | None, earlier: datetime | None) -> float | None:
    if later is None or earlier is None:
        return None
    if later.tzinfo is None:
        later = later.replace(tzinfo=timezone.utc)
    if earlier.tzinfo is None:
        earlier = earlier.replace(tzinfo=timezone.utc)
    return round((later - earlier).total_seconds() / 60, 1)


def _run_out(r: AgentRunRecord) -> dict:
    return {
        "run_id": r.id,
        "status": r.status,
        "assigned_to": r.assigned_to,
        "completed_at": r.completed_at.isoformat(),
        "dispatched_at": r.dispatched_at.isoformat() if r.dispatched_at else None,
        "inspected_at": r.inspected_at.isoformat() if r.inspected_at else None,
        "closed_at": r.closed_at.isoformat() if r.closed_at else None,
        # the brief's judged metric: time from anomaly signal to dispatch
        "signal_to_dispatch_minutes": _minutes(r.dispatched_at, r.completed_at),
        **json.loads(r.payload),
    }


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
    return {"anomaly_found": True, "run_id": record.id, "status": record.status,
            **result.model_dump(mode="json")}


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
        "runs": [_run_out(r) for r in rows],
    }


@router.get("/runs")
def run_history(
    city_slug: str = DEFAULT_CITY,
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """Persisted, paginated run history with dispatch state — the /enforcement
    page's replacement for its session-local list."""
    total = db.execute(
        select(func.count()).select_from(AgentRunRecord).where(AgentRunRecord.city_slug == city_slug)
    ).scalar_one()
    rows = db.execute(
        select(AgentRunRecord)
        .where(AgentRunRecord.city_slug == city_slug)
        .order_by(AgentRunRecord.completed_at.desc())
        .limit(limit)
        .offset(offset)
    ).scalars().all()
    dispatch_times = [
        m for r in rows if (m := _minutes(r.dispatched_at, r.completed_at)) is not None
    ]
    return {
        "city_slug": city_slug,
        "total": total,
        "limit": limit,
        "offset": offset,
        "mean_signal_to_dispatch_minutes": (
            round(sum(dispatch_times) / len(dispatch_times), 1) if dispatch_times else None
        ),
        "runs": [_run_out(r) for r in rows],
    }


@router.post("/runs/{run_id}/status")
def update_run_status(
    run_id: int,
    status: str,
    assignee: str | None = None,
    db: Session = Depends(get_db),
):
    if status not in STATUS_STAMPS:
        raise HTTPException(status_code=422, detail=f"status must be one of {list(STATUS_STAMPS)}")
    record = db.get(AgentRunRecord, run_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"No agent run with id {run_id}")
    if TRANSITIONS.get(record.status) != status:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot move run from '{record.status}' to '{status}' "
                   f"(order is new → dispatched → inspected → closed)",
        )
    record.status = status
    setattr(record, STATUS_STAMPS[status], datetime.now(timezone.utc))
    if status == "dispatched" and assignee:
        record.assigned_to = assignee
    db.commit()
    db.refresh(record)
    return _run_out(record)
