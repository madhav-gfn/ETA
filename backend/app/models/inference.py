"""
Step 5 serving: loads the trained checkpoint (cached, invalidated on retrain
via file mtime) and produces 1..72h PM2.5 grid forecasts by autoregressive
rollout — each predicted frame is written back into the pm25 channel of the
next input window. Meteorology channels for future hours come from Open-Meteo
forecast rows when available; other channels persist from the last observed
frame.

Serving-path guarantees:
  - inputs are normalized with the *checkpoint's* stats, exactly matching
    training — never with stats recomputed from whatever is in the DB now
  - only the last `window` cubes are loaded per request, not the full history
"""

import io
import logging
from dataclasses import dataclass
from datetime import timedelta
from functools import lru_cache
from pathlib import Path

import numpy as np
import torch
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.cache import cache_get_bytes, cache_set_bytes
from app.features.channels import CHANNELS
from app.geospatial.models import GridReading
from app.models.convlstm import ConvLSTMForecaster
from app.models.dataset import NormStats, load_series
from app.ingestion.models import MeteoReading

logger = logging.getLogger(__name__)

CKPT_DIR = Path(__file__).resolve().parents[2] / "checkpoints"
PM25_CH = CHANNELS.index("pm25")
METEO_CH = {  # channel -> MeteoReading attribute
    3: "temperature_c",
    4: "relative_humidity",
    5: "wind_speed_kmh",
}


def _ckpt_path(city_slug: str) -> Path:
    return CKPT_DIR / f"convlstm_{city_slug}.pt"


@lru_cache(maxsize=8)
def _load_model_cached(city_slug: str, mtime_ns: int):
    # mtime_ns keys the cache so a retrained checkpoint is picked up without
    # a process restart; stale entries just age out of the LRU.
    path = _ckpt_path(city_slug)
    try:
        ckpt = torch.load(path, map_location="cpu", weights_only=True)
    except Exception:
        logger.exception("Failed to load checkpoint %s", path)
        return None
    if ckpt.get("residual"):
        # Residual checkpoints predict corrections to persistence — serving
        # them as absolute values would be silently wrong. They exist for
        # horizon evaluation only (see train.py --residual).
        logger.error("Checkpoint %s is a residual model — not servable by rollout", path)
        return None
    model = ConvLSTMForecaster(in_channels=ckpt["in_channels"])
    model.load_state_dict(ckpt["state_dict"])
    model.eval()
    return model, ckpt


def _load_model(city_slug: str):
    path = _ckpt_path(city_slug)
    if not path.exists():
        return None
    return _load_model_cached(city_slug, path.stat().st_mtime_ns)


def model_available(city_slug: str) -> bool:
    return _ckpt_path(city_slug).exists()


def _ckpt_stats(ckpt: dict) -> NormStats:
    mean = np.array(ckpt["channel_mean"], dtype=np.float32)
    std = np.array(ckpt["channel_std"], dtype=np.float32)
    # Older checkpoints predate the persisted median; the mean is the closest
    # available fill value for them.
    median = np.array(ckpt.get("channel_median", ckpt["channel_mean"]), dtype=np.float32)
    return NormStats(mean=mean, std=std, median=median)


