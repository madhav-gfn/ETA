"""
Step 5 training entrypoint:

    python -m app.models.train [city_slug] [epochs]

Trains the ConvLSTM on Step 4 cubes with a chronological train/val/test
split, evaluates RMSE against the persistence baseline on held-out data
(the PS brief's literal evaluation focus), and writes:
  - checkpoints/convlstm_{city}.pt   (weights + normalization stats)
  - checkpoints/metrics_{city}.json  (RMSE vs persistence per horizon)
"""

import json
import logging
import sys
from pathlib import Path

import numpy as np
import torch
from torch import nn

from app.core.db import SessionLocal
from app.models.convlstm import ConvLSTMForecaster
from app.models.dataset import chronological_split, load_series, make_windows

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

CKPT_DIR = Path(__file__).resolve().parents[2] / "checkpoints"
WINDOW = 12


def masked_rmse(pred: np.ndarray, target: np.ndarray) -> float:
    mask = ~np.isnan(target)
    if mask.sum() == 0:
        return float("nan")
    return float(np.sqrt(np.mean((pred[mask] - target[mask]) ** 2)))


def train(city_slug: str = "delhi-ncr", epochs: int = 30, window: int = WINDOW) -> dict:
    db = SessionLocal()
    try:
        series = load_series(db, city_slug)
    finally:
        db.close()
    if series is None:
        raise SystemExit("No cubes in manifest — run POST /features/build first")

    X, y, y_persist = make_windows(series, window=window, horizon=1)
    if len(X) < 20:
        raise SystemExit(f"Only {len(X)} training windows — need more backfilled history")
    logger.info("windows=%d cube_shape=%s", len(X), X.shape[1:])

    tr, va, te = chronological_split(len(X))
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = ConvLSTMForecaster(in_channels=X.shape[2]).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    loss_fn = nn.MSELoss()

    pm25_mean = float(series.channel_mean[0])
    pm25_std = float(series.channel_std[0])

    def norm_target(arr: np.ndarray) -> np.ndarray:
        return (np.nan_to_num(arr, nan=pm25_mean) - pm25_mean) / pm25_std

    Xt = torch.from_numpy(X)
    yt = torch.from_numpy(norm_target(y).astype(np.float32))
    batch = 8
    best_val = float("inf")
    best_state = None

    for epoch in range(epochs):
        model.train()
        perm = range(tr.start, tr.stop)
        total = 0.0
        for i in range(tr.start, tr.stop, batch):
            xb = Xt[i : min(i + batch, tr.stop)].to(device)
            yb = yt[i : min(i + batch, tr.stop)].to(device)
            opt.zero_grad()
            out = model(xb)
            loss = loss_fn(out, yb)
            loss.backward()
            opt.step()
            total += loss.item() * len(xb)
        train_loss = total / max(len(list(perm)), 1)

        model.eval()
        with torch.no_grad():
            val_out = model(Xt[va].to(device)).cpu().numpy()
        val_pred = val_out * pm25_std + pm25_mean
        val_rmse = masked_rmse(val_pred, y[va])
        logger.info("epoch %d train_mse=%.4f val_rmse=%.2f", epoch, train_loss, val_rmse)
        if val_rmse < best_val:
            best_val = val_rmse
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}

    if best_state is not None:
        model.load_state_dict(best_state)

    # Held-out test evaluation vs persistence.
    model.eval()
    with torch.no_grad():
        test_out = model(Xt[te].to(device)).cpu().numpy()
    test_pred = test_out * pm25_std + pm25_mean
    model_rmse = masked_rmse(test_pred, y[te])
    persist_rmse = masked_rmse(np.nan_to_num(y_persist[te], nan=pm25_mean), y[te])

    CKPT_DIR.mkdir(exist_ok=True)
    torch.save(
        {
            "state_dict": model.state_dict(),
            "in_channels": X.shape[2],
            "window": window,
            "channel_mean": series.channel_mean.tolist(),
            "channel_std": series.channel_std.tolist(),
        },
        CKPT_DIR / f"convlstm_{city_slug}.pt",
    )
    metrics = {
        "city_slug": city_slug,
        "windows": len(X),
        "test_windows": te.stop - te.start,
        "model_rmse_1h": round(model_rmse, 3),
        "persistence_rmse_1h": round(persist_rmse, 3),
        "beats_persistence": bool(model_rmse < persist_rmse),
        "val_rmse_best": round(best_val, 3),
    }
    (CKPT_DIR / f"metrics_{city_slug}.json").write_text(json.dumps(metrics, indent=2))
    logger.info("DONE %s", metrics)
    return metrics


if __name__ == "__main__":
    city = sys.argv[1] if len(sys.argv) > 1 else "delhi-ncr"
    n_epochs = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    train(city, n_epochs)
