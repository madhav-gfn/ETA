"""Guard-path tests for /forecast/cell — the rollout itself needs a trained
checkpoint + cube history, which the SQLite test env doesn't have."""


def test_cell_forecast_invalid_horizon(client):
    resp = client.get("/forecast/cell/1", params={"horizon_hours": 36})
    assert resp.status_code == 422


def test_cell_forecast_no_model_409(client):
    # Mumbai is registered but untrained — the model check must fire before
    # any grid lookup so it also holds where grid tables don't exist.
    resp = client.get("/forecast/cell/1", params={"city_slug": "mumbai"})
    assert resp.status_code == 409