def _rollout(db: Session, city_slug: str, horizon_hours: int):
    """Shared autoregressive rollout. Returns (series, preds) where preds is a
    list of (step, timestamp, un-normalized PM2.5 grid) for every hourly step,
    or None when there's no checkpoint or not enough recent cubes."""
    loaded = _load_model(city_slug)
    if loaded is None:
        return None
    model, ckpt = loaded
    window = ckpt["window"]
    stats = _ckpt_stats(ckpt)
    mean, std = stats.mean, stats.std
    # Checkpoints trained with time-of-day channels need those channels
    # advanced every rollout step — otherwise time freezes at the last
    # observed hour. Indices come from the checkpoint's own channel list.
    ckpt_channels = list(ckpt.get("channels", CHANNELS[: ckpt["in_channels"]]))
    hod_chs = (
        (ckpt_channels.index("hod_sin"), ckpt_channels.index("hod_cos"))
        if "hod_sin" in ckpt_channels and "hod_cos" in ckpt_channels
        else None
    )

    series = load_series(db, city_slug, stats=stats, last_n=window)
    if series is None or len(series.timesteps) < window:
        return None
    if series.timesteps[-1] - series.timesteps[0] != timedelta(hours=window - 1):
        logger.warning(
            "Serving window for %s is non-contiguous: %s .. %s over %d frames",
            city_slug, series.timesteps[0], series.timesteps[-1], window,
        )

    frames = series.cubes.copy()  # normalized (T, H, W, C)
    last_ts = series.timesteps[-1]

    # Pre-fetch meteo forecast rows for the horizon.
    future_meteo = {
        m.measured_at: m
        for m in db.execute(
            select(MeteoReading).where(
                MeteoReading.city_slug == city_slug,
                MeteoReading.measured_at > last_ts,
                MeteoReading.measured_at <= last_ts + timedelta(hours=horizon_hours),
            )
        ).scalars().all()
    }

    preds: list[tuple[int, object, np.ndarray]] = []
    with torch.no_grad():
        for step in range(1, horizon_hours + 1):
            x = torch.from_numpy(np.transpose(frames, (0, 3, 1, 2))[None])  # (1,T,C,H,W)
            pred_norm = model(x).numpy()[0]  # (H, W), normalized
            pred = pred_norm * std[PM25_CH] + mean[PM25_CH]
            ts = last_ts + timedelta(hours=step)
            preds.append((step, ts, pred))

            # Next input frame: copy the last one, replace pm25 with the
            # prediction, advance the time-of-day channels, refresh meteo
            # channels from the forecast if we have it.
            nxt = frames[-1].copy()
            nxt[:, :, PM25_CH] = (pred - mean[PM25_CH]) / std[PM25_CH]
            if hod_chs is not None:
                sin_ch, cos_ch = hod_chs
                hod = 2.0 * np.pi * ts.hour / 24.0
                nxt[:, :, sin_ch] = (np.sin(hod) - mean[sin_ch]) / std[sin_ch]
                nxt[:, :, cos_ch] = (np.cos(hod) - mean[cos_ch]) / std[cos_ch]
            m = future_meteo.get(ts)
            if m is not None:
                for ch, attr in METEO_CH.items():
                    val = getattr(m, attr)
                    if val is not None:
                        nxt[:, :, ch] = (val - mean[ch]) / std[ch]
                if m.wind_direction_deg is not None:
                    rad = np.deg2rad(m.wind_direction_deg)
                    nxt[:, :, 6] = (np.sin(rad) - mean[6]) / std[6]
                    nxt[:, :, 7] = (np.cos(rad) - mean[7]) / std[7]
            frames = np.concatenate([frames[1:], nxt[None]], axis=0)

    return series, preds


@dataclass
class RolloutPayload:
    """Everything `forecast_grid` and `forecast_cell` need, in cache-friendly
    (numpy/plain-Python) form — decoupled from the `CubeSeries`/torch objects
    `_rollout` returns so a cache hit never touches the model or the DB series."""

    generated_from: str
    grid_shape: tuple[int, int]
    valid_mask: np.ndarray  # (H, W) bool
    last_observed_pm25: np.ndarray  # (H, W) float32, NaN where unobserved
    steps: list[int]
    timesteps: list[str]
    preds: np.ndarray  # (T, H, W) float32, aligned with steps/timesteps


def _freshness_token(db: Session, city_slug: str):
    """Latest materialized pm25 hour for this city — the same signal
    `advisory.py` already uses to know the gridded state has moved on. One
    cheap indexed aggregate query, guarding a rollout that costs far more."""
    return db.execute(
        select(func.max(GridReading.measured_at)).where(
            GridReading.city_slug == city_slug, GridReading.parameter == "pm25"
        )
    ).scalar_one_or_none()


def _rollout_cache_key(city_slug: str, horizon_hours: int, latest_ts, ckpt_mtime_ns: int) -> str:
    ts_key = latest_ts.isoformat() if latest_ts is not None else "none"
    return f"rollout:{city_slug}:{horizon_hours}:{ts_key}:{ckpt_mtime_ns}"


