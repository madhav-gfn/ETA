"""
Step 4 — multi-modal feature cube assembly (research report Section 2).

For each hourly timestep, stack channels into a (H, W, C) float32 tensor over
the city's 1km grid (H=row_idx range, W=col_idx range from Step 3):

  0 pm25          IDW-interpolated ground PM2.5 (µg/m³); NaN outside radius
  1 pm10          same for PM10
  2 no2           same for NO2 (ground proxy; S5P raster regridding is the
                  documented upgrade path and slots in here without changing
                  the layout)
  3 temperature   city-wide Open-Meteo value broadcast to all cells (°C)
  4 humidity      relative humidity % (broadcast)
  5 wind_speed    km/h (broadcast)
  6 wind_dir_sin  sin/cos encoding of wind direction — circular quantity,
  7 wind_dir_cos  raw degrees would make 359° and 1° maximally distant
  8 fire_frp      sum of FIRMS Fire Radiative Power (MW) landing in the cell
  9 road_density  static: primary/trunk OSM elements per cell
 10 industrial    static: industrial land-use OSM elements per cell

Missing data stays NaN — never silently zero-filled (the acceptance criterion);
consumers decide how to impute. Cubes are saved as .npy with a manifest row
in Postgres pointing at each file.
"""

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.features.models import FeatureCubeManifest
from app.geospatial.grid import load_cells
from app.ingestion.models import CAAQMSReading, FireDetection, MeteoReading, OSMLandUseFeature

logger = logging.getLogger(__name__)

CHANNELS = [
    "pm25", "pm10", "no2",
    "temperature", "humidity", "wind_speed", "wind_dir_sin", "wind_dir_cos",
    "fire_frp", "road_density", "industrial",
]
POLLUTANT_CHANNELS = {"pm25": 0, "pm10": 1, "no2": 2}

CUBE_DIR = Path(__file__).resolve().parents[2] / "data" / "cubes"


class GridIndex:
    """Cached cell layout for a city: (H, W) shape + centroid arrays + a
    lat/lon -> (row, col) locator."""

    def __init__(self, db: Session, city_slug: str):
        cells = load_cells(db, city_slug)
        if not cells:
            raise ValueError(f"No grid cells for '{city_slug}' — run /grid/generate first")
        self.city_slug = city_slug
        self.n_rows = max(c.row_idx for c in cells) + 1
        self.n_cols = max(c.col_idx for c in cells) + 1
        self.centroid_lat = np.full((self.n_rows, self.n_cols), np.nan)
        self.centroid_lon = np.full((self.n_rows, self.n_cols), np.nan)
        self.grid_ids = np.zeros((self.n_rows, self.n_cols), dtype=np.int64)
        for c in cells:
            self.centroid_lat[c.row_idx, c.col_idx] = c.centroid_lat
            self.centroid_lon[c.row_idx, c.col_idx] = c.centroid_lon
            self.grid_ids[c.row_idx, c.col_idx] = c.grid_id
        # Approximate uniform spacing for lat/lon -> index lookup.
        self.lat0 = float(np.nanmin(self.centroid_lat))
        self.lon0 = float(np.nanmin(self.centroid_lon))
        self.dlat = float((np.nanmax(self.centroid_lat) - self.lat0) / max(self.n_rows - 1, 1))
        self.dlon = float((np.nanmax(self.centroid_lon) - self.lon0) / max(self.n_cols - 1, 1))

    @property
    def shape(self) -> tuple[int, int]:
        return self.n_rows, self.n_cols

    def locate(self, lat: float, lon: float) -> tuple[int, int] | None:
        """Nearest cell (row, col) for a point, or None if outside the grid."""
        if self.dlat == 0 or self.dlon == 0:
            return None
        row = round((lat - self.lat0) / self.dlat)
        col = round((lon - self.lon0) / self.dlon)
        if 0 <= row < self.n_rows and 0 <= col < self.n_cols:
            return row, col
        return None


def _static_osm_channels(db: Session, index: GridIndex) -> tuple[np.ndarray, np.ndarray]:
    """Rasterize OSM element points into per-cell counts: roads, industrial."""
    roads = np.zeros(index.shape, dtype=np.float32)
    industrial = np.zeros(index.shape, dtype=np.float32)
    rows = db.execute(
        select(OSMLandUseFeature).where(OSMLandUseFeature.city_slug == index.city_slug)
    ).scalars().all()
    for f in rows:
        loc = index.locate(f.latitude, f.longitude)
        if loc is None:
            continue
        if f.tag_key == "highway":
            roads[loc] += 1.0
        elif f.tag_key == "landuse" and f.tag_value == "industrial":
            industrial[loc] += 1.0
    return roads, industrial


def _pollutant_grid(
    db: Session, index: GridIndex, parameter: str, hour_start: datetime, hour_end: datetime
) -> np.ndarray:
    """IDW surface for one pollutant from that hour's sensor readings."""
    grid = np.full(index.shape, np.nan, dtype=np.float32)
    rows = db.execute(
        select(CAAQMSReading).where(
            CAAQMSReading.city_slug == index.city_slug,
            CAAQMSReading.parameter == parameter,
            CAAQMSReading.measured_at >= hour_start,
            CAAQMSReading.measured_at < hour_end,
        )
    ).scalars().all()
    latest_by_sensor: dict[int, CAAQMSReading] = {}
    for r in sorted(rows, key=lambda r: r.measured_at, reverse=True):
        latest_by_sensor.setdefault(r.sensor_id, r)
    if not latest_by_sensor:
        return grid
    lats = np.array([r.latitude for r in latest_by_sensor.values()])
    lons = np.array([r.longitude for r in latest_by_sensor.values()])
    vals = np.array([r.value for r in latest_by_sensor.values()])
    return _idw_vectorized(index, lats, lons, vals)


