"""Tests for the dashboard-support endpoints: /stats/summary, /stations,
/cities, and the consolidated /ingestion/summary."""

from datetime import datetime, timedelta, timezone

from app.geospatial.models import GridReading
from app.ingestion.models import CAAQMSReading

NOW = datetime(2026, 7, 18, 6, 0, tzinfo=timezone.utc)


def _seed_grid_readings(db, values, measured_at, city="delhi-ncr"):
    for grid_id, value in enumerate(values, start=1):
        db.add(
            GridReading(
                grid_id=grid_id,
                city_slug=city,
                parameter="pm25",
                value=value,
                measured_at=measured_at,
                contributing_sensor_count=3,
            )
        )
    db.commit()


def test_stats_summary_empty(client):
    resp = client.get("/stats/summary")
    assert resp.status_code == 200
    assert resp.json()["measured_at"] is None


def test_stats_summary_with_trend(client, db_session):
    _seed_grid_readings(db_session, [80.0, 100.0, 120.0], NOW - timedelta(hours=25))
    _seed_grid_readings(db_session, [100.0, 120.0, 140.0], NOW)

    resp = client.get("/stats/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["mean"] == 120.0
    assert body["max"] == 140.0
    assert body["cells_reporting"] == 3
    assert body["category"] == "Poor"
    # mean rose from 100 → 120 vs the snapshot ≥24h earlier
    assert body["trend_delta_24h"] == 20.0
    assert body["trend_compared_to"] is not None


def test_stations_grouped_by_location(client, db_session):
    for i, (loc, param) in enumerate([(101, "pm25"), (101, "pm10"), (202, "pm25")]):
        db_session.add(
            CAAQMSReading(
                city_slug="delhi-ncr",
                location_id=loc,
                sensor_id=1000 + i,
                station_name=f"Station {loc}",
                latitude=28.6,
                longitude=77.2,
                parameter=param,
                value=90.0,
                unit="µg/m³",
                measured_at=NOW,
            )
        )
    db_session.commit()

    resp = client.get("/stations")
    assert resp.status_code == 200
    body = resp.json()
    assert body["station_count"] == 2
    st = {s["location_id"]: s for s in body["stations"]}
    assert st[101]["parameter_count"] == 2
    assert st[202]["station_name"] == "Station 202"


def test_cities_registered_vs_live(client, db_session):
    _seed_grid_readings(db_session, [50.0, 70.0], NOW)

    resp = client.get("/cities")
    assert resp.status_code == 200
    cities = {c["city_slug"]: c for c in resp.json()["cities"]}
    assert cities["delhi-ncr"]["live"] is True
    assert cities["delhi-ncr"]["mean_pm25"] == 60.0
    assert cities["delhi-ncr"]["category"] == "Satisfactory"
    # Mumbai is registered in cities.py but has no gridded data yet.
    assert cities["mumbai"]["live"] is False
    assert cities["mumbai"]["mean_pm25"] is None


def test_ingestion_summary_reflects_runs_and_rows(client, db_session, monkeypatch):
    import app.api.routes.ingestion as ingestion_routes

    monkeypatch.setattr(ingestion_routes, "pull_caaqms_readings", lambda db, city_slug, **kw: 3)
    client.post("/ingestion/caaqms/run")
    db_session.add(
        CAAQMSReading(
            city_slug="delhi-ncr",
            location_id=1,
            sensor_id=1,
            station_name="S",
            latitude=28.6,
            longitude=77.2,
            parameter="pm25",
            value=90.0,
            unit="µg/m³",
            measured_at=NOW,
        )
    )
    db_session.commit()

    resp = client.get("/ingestion/summary")
    assert resp.status_code == 200
    body = resp.json()
    sources = {s["source"]: s for s in body["sources"]}
    assert set(sources) == {"caaqms", "firms", "osm", "sentinel5p", "meteo"}
    assert sources["caaqms"]["table_rows"] == 1
    assert sources["caaqms"]["latest_data_at"] is not None
    assert sources["caaqms"]["last_run"]["status"] == "success"
    assert sources["caaqms"]["last_run"]["records_ingested"] == 3
    assert sources["firms"]["table_rows"] == 0
    assert sources["firms"]["last_run"] is None