def _serialize_rollout(series, preds: list) -> bytes:
    buf = io.BytesIO()
    np.savez_compressed(
        buf,
        generated_from=np.array(series.timesteps[-1].isoformat()),
        grid_shape=np.array([series.cubes.shape[1], series.cubes.shape[2]], dtype=np.int32),
        valid_mask=series.valid_mask,
        last_observed_pm25=series.raw_pm25[-1],
        steps=np.array([step for step, _, _ in preds], dtype=np.int32),
        timesteps=np.array([ts.isoformat() for _, ts, _ in preds]),
        preds=np.stack([pred for _, _, pred in preds]).astype(np.float32),
    )
    return buf.getvalue()


def _deserialize_rollout(raw: bytes) -> RolloutPayload:
    with np.load(io.BytesIO(raw)) as data:
        return RolloutPayload(
            generated_from=data["generated_from"].item(),
            grid_shape=tuple(int(x) for x in data["grid_shape"]),
            valid_mask=data["valid_mask"],
            last_observed_pm25=data["last_observed_pm25"],
            steps=[int(s) for s in data["steps"]],
            timesteps=[str(t) for t in data["timesteps"]],
            preds=data["preds"],
        )


def _rollout_payload(db: Session, city_slug: str, horizon_hours: int) -> RolloutPayload | None:
    """Cached wrapper around `_rollout`. The rollout only changes when a new
    hour materializes or the model is retrained, so `forecast_grid` and every
    `forecast_cell` drill-down share one cached computation per (city,
    horizon, latest hour, checkpoint) — `forecast_cell` in particular no
    longer triggers a full-grid rollout per cell."""
    ckpt_path = _ckpt_path(city_slug)
    if not ckpt_path.exists():
        return None
    cache_key = _rollout_cache_key(
        city_slug, horizon_hours, _freshness_token(db, city_slug), ckpt_path.stat().st_mtime_ns
    )

    cached = cache_get_bytes(cache_key)
    if cached is not None:
        try:
            return _deserialize_rollout(cached)
        except Exception:
            logger.warning("Corrupt rollout cache entry at %s — recomputing", cache_key)

    rolled = _rollout(db, city_slug, horizon_hours)
    if rolled is None:
        return None
    series, preds = rolled
    payload_bytes = _serialize_rollout(series, preds)
    cache_set_bytes(cache_key, payload_bytes)
    return _deserialize_rollout(payload_bytes)


def forecast_grid(db: Session, city_slug: str, horizon_hours: int = 24) -> dict | None:
    """Rollout forecast. Returns per-horizon PM2.5 grids plus timestamps, or
    None when there's no checkpoint or not enough recent cubes. `valid_mask`
    marks cells with PM2.5 coverage within the serving window (recent
    coverage, not all-time)."""
    payload = _rollout_payload(db, city_slug, horizon_hours)
    if payload is None:
        return None

    horizons = {
        step: {"timestep": ts, "pm25": pred.round(2).tolist()}
        for step, ts, pred in zip(payload.steps, payload.timesteps, payload.preds)
        if step in (1, 6, 12, 24, 48, 72) or step == horizon_hours
    }
    return {
        "city_slug": city_slug,
        "generated_from": payload.generated_from,
        "horizon_hours": horizon_hours,
        "grid_shape": list(payload.grid_shape),
        "valid_mask": payload.valid_mask.tolist(),
        "horizons": horizons,
    }


def forecast_cell(
    db: Session, city_slug: str, row_idx: int, col_idx: int, horizon_hours: int = 24
) -> dict | None:
    """Hourly forecast series for one grid cell — backs the per-cell trend
    chart. Also returns the last observed value, which doubles as the
    persistence baseline for every horizon."""
    payload = _rollout_payload(db, city_slug, horizon_hours)
    if payload is None:
        return None
    n_rows, n_cols = payload.grid_shape
    if not (0 <= row_idx < n_rows and 0 <= col_idx < n_cols):
        return None

    last_observed = payload.last_observed_pm25[row_idx, col_idx]
    return {
        "generated_from": payload.generated_from,
        "last_observed_pm25": None if np.isnan(last_observed) else round(float(last_observed), 2),
        "forecast": [
            {"timestep": ts, "pm25": round(float(pred[row_idx, col_idx]), 2)}
            for ts, pred in zip(payload.timesteps, payload.preds)
        ],
    }