def _idw_vectorized(
    index: GridIndex, lats: np.ndarray, lons: np.ndarray, vals: np.ndarray,
    power: float = 2.0, radius_m: float = 15_000.0,
) -> np.ndarray:
    """Vectorized IDW: same math as geospatial.idw but over all cells at once
    (needed to build thousands of historical cubes in reasonable time)."""
    earth = 6_371_000.0
    clat = index.centroid_lat[:, :, None]  # (H, W, 1)
    clon = index.centroid_lon[:, :, None]
    mean_lat = np.deg2rad((clat + lats[None, None, :]) / 2)
    dx = np.deg2rad(lons[None, None, :] - clon) * np.cos(mean_lat) * earth
    dy = np.deg2rad(lats[None, None, :] - clat) * earth
    dist = np.hypot(dx, dy)  # (H, W, K)
    in_radius = dist <= radius_m
    dist = np.maximum(dist, 1.0)
    w = np.where(in_radius, 1.0 / dist ** power, 0.0)
    wsum = w.sum(axis=2)
    est = np.divide(
        (w * vals[None, None, :]).sum(axis=2), wsum,
        out=np.full(index.shape, np.nan), where=wsum > 0,
    )
    return est.astype(np.float32)


def _fire_grid(db: Session, index: GridIndex, hour_start: datetime, hour_end: datetime) -> np.ndarray:
    """Sum FRP of fire detections falling inside grid cells for the day of
    this timestep (FIRMS gives acq_date/time; sub-daily matching uses the
    acquisition date only — overpasses are ~2/day)."""
    grid = np.zeros(index.shape, dtype=np.float32)
    day = hour_start.date().isoformat()
    rows = db.execute(
        select(FireDetection).where(
            FireDetection.city_slug == index.city_slug,
            FireDetection.acq_date == day,
        )
    ).scalars().all()
    for f in rows:
        loc = index.locate(f.latitude, f.longitude)
        if loc is not None and f.frp is not None:
            grid[loc] += f.frp
    return grid


def _meteo_for_hour(db: Session, city_slug: str, hour_start: datetime) -> MeteoReading | None:
    return db.execute(
        select(MeteoReading)
        .where(
            MeteoReading.city_slug == city_slug,
            MeteoReading.measured_at == hour_start,
        )
        .limit(1)
    ).scalars().first()


def build_cube(db: Session, index: GridIndex, timestep: datetime) -> np.ndarray | None:
    """Assemble one (H, W, C) cube for the hour starting at `timestep`.
    Returns None if there is no pollutant data at all for the hour (nothing
    worth training on)."""
    hour_start = timestep.replace(minute=0, second=0, microsecond=0)
    hour_end = hour_start + timedelta(hours=1)
    h, w = index.shape
    cube = np.full((h, w, len(CHANNELS)), np.nan, dtype=np.float32)

    any_pollutant = False
    for param, ch in POLLUTANT_CHANNELS.items():
        grid = _pollutant_grid(db, index, param, hour_start, hour_end)
        cube[:, :, ch] = grid
        if not np.all(np.isnan(grid)):
            any_pollutant = True
    if not any_pollutant:
        return None

    meteo = _meteo_for_hour(db, index.city_slug, hour_start)
    if meteo is not None:
        cube[:, :, 3] = meteo.temperature_c if meteo.temperature_c is not None else np.nan
        cube[:, :, 4] = meteo.relative_humidity if meteo.relative_humidity is not None else np.nan
        cube[:, :, 5] = meteo.wind_speed_kmh if meteo.wind_speed_kmh is not None else np.nan
        if meteo.wind_direction_deg is not None:
            rad = np.deg2rad(meteo.wind_direction_deg)
            cube[:, :, 6] = np.sin(rad)
            cube[:, :, 7] = np.cos(rad)

    cube[:, :, 8] = _fire_grid(db, index, hour_start, hour_end)
    return cube


def build_cubes(
    db: Session, city_slug: str, start: datetime, end: datetime
) -> dict:
    """Assemble + persist cubes for every hour in [start, end). Static OSM
    channels are computed once and stamped into every cube."""
    index = GridIndex(db, city_slug)
    roads, industrial = _static_osm_channels(db, index)

    out_dir = CUBE_DIR / city_slug
    out_dir.mkdir(parents=True, exist_ok=True)

    built, skipped = 0, 0
    t = start.replace(minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
    end = end.replace(tzinfo=timezone.utc)
    while t < end:
        cube = build_cube(db, index, t)
        if cube is None:
            skipped += 1
        else:
            cube[:, :, 9] = roads
            cube[:, :, 10] = industrial
            fname = t.strftime("%Y%m%dT%H00Z") + ".npy"
            np.save(out_dir / fname, cube)
            stmt = (
                pg_insert(FeatureCubeManifest)
                .values(
                    city_slug=city_slug,
                    timestep=t,
                    channels=",".join(CHANNELS),
                    storage_path=str(out_dir / fname),
                    n_rows=index.n_rows,
                    n_cols=index.n_cols,
                )
                .on_conflict_do_update(
                    index_elements=["city_slug", "timestep"],
                    set_={"storage_path": str(out_dir / fname), "channels": ",".join(CHANNELS)},
                )
            )
            db.execute(stmt)
            built += 1
        t += timedelta(hours=1)

    db.commit()
    logger.info("Cube build for %s: %d built, %d skipped (no data)", city_slug, built, skipped)
    return {"city_slug": city_slug, "built": built, "skipped_empty_hours": skipped,
            "shape": [index.n_rows, index.n_cols, len(CHANNELS)], "channels": CHANNELS}
