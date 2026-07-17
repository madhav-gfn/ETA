"""
1km×1km grid generation (Step 3, research report Section 2.1).

The city bbox is projected from WGS84 into the city's UTM zone (EPSG from
`cities.py`, e.g. 32643 for North India), tiled into exact 1000m×1000m cells,
and each cell polygon is reprojected back to WGS84 for storage/display.
Deterministic and idempotent: cells are keyed by (city_slug, row_idx, col_idx)
and re-runs upsert rather than duplicate.
"""

import logging
import math

from pyproj import Transformer
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.geospatial.models import GridCell
from app.ingestion.cities import CityBounds, get_city

logger = logging.getLogger(__name__)

CELL_SIZE_M = 1000.0


def grid_dimensions(city: CityBounds) -> tuple[int, int, float, float, float, float]:
    """Compute (n_rows, n_cols, min_x, min_y, max_x, max_y) in UTM meters."""
    to_utm = Transformer.from_crs(4326, city.utm_epsg, always_xy=True)
    min_lon, min_lat, max_lon, max_lat = city.bbox
    # Project all 4 corners: the bbox is a trapezoid in UTM, take outer bounds.
    xs, ys = [], []
    for lon, lat in [(min_lon, min_lat), (max_lon, min_lat), (min_lon, max_lat), (max_lon, max_lat)]:
        x, y = to_utm.transform(lon, lat)
        xs.append(x)
        ys.append(y)
    min_x, max_x, min_y, max_y = min(xs), max(xs), min(ys), max(ys)
    n_cols = math.ceil((max_x - min_x) / CELL_SIZE_M)
    n_rows = math.ceil((max_y - min_y) / CELL_SIZE_M)
    return n_rows, n_cols, min_x, min_y, max_x, max_y


def generate_cells(city: CityBounds) -> list[dict]:
    """Pure generation of cell records (no DB) — testable and deterministic."""
    n_rows, n_cols, min_x, min_y, _, _ = grid_dimensions(city)
    to_wgs = Transformer.from_crs(city.utm_epsg, 4326, always_xy=True)

    cells = []
    for row in range(n_rows):
        for col in range(n_cols):
            x0 = min_x + col * CELL_SIZE_M
            y0 = min_y + row * CELL_SIZE_M
            x1, y1 = x0 + CELL_SIZE_M, y0 + CELL_SIZE_M
            corners_utm = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
            corners = [to_wgs.transform(x, y) for x, y in corners_utm]
            c_lon, c_lat = to_wgs.transform((x0 + x1) / 2, (y0 + y1) / 2)
            wkt = "POLYGON((" + ",".join(f"{lon:.6f} {lat:.6f}" for lon, lat in corners) + "))"
            cells.append(
                {
                    "city_slug": city.slug,
                    "row_idx": row,
                    "col_idx": col,
                    "centroid_lat": round(c_lat, 6),
                    "centroid_lon": round(c_lon, 6),
                    "geom": f"SRID=4326;{wkt}",
                }
            )
    return cells


def generate_grid(db: Session, city_slug: str) -> int:
    """Generate (or refresh) the city grid. Returns the cell count."""
    city = get_city(city_slug)
    cells = generate_cells(city)

    for cell in cells:
        stmt = (
            pg_insert(GridCell)
            .values(**cell)
            .on_conflict_do_update(
                index_elements=["city_slug", "row_idx", "col_idx"],
                set_={
                    "centroid_lat": cell["centroid_lat"],
                    "centroid_lon": cell["centroid_lon"],
                    "geom": cell["geom"],
                },
            )
        )
        db.execute(stmt)
    db.commit()

    count = db.execute(
        select(func.count()).select_from(GridCell).where(GridCell.city_slug == city_slug)
    ).scalar_one()
    logger.info("Grid for %s: %d cells", city_slug, count)
    return count


def load_cells(db: Session, city_slug: str) -> list[GridCell]:
    stmt = (
        select(GridCell)
        .where(GridCell.city_slug == city_slug)
        .order_by(GridCell.row_idx, GridCell.col_idx)
    )
    return list(db.execute(stmt).scalars().all())
