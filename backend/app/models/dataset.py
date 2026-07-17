"""
Cube-sequence dataset for Step 5 training.

Loads cubes from the Step 4 manifest, imputes NaNs (channel median, then 0),
normalizes per channel, and yields (window, target) pairs where the target is
the PM2.5 channel `horizon` hours after the window. Splits are chronological
— shuffling a time series would leak the future into training.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.features.cube import CHANNELS
from app.features.models import FeatureCubeManifest

PM25_CH = CHANNELS.index("pm25")


@dataclass
class CubeSeries:
    timesteps: list[datetime]
    cubes: np.ndarray  # (N, H, W, C) — NaN-imputed, normalized
    raw_pm25: np.ndarray  # (N, H, W) un-normalized PM2.5 for targets/metrics
    channel_mean: np.ndarray
    channel_std: np.ndarray
    valid_mask: np.ndarray  # (H, W) cells that ever had PM2.5 coverage


def load_series(db: Session, city_slug: str) -> CubeSeries | None:
    rows = db.execute(
        select(FeatureCubeManifest)
        .where(FeatureCubeManifest.city_slug == city_slug)
        .order_by(FeatureCubeManifest.timestep)
    ).scalars().all()
    if not rows:
        return None

    cubes = np.stack([np.load(r.storage_path) for r in rows])  # (N, H, W, C)
    timesteps = [r.timestep for r in rows]
    raw_pm25 = cubes[:, :, :, PM25_CH].copy()
    valid_mask = ~np.all(np.isnan(raw_pm25), axis=0)

    # Channel-wise NaN imputation with the channel median, then normalize.
    flat = cubes.reshape(-1, cubes.shape[-1])
    channel_median = np.nanmedian(flat, axis=0)
    channel_median = np.nan_to_num(channel_median, nan=0.0)
    for ch in range(cubes.shape[-1]):
        chan = cubes[:, :, :, ch]
        chan[np.isnan(chan)] = channel_median[ch]
    flat = cubes.reshape(-1, cubes.shape[-1])
    channel_mean = flat.mean(axis=0)
    channel_std = flat.std(axis=0)
    channel_std[channel_std < 1e-6] = 1.0
    cubes = (cubes - channel_mean) / channel_std

    return CubeSeries(
        timesteps=timesteps,
        cubes=cubes.astype(np.float32),
        raw_pm25=raw_pm25.astype(np.float32),
        channel_mean=channel_mean.astype(np.float32),
        channel_std=channel_std.astype(np.float32),
        valid_mask=valid_mask,
    )


def make_windows(
    series: CubeSeries, window: int = 12, horizon: int = 1
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Build (X, y, y_persistence) with only contiguous-hour windows.

    X: (S, T, C, H, W)   y: (S, H, W) raw PM2.5   y_persist: (S, H, W)
    The persistence 'forecast' is the last observed PM2.5 frame in the window
    — the baseline the model must beat (PS brief's evaluation focus).
    """
    xs, ys, persists = [], [], []
    n = len(series.timesteps)
    for start in range(n - window - horizon + 1):
        end = start + window  # exclusive
        target_idx = end + horizon - 1
        span = series.timesteps[target_idx] - series.timesteps[start]
        if span != timedelta(hours=window + horizon - 1):
            continue  # gap in the hourly record — skip non-contiguous windows
        target = series.raw_pm25[target_idx]
        if np.all(np.isnan(target)):
            continue
        xs.append(np.transpose(series.cubes[start:end], (0, 3, 1, 2)))  # (T, C, H, W)
        ys.append(target)
        persists.append(series.raw_pm25[end - 1])
    if not xs:
        return np.empty(0), np.empty(0), np.empty(0)
    return np.stack(xs), np.stack(ys), np.stack(persists)


def chronological_split(
    n: int, train_frac: float = 0.7, val_frac: float = 0.15
) -> tuple[slice, slice, slice]:
    train_end = int(n * train_frac)
    val_end = int(n * (train_frac + val_frac))
    return slice(0, train_end), slice(train_end, val_end), slice(val_end, n)
