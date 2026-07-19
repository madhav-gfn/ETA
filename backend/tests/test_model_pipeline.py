"""Unit tests for the production-hardened model/data pipeline: leakage-free
normalization stats, purged chronological splits, gap-aware windowing, masked
training loss, checkpoint-stat serving, and the vectorized agent geospatial
helpers."""

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest
import torch

from app.agents.graph import _bearing_deg_vec, _count_within
from app.features.cube import CHANNELS
from app.geospatial.idw import distance_m
from app.models.dataset import (
    PM25_CH,
    CubeSeries,
    NormStats,
    chronological_split,
    compute_stats,
    gather_batch,
    window_indices,
)
from app.models.inference import _ckpt_stats
from app.models.train import _masked_mse_loss, masked_rmse

C = len(CHANNELS)


def _series(n=30, h=3, w=3, gap_at=None, seed=0) -> CubeSeries:
    rng = np.random.default_rng(seed)
    cubes = rng.normal(50, 10, size=(n, h, w, C)).astype(np.float32)
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    timesteps = []
    t = t0
    for i in range(n):
        if gap_at is not None and i == gap_at:
            t += timedelta(hours=3)  # >1h hole in the hourly record
        timesteps.append(t)
        t += timedelta(hours=1)
    raw = cubes[:, :, :, PM25_CH].copy()
    stats = compute_stats(cubes)
    return CubeSeries(
        timesteps=timesteps,
        cubes=cubes,
        raw_pm25=raw,
        stats=stats,
        valid_mask=~np.all(np.isnan(raw), axis=0),
    )


def test_compute_stats_ignores_nans():
    cubes = np.full((4, 2, 2, C), np.nan, dtype=np.float32)
    cubes[0, :, :, 0] = 10.0
    cubes[1, :, :, 0] = 20.0
    stats = compute_stats(cubes)
    assert stats.mean[0] == pytest.approx(15.0)
    assert stats.median[0] == pytest.approx(15.0)
    # all-NaN channel falls back to inert 0/1 stats instead of NaN
    assert stats.median[1] == 0.0
    assert stats.std[1] == 1.0


def test_split_gap_keeps_sets_disjoint_in_time():
    window, horizon = 12, 1
    gap = window + horizon - 1
    tr, va, te = chronological_split(1000, gap=gap)
    # stride-1 windows i and j share hours iff |i - j| < window + horizon - 1
    assert va.start - (tr.stop - 1) >= gap
    assert te.start - (va.stop - 1) >= gap


def test_window_indices_skip_gaps():
    series = _series(n=30, gap_at=15)
    pairs = window_indices(series, window=6, horizon=1)
    # every returned window must span exactly window+horizon-1 hours
    for start, target in pairs:
        assert series.timesteps[target] - series.timesteps[start] == timedelta(hours=6)
    # windows crossing the synthetic gap were dropped
    assert len(pairs) < 30 - 6


def test_window_indices_skip_all_nan_targets():
    series = _series(n=20)
    series.raw_pm25[10] = np.nan  # nothing observed that hour
    pairs = window_indices(series, window=6, horizon=1)
    assert all(target != 10 for _, target in pairs)


def test_gather_batch_shapes_and_persistence_frame():
    series = _series(n=20, h=4, w=5)
    pairs = window_indices(series, window=6, horizon=2)
    X, y, y_persist = gather_batch(series, pairs[:3], window=6)
    assert X.shape == (3, 6, C, 4, 5)
    assert y.shape == y_persist.shape == (3, 4, 5)
    start, target = pairs[0]
    assert target == start + 6 + 2 - 1
    np.testing.assert_array_equal(y[0], series.raw_pm25[target])
    # persistence = last observed frame inside the window
    np.testing.assert_array_equal(y_persist[0], series.raw_pm25[start + 5])


def test_masked_loss_ignores_unobserved_cells():
    out = torch.tensor([[1.0, 2.0], [3.0, 4.0]])
    target = torch.tensor([[1.5, 0.0], [3.0, 0.0]])  # NaNs pre-filled with 0
    mask = torch.tensor([[True, False], [True, False]])
    loss = _masked_mse_loss(out, target, mask)
    assert loss.item() == pytest.approx(0.125)  # mean of (0.5², 0²) — masked cells excluded
    # an all-masked batch must not produce NaN gradients
    empty = _masked_mse_loss(out.requires_grad_(), target, torch.zeros_like(mask))
    assert empty.item() == 0.0


def test_masked_rmse_joint_mask():
    pred = np.array([[10.0, 20.0]])
    target = np.array([[12.0, np.nan]])
    extra = np.array([[True, True]])
    assert masked_rmse(pred, target, mask=extra) == pytest.approx(2.0)
    assert np.isnan(masked_rmse(pred, np.full_like(target, np.nan)))


def test_ckpt_stats_median_fallback():
    base = {"channel_mean": [1.0] * C, "channel_std": [2.0] * C}
    stats = _ckpt_stats(base)
    np.testing.assert_array_equal(stats.median, stats.mean)  # legacy checkpoint
    with_median = _ckpt_stats({**base, "channel_median": [5.0] * C})
    assert isinstance(with_median, NormStats)
    assert with_median.median[0] == 5.0


def test_count_within_matches_bruteforce():
    rng = np.random.default_rng(1)
    src = rng.uniform([28.4, 76.8], [28.9, 77.4], size=(40, 2))
    pts = rng.uniform([28.4, 76.8], [28.9, 77.4], size=(200, 2))
    counts = _count_within(src[:, 0], src[:, 1], pts[:, 0], pts[:, 1], 5_000, chunk=16)
    brute = [
        sum(1 for p in pts if distance_m(s[0], s[1], p[0], p[1]) <= 5_000) for s in src
    ]
    np.testing.assert_array_equal(counts, brute)


def test_load_series_from_dir_parses_filenames(tmp_path):
    from app.models.dataset import load_series_from_dir

    rng = np.random.default_rng(2)
    for name in ["20260101T0000Z", "20260101T0100Z", "20260101T0200Z"]:
        np.save(tmp_path / f"{name}.npy", rng.normal(40, 5, size=(3, 3, C)).astype(np.float32))
    series = load_series_from_dir(tmp_path)
    assert series is not None
    assert len(series.timesteps) == 3
    assert series.timesteps[0] == datetime(2026, 1, 1, 0, tzinfo=timezone.utc)
    assert series.timesteps[2] - series.timesteps[1] == timedelta(hours=1)
    assert series.cubes.shape == (3, 3, 3, C)
    # last_n trims from the front, keeping the most recent frames
    tail = load_series_from_dir(tmp_path, last_n=2)
    assert tail.timesteps[0].hour == 1
    assert load_series_from_dir(tmp_path / "empty") is None


def test_bearing_vec_cardinal_directions():
    lat, lon = 28.6, 77.2
    lats = np.array([29.6, 28.6, 27.6, 28.6])
    lons = np.array([77.2, 78.2, 77.2, 76.2])
    b = _bearing_deg_vec(lat, lon, lats, lons)
    assert b[0] == pytest.approx(0.0, abs=1.0)  # north
    assert b[1] == pytest.approx(90.0, abs=1.0)  # east
    assert b[2] == pytest.approx(180.0, abs=1.0)  # south
    assert b[3] == pytest.approx(270.0, abs=1.0)  # west
