import math

from app.geospatial.grid import CELL_SIZE_M, generate_cells, grid_dimensions
from app.geospatial.idw import (
    SensorSample,
    distance_m,
    idw_estimate,
    leave_one_out_rmse,
)
from app.ingestion.cities import get_city


# --- grid generation -------------------------------------------------------

def test_grid_dimensions_cover_delhi_bbox():
    city = get_city("delhi-ncr")
    n_rows, n_cols, min_x, min_y, max_x, max_y = grid_dimensions(city)
    assert n_cols * CELL_SIZE_M >= (max_x - min_x)
    assert n_rows * CELL_SIZE_M >= (max_y - min_y)
    # Delhi bbox is ~50km x ~53km — sanity-check the order of magnitude.
    assert 40 <= n_cols <= 70
    assert 40 <= n_rows <= 70


def test_generate_cells_is_deterministic():
    city = get_city("delhi-ncr")
    a = generate_cells(city)
    b = generate_cells(city)
    assert a == b
    # Unique (row, col) keys — idempotent upsert cannot duplicate.
    keys = {(c["row_idx"], c["col_idx"]) for c in a}
    assert len(keys) == len(a)


def test_generated_centroids_fall_near_bbox():
    city = get_city("delhi-ncr")
    cells = generate_cells(city)
    min_lon, min_lat, max_lon, max_lat = city.bbox
    for c in cells[:: max(1, len(cells) // 50)]:
        assert min_lat - 0.05 <= c["centroid_lat"] <= max_lat + 0.05
        assert min_lon - 0.05 <= c["centroid_lon"] <= max_lon + 0.05


# --- IDW -------------------------------------------------------------------

def test_distance_m_known_value():
    # 1 degree latitude ≈ 111.2 km
    d = distance_m(28.0, 77.0, 29.0, 77.0)
    assert abs(d - 111_195) < 500


def test_idw_exact_at_sensor_location():
    samples = [
        SensorSample(28.60, 77.20, 100.0),
        SensorSample(28.70, 77.30, 50.0),
    ]
    est = idw_estimate(28.60, 77.20, samples)
    assert est is not None
    value, n = est
    assert n == 2
    assert abs(value - 100.0) < 0.1  # dominated by the co-located sensor


def test_idw_weighted_between_two_sensors():
    samples = [
        SensorSample(28.60, 77.20, 100.0),
        SensorSample(28.60, 77.30, 0.0),
    ]
    # Midpoint: equal distance -> equal weights -> mean
    est = idw_estimate(28.60, 77.25, samples)
    assert est is not None
    assert abs(est[0] - 50.0) < 1.0


def test_idw_respects_search_radius():
    samples = [SensorSample(28.60, 77.20, 100.0)]
    # ~55km away with a 15km radius -> no estimate
    assert idw_estimate(28.10, 77.20, samples) is None


def test_leave_one_out_rmse_perfect_field():
    # A constant field interpolates exactly -> RMSE 0
    samples = [
        SensorSample(28.60, 77.20, 42.0),
        SensorSample(28.62, 77.22, 42.0),
        SensorSample(28.64, 77.24, 42.0),
    ]
    result = leave_one_out_rmse(samples)
    assert result is not None
    rmse, n = result
    assert n == 3
    assert math.isclose(rmse, 0.0, abs_tol=1e-9)
