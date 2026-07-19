"""Advisory language coverage: all six langs return a script-correct fallback
when no LLM key is configured, and unknown langs degrade to English."""

from datetime import datetime, timezone

import pytest

import app.api.routes.advisory as advisory_routes
from app.geospatial.models import GridReading

NOW = datetime(2026, 7, 18, 6, 0, tzinfo=timezone.utc)


@pytest.fixture()
def seeded(db_session, monkeypatch):
    # Deterministic-fallback path regardless of any real key in .env.
    monkeypatch.setattr(advisory_routes, "complete", lambda **kw: None)
    db_session.add(
        GridReading(
            grid_id=1,
            city_slug="delhi-ncr",
            parameter="pm25",
            value=100.0,
            measured_at=NOW,
            contributing_sensor_count=4,
        )
    )
    db_session.commit()


@pytest.mark.parametrize(
    ("lang", "marker"),
    [
        ("en", "PM2.5 in Delhi NCR"),
        ("hi", "में PM2.5"),
        ("kn", "ನಲ್ಲಿ PM2.5"),
        ("ta", "இல் PM2.5"),
        ("bn", "PM2.5 বর্তমানে"),
        ("mr", "मध्ये PM2.5"),
    ],
)
def test_all_langs_fall_back_in_their_script(client, seeded, lang, marker):
    resp = client.get("/advisory", params={"lang": lang})
    assert resp.status_code == 200
    body = resp.json()
    assert body["lang"] == lang
    assert body["llm_used"] is False
    assert marker in body["advisory"]
    assert body["category"] == "Poor"


def test_unknown_lang_degrades_to_english(client, seeded):
    resp = client.get("/advisory", params={"lang": "fr"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["lang"] == "en"
    assert "PM2.5 in Delhi NCR" in body["advisory"]
