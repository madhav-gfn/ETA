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
 11 hod_sin       hour-of-day sin/cos (UTC) broadcast to all cells — the
 12 hod_cos       diurnal cycle a 24h forecast must see to beat persistence

Missing data stays NaN — never silently zero-filled (the acceptance criterion);
consumers decide how to impute. Cubes are saved as .npy with a manifest row
in Postgres pointing at each file.

Source rows for the whole build range are prefetched in three queries and
bucketed by hour in memory — the per-hour-per-source query pattern was
thousands of round-trips per backfill.
"""

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.features.models import FeatureCubeManifest
from app.geospatial.grid import load_cells
from app.ingestion.models import CAAQMSReading, FireDetection, MeteoReading, OSMLandUseFeature

from app.features.channels import (  # noqa: F401  (re-exported for compat)
    CHANNELS,
    HOD_COS_CH,
    HOD_SIN_CH,
    POLLUTANT_CHANNELS,
)

logger = logging.getLogger(__name__)

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
        select(
            OSMLandUseFeature.tag_key, OSMLandUseFeature.tag_value,
            OSMLandUseFeature.latitude, OSMLandUseFeature.longitude,
        ).where(OSMLandUseFeature.city_slug == index.city_slug)
    ).all()
    for tag_key, tag_value, lat, lon in rows:
        loc = index.locate(lat, lon)
        if loc is None:
            continue
        if tag_key == "highway":
            roads[loc] += 1.0
        elif tag_key == "landuse" and tag_value == "industrial":
            industrial[loc] += 1.0
    return roads, industrial


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


def _as_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


@dataclass
class _RangeData:
    """Source rows for a build range, bucketed by hour/day in memory."""

    # (parameter, hour) -> [(lat, lon, value)]: newest reading per sensor in the hour
    sensors_by_hour: dict[tuple[str, datetime], list[tuple[float, float, float]]]
    # acq_date "YYYY-MM-DD" -> [(lat, lon, frp)]
    fires_by_day: dict[str, list[tuple[float, float, float | None]]]
    # hour -> (temperature_c, relative_humidity, wind_speed_kmh, wind_direction_deg)
    meteo_by_hour: dict[datetime, tuple]


def _prefetch_range(db: Session, city_slug: str, start: datetime, end: datetime) -> _RangeData:
    readings = db.execute(
        select(
            CAAQMSReading.parameter, CAAQMSReading.sensor_id,
            CAAQMSReading.latitude, CAAQMSReading.longitude,
            CAAQMSReading.value, CAAQMSReading.measured_at,
        ).where(
            CAAQMSReading.city_slug == city_slug,
            CAAQMSReading.parameter.in_(POLLUTANT_CHANNELS),
            CAAQMSReading.measured_at >= start,
            CAAQMSReading.measured_at < end,
        ).order_by(CAAQMSReading.measured_at.desc())
    ).all()
    latest: dict[tuple[str, datetime, int], tuple[float, float, float]] = {}
    for param, sensor_id, lat, lon, value, ts in readings:
        hour = _as_utc(ts).replace(minute=0, second=0, microsecond=0)
        latest.setdefault((param, hour, sensor_id), (lat, lon, value))  # desc order → newest wins
    sensors_by_hour: dict[tuple[str, datetime], list] = defaultdict(list)
    for (param, hour, _sid), sample in latest.items():
        sensors_by_hour[(param, hour)].append(sample)

    fires_by_day: dict[str, list] = defaultdict(list)
    fire_rows = db.execute(
        select(
            FireDetection.latitude, FireDetection.longitude,
            FireDetection.frp, FireDetection.acq_date,
        ).where(
            FireDetection.city_slug == city_slug,
            FireDetection.acq_date >= start.date().isoformat(),
            FireDetection.acq_date <= end.date().isoformat(),
        )
    ).all()
    for lat, lon, frp, day in fire_rows:
        fires_by_day[day].append((lat, lon, frp))

    meteo_by_hour: dict[datetime, tuple] = {}
    meteo_rows = db.execute(
        select(
            MeteoReading.measured_at, MeteoReading.temperature_c,
            MeteoReading.relative_humidity, MeteoReading.wind_speed_kmh,
            MeteoReading.wind_direction_deg,
        ).where(
            MeteoReading.city_slug == city_slug,
            MeteoReading.measured_at >= start,
            MeteoReading.measured_at < end,
        )
    ).all()
    for ts, temp, rh, wind, wdir in meteo_rows:
        meteo_by_hour[_as_utc(ts)] = (temp, rh, wind, wdir)

    return _RangeData(dict(sensors_by_hour), dict(fires_by_day), meteo_by_hour)


def _assemble_cube(index: GridIndex, data: _RangeData, hour_start: datetime) -> np.ndarray | None:
    """Assemble one (H, W, C) cube for the hour starting at `hour_start` from
    prefetched range data. Returns None if there is no pollutant data at all
    for the hour (nothing worth training on)."""
    h, w = index.shape
    cube = np.full((h, w, len(CHANNELS)), np.nan, dtype=np.float32)

    any_pollutant = False
    for param, ch in POLLUTANT_CHANNELS.items():
        samples = data.sensors_by_hour.get((param, hour_start))
        if not samples:
            continue
        lats = np.array([s[0] for s in samples])
        lons = np.array([s[1] for s in samples])
        vals = np.array([s[2] for s in samples])
        grid = _idw_vectorized(index, lats, lons, vals)
        cube[:, :, ch] = grid
        if not np.all(np.isnan(grid)):
            any_pollutant = True
    if not any_pollutant:
        return None

    meteo = data.meteo_by_hour.get(hour_start)
    if meteo is not None:
        temp, rh, wind, wdir = meteo
        cube[:, :, 3] = temp if temp is not None else np.nan
        cube[:, :, 4] = rh if rh is not None else np.nan
        cube[:, :, 5] = wind if wind is not None else np.nan
        if wdir is not None:
            rad = np.deg2rad(wdir)
            cube[:, :, 6] = np.sin(rad)
            cube[:, :, 7] = np.cos(rad)

    # FIRMS gives acq_date/acq_time; sub-daily matching uses the acquisition
    # date only — overpasses are ~2/day.
    fire = np.zeros(index.shape, dtype=np.float32)
    for lat, lon, frp in data.fires_by_day.get(hour_start.date().isoformat(), []):
        loc = index.locate(lat, lon)
        if loc is not None and frp is not None:
            fire[loc] += frp
    cube[:, :, 8] = fire

    hod = 2.0 * np.pi * hour_start.hour / 24.0
    cube[:, :, HOD_SIN_CH] = np.sin(hod)
    cube[:, :, HOD_COS_CH] = np.cos(hod)
    return cube


def build_cubes(
    db: Session, city_slug: str, start: datetime, end: datetime
) -> dict:
    """Assemble + persist cubes for every hour in [start, end). Static OSM
    channels are computed once and stamped into every cube. Manifest rows are
    upserted, so rebuilding recent hours (to pick up late-arriving station
    data) is idempotent."""
    index = GridIndex(db, city_slug)
    roads, industrial = _static_osm_channels(db, index)

    out_dir = CUBE_DIR / city_slug
    out_dir.mkdir(parents=True, exist_ok=True)

    t = start.replace(minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
    end = end.replace(tzinfo=timezone.utc)
    data = _prefetch_range(db, city_slug, t, end)

    built, skipped = 0, 0
    while t < end:
        cube = _assemble_cube(index, data, t)
        if cube is None:
            skipped += 1
        else:
            cube[:, :, 9] = roads
            cube[:, :, 10] = industrial
            fname = t.strftime("%Y%m%dT%H00Z") + ".npy"
            np.save(out_dir / fname, cube)
            # Manifest paths are stored relative to CUBE_DIR so a DB dump
            # restores cleanly on a teammate's machine with a different
            # checkout location; the loader resolves both forms.
            rel_path = f"{city_slug}/{fname}"
            stmt = (
                pg_insert(FeatureCubeManifest)
                .values(
                    city_slug=city_slug,
                    timestep=t,
                    channels=",".join(CHANNELS),
                    storage_path=rel_path,
                    n_rows=index.n_rows,
                    n_cols=index.n_cols,
                )
                .on_conflict_do_update(
                    index_elements=["city_slug", "timestep"],
                    set_={"storage_path": rel_path, "channels": ",".join(CHANNELS)},
                )
            )
            db.execute(stmt)
            built += 1
        t += timedelta(hours=1)

    db.commit()
    logger.info("Cube build for %s: %d built, %d skipped (no data)", city_slug, built, skipped)
    return {"city_slug": city_slug, "built": built, "skipped_empty_hours": skipped,
            "shape": [index.n_rows, index.n_cols, len(CHANNELS)], "channels": CHANNELS}
