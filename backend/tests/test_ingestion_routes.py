"""
Route-level tests. The actual pullers hit external APIs (OpenAQ, FIRMS,
Overpass, CDSE) that aren't reachable from this sandbox, so these tests
monkeypatch the puller functions to confirm the routes wire request params
through correctly and shape responses as expected — not that the live
integrations work end-to-end (that needs real credentials + network).
"""

import app.api.routes.ingestion as ingestion_routes


def test_trigger_caaqms_run(client, monkeypatch):
    monkeypatch.setattr(ingestion_routes, "pull_caaqms_readings", lambda db, city_slug, **kw: 42)

    resp = client.post("/ingestion/caaqms/run", params={"city_slug": "delhi-ncr"})

    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "source": "caaqms",
        "city_slug": "delhi-ncr",
        "records_ingested": 42,
        "status": "success",
    }


def test_trigger_firms_run(client, monkeypatch):
    async def fake_pull(db, city_slug):
        return 7

    monkeypatch.setattr(ingestion_routes, "pull_fire_detections", fake_pull)

    resp = client.post("/ingestion/firms/run", params={"city_slug": "mumbai"})

    assert resp.status_code == 200
    assert resp.json()["records_ingested"] == 7
    assert resp.json()["city_slug"] == "mumbai"


def test_trigger_run_reports_failure_status(client, monkeypatch):
    def raising_pull(db, city_slug, **kw):
        raise RuntimeError("upstream unavailable")

    monkeypatch.setattr(ingestion_routes, "pull_caaqms_readings", raising_pull)

    # track_run re-raises after logging the failure, so the route itself
    # propagates a 500 — confirming failures aren't silently swallowed.
    import pytest

    with pytest.raises(RuntimeError):
        client.post("/ingestion/caaqms/run")


def test_ingestion_status_empty_initially(client):
    resp = client.get("/ingestion/status")
    assert resp.status_code == 200
    assert resp.json() == []


def test_ingestion_status_reflects_previous_runs(client, monkeypatch):
    monkeypatch.setattr(ingestion_routes, "pull_caaqms_readings", lambda db, city_slug, **kw: 5)
    client.post("/ingestion/caaqms/run")

    resp = client.get("/ingestion/status")
    assert resp.status_code == 200
    logs = resp.json()
    assert len(logs) == 1
    assert logs[0]["source"] == "caaqms"
    assert logs[0]["records_ingested"] == 5
    assert logs[0]["status"] == "success"


def test_caaqms_latest_empty_initially(client):
    resp = client.get("/ingestion/caaqms/latest")
    assert resp.status_code == 200
    assert resp.json() == []
