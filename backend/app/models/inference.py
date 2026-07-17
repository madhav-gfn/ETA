"""
Step 5 serving: loads the trained checkpoint once (module-level cache) and
produces 1..72h PM2.5 grid forecasts by autoregressive rollout — each
predicted frame is written back into the pm25 channel of the next input
window. Meteorology channels for future hours come from Open-Meteo forecast
rows when available; other channels persist from the last observed frame.
"""

import logging
from datetime import timedelta
from functools import lru_cache
from pathlib import Path

import numpy as np
import torch
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.features.cube import CHANNELS
from app.models.convlstm import ConvLSTMForecaster
from app.models.dataset import load_series
from app.ingestion.models import MeteoReading

logger = logging.getLogger(__name__)

CKPT_DIR = Path(__file__).resolve().parents[2] / "checkpoints"
PM25_CH = CHANNELS.index("pm25")
METEO_CH = {  # channel -> MeteoReading attribute
    3: "temperature_c",
    4: "relative_humidity",
    5: "wind_speed_kmh",
}


@lru_cache(maxsize=4)
def _load_model(city_slug: str):
    path = CKPT_DIR / f"convlstm_{city_slug}.pt"
    if not path.exists():
        return None
    ckpt = torch.load(path, map_location="cpu", weights_only=False)
    model = ConvLSTMForecaster(in_channels=ckpt["in_channels"])
    model.load_state_dict(ckpt["state_dict"])
    model.eval()
    return model, ckpt


def model_available(city_slug: str) -> bool:
    return (CKPT_DIR / f"convlstm_{city_slug}.pt").exists()


def forecast_grid(db: Session, city_slug: str, horizon_hours: int = 24) -> dict | None:
    """Rollout forecast. Returns per-horizon PM2.5 grids plus timestamps, or
    None when there's no checkpoint or not enough recent cubes."""
    loaded = _load_model(city_slug)
    if loaded is None:
        return None
    model, ckpt = loaded
    window = ckpt["window"]
    mean = np.array(ckpt["channel_mean"], dtype=np.float32)
    std = np.array(ckpt["channel_std"], dtype=np.float32)

    series = load_series(db, city_slug)
    if series is None or len(series.timesteps) < window:
        return None

    frames = series.cubes[-window:].copy()  # normalized (T, H, W, C)
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

    horizons = {}
    with torch.no_grad():
        for step in range(1, horizon_hours + 1):
            x = torch.from_numpy(np.transpose(frames, (0, 3, 1, 2))[None])  # (1,T,C,H,W)
            pred_norm = model(x).numpy()[0]  # (H, W), normalized
            pred = pred_norm * std[PM25_CH] + mean[PM25_CH]
            ts = last_ts + timedelta(hours=step)
            if step in (1, 6, 12, 24, 48, 72) or step == horizon_hours:
                horizons[step] = {"timestep": ts.isoformat(), "pm25": pred.round(2).tolist()}

            # Next input frame: copy the last one, replace pm25 with the
            # prediction, refresh meteo channels from the forecast if we have it.
            nxt = frames[-1].copy()
            nxt[:, :, PM25_CH] = (pred - mean[PM25_CH]) / std[PM25_CH]
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

    return {
        "city_slug": city_slug,
        "generated_from": last_ts.isoformat(),
        "horizon_hours": horizon_hours,
        "grid_shape": [series.cubes.shape[1], series.cubes.shape[2]],
        "valid_mask": series.valid_mask.tolist(),
        "horizons": horizons,
    }
