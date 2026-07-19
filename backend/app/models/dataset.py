"""
Cube-sequence dataset for Step 5 training and serving.

Loads cubes from the Step 4 manifest, imputes NaNs (channel median, then 0),
and normalizes per channel. Two leakage guards production training needs:

  - Normalization/imputation stats come from the *training fraction* of the
    series only (``stats_frac``) — val/test hours never inform them. Serving
    passes the stats persisted in the checkpoint (``stats=``) so inputs are
    normalized exactly the way the model was trained.
  - Windows are exposed as (start, target) index pairs rather than
    materialized arrays; ``chronological_split`` accepts a purge ``gap`` so
    train/val/test windows share no underlying hours.

Splits are chronological — shuffling a time series would leak the future
into training.
"""

import warnings
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.features.cube import CHANNELS
from app.features.models import FeatureCubeManifest

PM25_CH = CHANNELS.index("pm25")


@dataclass
class NormStats:
    mean: np.ndarray  # (C,)
    std: np.ndarray  # (C,)
    median: np.ndarray  # (C,) per-channel NaN fill value


@dataclass
class CubeSeries:
    timesteps: list[datetime]
    cubes: np.ndarray  # (N, H, W, C) — NaN-imputed, normalized
    raw_pm25: np.ndarray  # (N, H, W) un-normalized PM2.5 for targets/metrics
    stats: NormStats
    valid_mask: np.ndarray  # (H, W) cells with PM2.5 coverage in the loaded frames


def compute_stats(cubes: np.ndarray) -> NormStats:
    """Per-channel stats from raw (NaN-preserving) cubes. Callers pass only
    the training fraction so held-out hours never inform normalization.
    All-NaN channels (a source that never reported) fall back to 0/1 stats."""
    flat = cubes.reshape(-1, cubes.shape[-1])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        median = np.nan_to_num(np.nanmedian(flat, axis=0), nan=0.0)
        mean = np.nan_to_num(np.nanmean(flat, axis=0), nan=0.0)
        std = np.nan_to_num(np.nanstd(flat, axis=0), nan=1.0)
    std[std < 1e-6] = 1.0
    return NormStats(
        mean=mean.astype(np.float32),
        std=std.astype(np.float32),
        median=median.astype(np.float32),
    )


def load_series(
    db: Session,
    city_slug: str,
    stats: NormStats | None = None,
    stats_frac: float = 1.0,
    last_n: int | None = None,
) -> CubeSeries | None:
    """Load the cube series for a city.

    ``stats``: normalize with these precomputed stats (serving path — pass the
    checkpoint's). When None, stats are computed from the first ``stats_frac``
    of the loaded frames (training path).
    ``last_n``: only load the most recent N cubes — serving needs one input
    window, not the full history.
    """
    q = (
        select(FeatureCubeManifest)
        .where(FeatureCubeManifest.city_slug == city_slug)
        .order_by(FeatureCubeManifest.timestep.desc() if last_n else FeatureCubeManifest.timestep)
    )
    if last_n:
        q = q.limit(last_n)
    rows = db.execute(q).scalars().all()
    if not rows:
        return None
    if last_n:
        rows = list(reversed(rows))

    cubes = np.stack([np.load(r.storage_path) for r in rows]).astype(np.float32)
    return _assemble_series([r.timestep for r in rows], cubes, stats, stats_frac)


def load_series_from_dir(
    cubes_dir: str | Path,
    stats: NormStats | None = None,
    stats_frac: float = 1.0,
    last_n: int | None = None,
) -> CubeSeries | None:
    """Manifest-free loader for offline/remote training (e.g. a GPU box with
    no Postgres): timesteps come from the cube filenames build_cubes writes
    (YYYYMMDDTHH00Z.npy), which sort chronologically."""
    paths = sorted(Path(cubes_dir).glob("*.npy"))
    if last_n:
        paths = paths[-last_n:]
    if not paths:
        return None
    timesteps = [
        datetime.strptime(p.stem, "%Y%m%dT%H%MZ").replace(tzinfo=timezone.utc) for p in paths
    ]
    cubes = np.stack([np.load(p) for p in paths]).astype(np.float32)
    return _assemble_series(timesteps, cubes, stats, stats_frac)


def _assemble_series(
    timesteps: list[datetime], cubes: np.ndarray, stats: NormStats | None, stats_frac: float
) -> CubeSeries:
    raw_pm25 = cubes[:, :, :, PM25_CH].copy()
    valid_mask = ~np.all(np.isnan(raw_pm25), axis=0)

    if stats is None:
        k = max(1, int(round(len(timesteps) * stats_frac)))
        stats = compute_stats(cubes[:k])

    cubes = np.where(np.isnan(cubes), stats.median, cubes)
    cubes = (cubes - stats.mean) / stats.std

    return CubeSeries(
        timesteps=timesteps,
        cubes=cubes.astype(np.float32),
        raw_pm25=raw_pm25.astype(np.float32),
        stats=stats,
        valid_mask=valid_mask,
    )


def window_indices(
    series: CubeSeries, window: int = 12, horizon: int = 1
) -> list[tuple[int, int]]:
    """(start, target_idx) pairs for every contiguous-hour window whose target
    frame has at least one observed PM2.5 cell. Index pairs instead of stacked
    arrays: stride-1 windows overlap 12×, so materializing them all would blow
    memory up by the window length."""
    out: list[tuple[int, int]] = []
    n = len(series.timesteps)
    full_span = timedelta(hours=window + horizon - 1)
    for start in range(n - window - horizon + 1):
        target_idx = start + window + horizon - 1
        if series.timesteps[target_idx] - series.timesteps[start] != full_span:
            continue  # gap in the hourly record — skip non-contiguous windows
        if np.all(np.isnan(series.raw_pm25[target_idx])):
            continue
        out.append((start, target_idx))
    return out


def gather_batch(
    series: CubeSeries, pairs: list[tuple[int, int]], window: int = 12
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Materialize one batch of windows.

    X: (B, T, C, H, W) normalized inputs
    y: (B, H, W) raw-scale PM2.5 targets (NaN where unobserved)
    y_persist: (B, H, W) last observed frame in each window — the persistence
    baseline the model must beat (PS brief's evaluation focus).
    """
    X = np.stack(
        [np.transpose(series.cubes[s : s + window], (0, 3, 1, 2)) for s, _ in pairs]
    )
    y = np.stack([series.raw_pm25[t] for _, t in pairs])
    y_persist = np.stack([series.raw_pm25[s + window - 1] for s, _ in pairs])
    return X, y, y_persist


def chronological_split(
    n: int, train_frac: float = 0.7, val_frac: float = 0.15, gap: int = 0
) -> tuple[slice, slice, slice]:
    """Chronological train/val/test slices over n windows. ``gap`` drops that
    many windows after each boundary — with stride-1 windows, neighbours share
    input hours, so a gap of (window + horizon - 1) keeps the splits disjoint
    in time (purged split)."""
    train_end = int(n * train_frac)
    val_end = int(n * (train_frac + val_frac))
    return (
        slice(0, train_end),
        slice(min(train_end + gap, val_end), val_end),
        slice(min(val_end + gap, n), n),
    )
