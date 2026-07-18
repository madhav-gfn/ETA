"""Dispatch-lifecycle tests for the persisted agent run history: pagination,
status transitions (new → dispatched → inspected → closed), and the
signal-to-dispatch response-time metric."""

import json
from datetime import datetime, timedelta, timezone

from app.agents.models import AgentRunRecord

PAYLOAD = json.dumps({"alert": {"grid_id": 1}, "attribution": {}, "plan": {}})


def _seed_run(db, city="delhi-ncr", hours_ago=1):
    record = AgentRunRecord(
        city_slug=city,
        payload=PAYLOAD,
        completed_at=datetime.now(timezone.utc) - timedelta(hours=hours_ago),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def test_runs_empty(client):
    resp = client.get("/agents/runs")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["runs"] == []
    assert body["mean_signal_to_dispatch_minutes"] is None


def test_runs_pagination(client, db_session):
    for i in range(5):
        _seed_run(db_session, hours_ago=i + 1)

    resp = client.get("/agents/runs", params={"limit": 2, "offset": 2})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 5
    assert len(body["runs"]) == 2
    # Newest-first ordering (run 1 is the most recent): offset 2 skips runs 1-2.
    assert [r["run_id"] for r in body["runs"]] == [3, 4]
    assert all(r["status"] == "new" for r in body["runs"])


def test_status_lifecycle(client, db_session):
    record = _seed_run(db_session)

    resp = client.post(
        f"/agents/runs/{record.id}/status",
        params={"status": "dispatched", "assignee": "Inspector Sharma"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "dispatched"
    assert body["assigned_to"] == "Inspector Sharma"
    assert body["dispatched_at"] is not None
    # Run completed ~1h ago, dispatched now → ~60 min signal-to-dispatch.
    assert 55 <= body["signal_to_dispatch_minutes"] <= 65

    assert client.post(f"/agents/runs/{record.id}/status", params={"status": "inspected"}).status_code == 200
    closed = client.post(f"/agents/runs/{record.id}/status", params={"status": "closed"})
    assert closed.status_code == 200
    assert closed.json()["status"] == "closed"
    assert closed.json()["closed_at"] is not None


def test_status_transition_order_enforced(client, db_session):
    record = _seed_run(db_session)
    # Can't skip straight from new to closed.
    resp = client.post(f"/agents/runs/{record.id}/status", params={"status": "closed"})
    assert resp.status_code == 409


def test_status_unknown_run_404(client):
    resp = client.post("/agents/runs/999/status", params={"status": "dispatched"})
    assert resp.status_code == 404


def test_status_invalid_value_422(client, db_session):
    record = _seed_run(db_session)
    resp = client.post(f"/agents/runs/{record.id}/status", params={"status": "resolved"})
    assert resp.status_code == 422


def test_recommendations_include_tracking_fields(client, db_session):
    _seed_run(db_session)
    resp = client.get("/agents/recommendations")
    assert resp.status_code == 200
    run = resp.json()["runs"][0]
    assert run["status"] == "new"
    assert "run_id" in run
    assert run["alert"] == {"grid_id": 1}
