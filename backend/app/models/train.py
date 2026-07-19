"""
Step 5 training entrypoint:

    python -m app.models.train [city_slug] [epochs] [horizon] [--cubes-dir DIR]

--cubes-dir trains from a directory of .npy cubes with no database — zip
backend/data/cubes/<city>/ onto any GPU box, train there, and copy the
resulting checkpoints/*.pt (+ metrics json) back into backend/checkpoints/.
Serving picks up the new checkpoint automatically (mtime-keyed cache).

Trains the ConvLSTM on Step 4 cubes with a purged chronological
train/val/test split, evaluates RMSE against the persistence baseline on
held-out data (the PS brief's literal evaluation focus), and writes:
  - checkpoints/convlstm_{city}.pt   (weights + normalization stats)
  - checkpoints/metrics_{city}.json  (RMSE vs persistence per horizon)

Production-training guards:
  - masked MSE loss — unobserved (NaN) target cells are excluded, not filled
    with the mean, so the model isn't dragged toward predicting the average
  - normalization stats from the train fraction only; persisted in the
    checkpoint so serving normalizes identically
  - shuffled batches, gradient clipping, ReduceLROnPlateau, early stopping,
    and full seeding for reproducibility
"""

import argparse
import json
import logging
import random
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch

from app.features.cube import CHANNELS
from app.models.convlstm import ConvLSTMForecaster
from app.models.dataset import (
    PM25_CH,
    CubeSeries,
    chronological_split,
    gather_batch,
    load_series,
    load_series_from_dir,
    window_indices,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

CKPT_DIR = Path(__file__).resolve().parents[2] / "checkpoints"
WINDOW = 12
TRAIN_FRAC = 0.7
VAL_FRAC = 0.15
SEED = 42
BATCH_SIZE = 8
LR = 1e-3
GRAD_CLIP_NORM = 1.0
EARLY_STOP_PATIENCE = 8


def seed_everything(seed: int = SEED) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def masked_rmse(pred: np.ndarray, target: np.ndarray, mask: np.ndarray | None = None) -> float:
    """RMSE over cells where the target (and optional extra mask) is observed."""
    m = ~np.isnan(target) if mask is None else (~np.isnan(target) & mask)
    if m.sum() == 0:
        return float("nan")
    return float(np.sqrt(np.mean((pred[m] - target[m]) ** 2)))


def _masked_mse_loss(out: torch.Tensor, target: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
    """MSE over observed target cells only. `target` has NaNs zero-filled;
    `mask` marks the genuinely observed cells."""
    diff = (out - target)[mask]
    if diff.numel() == 0:
        return out.sum() * 0.0  # keep the graph alive; contributes nothing
    return (diff**2).mean()


def _eval_rmse(
    model: torch.nn.Module,
    series: CubeSeries,
    pairs: list[tuple[int, int]],
    window: int,
    device: str,
    batch: int = 16,
) -> float:
    """Masked RMSE on the raw µg/m³ scale, accumulated batch-wise."""
    mean = float(series.stats.mean[PM25_CH])
    std = float(series.stats.std[PM25_CH])
    sq_sum, count = 0.0, 0
    model.eval()
    with torch.no_grad():
        for i in range(0, len(pairs), batch):
            X, y, _ = gather_batch(series, pairs[i : i + batch], window)
            out = model(torch.from_numpy(X).to(device)).cpu().numpy()
            pred = out * std + mean
            m = ~np.isnan(y)
            sq_sum += float(((pred[m] - y[m]) ** 2).sum())
            count += int(m.sum())
    return float(np.sqrt(sq_sum / count)) if count else float("nan")


def train(
    city_slug: str = "delhi-ncr",
    epochs: int = 30,
    window: int = WINDOW,
    horizon: int = 1,
    cubes_dir: str | None = None,
) -> dict:
    """Train from the Postgres manifest, or — when ``cubes_dir`` is given —
    straight from a directory of .npy cubes (remote/GPU training without a
    database; see docs on portable training)."""
    seed_everything()

    if cubes_dir is not None:
        series = load_series_from_dir(cubes_dir, stats_frac=TRAIN_FRAC)
    else:
        from app.core.db import SessionLocal  # deferred: offline boxes lack a DB driver

        db = SessionLocal()
        try:
            series = load_series(db, city_slug, stats_frac=TRAIN_FRAC)
        finally:
            db.close()
    if series is None:
        raise SystemExit("No cubes found — run POST /features/build first (or check --cubes-dir)")
    if series.cubes.shape[-1] != len(CHANNELS):
        raise SystemExit(
            f"Cube channel count {series.cubes.shape[-1]} != expected {len(CHANNELS)} — rebuild cubes"
        )

    pairs = window_indices(series, window=window, horizon=horizon)
    if len(pairs) < 20:
        raise SystemExit(f"Only {len(pairs)} training windows — need more backfilled history")
    logger.info("windows=%d grid=%s", len(pairs), series.cubes.shape[1:])

    gap = window + horizon - 1  # purge: stride-1 neighbours share hours
    tr, va, te = chronological_split(len(pairs), TRAIN_FRAC, VAL_FRAC, gap=gap)
    train_pairs, val_pairs, test_pairs = pairs[tr], pairs[va], pairs[te]

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = ConvLSTMForecaster(in_channels=len(CHANNELS)).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=LR)
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, factor=0.5, patience=3)

    pm25_mean = float(series.stats.mean[PM25_CH])
    pm25_std = float(series.stats.std[PM25_CH])

    rng = np.random.default_rng(SEED)
    best_val = float("inf")
    best_state = None
    epochs_since_best = 0
    epochs_ran = 0

    for epoch in range(epochs):
        model.train()
        order = rng.permutation(len(train_pairs))
        total_loss, n_batches = 0.0, 0
        for i in range(0, len(order), BATCH_SIZE):
            chunk = [train_pairs[j] for j in order[i : i + BATCH_SIZE]]
            X, y, _ = gather_batch(series, chunk, window)
            xb = torch.from_numpy(X).to(device)
            mask = torch.from_numpy(~np.isnan(y)).to(device)
            yb = torch.from_numpy(
                (np.nan_to_num(y, nan=pm25_mean) - pm25_mean) / pm25_std
            ).to(device)
            opt.zero_grad()
            loss = _masked_mse_loss(model(xb), yb, mask)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), GRAD_CLIP_NORM)
            opt.step()
            total_loss += loss.item()
            n_batches += 1
        train_loss = total_loss / max(n_batches, 1)

        val_rmse = _eval_rmse(model, series, val_pairs, window, device)
        sched.step(val_rmse)
        epochs_ran = epoch + 1
        logger.info(
            "epoch %d train_mse=%.4f val_rmse=%.2f lr=%.2g",
            epoch, train_loss, val_rmse, opt.param_groups[0]["lr"],
        )
        if val_rmse < best_val - 1e-4:
            best_val = val_rmse
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
            epochs_since_best = 0
        else:
            epochs_since_best += 1
            if epochs_since_best >= EARLY_STOP_PATIENCE:
                logger.info("early stop at epoch %d (no val improvement in %d)", epoch, EARLY_STOP_PATIENCE)
                break

    if best_state is not None:
        model.load_state_dict(best_state)

    # Held-out test evaluation vs persistence, on the same joint mask so the
    # comparison is fair (persistence has NaN where the last frame was unobserved).
    model.eval()
    preds, ys, persists = [], [], []
    with torch.no_grad():
        for i in range(0, len(test_pairs), 16):
            X, y, y_persist = gather_batch(series, test_pairs[i : i + 16], window)
            out = model(torch.from_numpy(X).to(device)).cpu().numpy()
            preds.append(out * pm25_std + pm25_mean)
            ys.append(y)
            persists.append(y_persist)
    test_pred = np.concatenate(preds)
    test_y = np.concatenate(ys)
    test_persist = np.concatenate(persists)
    joint_mask = ~np.isnan(test_persist)
    model_rmse = masked_rmse(test_pred, test_y, mask=joint_mask)
    persist_rmse = masked_rmse(test_persist, test_y, mask=joint_mask)

    CKPT_DIR.mkdir(exist_ok=True)
    # The 1h model is the rollout/serving checkpoint; horizon-specific models
    # (e.g. 24h-direct, the PS brief's judged horizon) get suffixed files.
    suffix = "" if horizon == 1 else f"_{horizon}h"
    torch.save(
        {
            "state_dict": model.state_dict(),
            "in_channels": len(CHANNELS),
            "channels": CHANNELS,
            "window": window,
            "horizon": horizon,
            "channel_mean": series.stats.mean.tolist(),
            "channel_std": series.stats.std.tolist(),
            "channel_median": series.stats.median.tolist(),
            "seed": SEED,
            "trained_at": datetime.now(timezone.utc).isoformat(),
        },
        CKPT_DIR / f"convlstm_{city_slug}{suffix}.pt",
    )
    metrics = {
        "city_slug": city_slug,
        "horizon_hours": horizon,
        "windows": len(pairs),
        "train_windows": len(train_pairs),
        "val_windows": len(val_pairs),
        "test_windows": len(test_pairs),
        "epochs_ran": epochs_ran,
        f"model_rmse_{horizon}h": round(model_rmse, 3),
        f"persistence_rmse_{horizon}h": round(persist_rmse, 3),
        "beats_persistence": bool(model_rmse < persist_rmse),
        "val_rmse_best": round(best_val, 3),
        "trained_at": datetime.now(timezone.utc).isoformat(),
    }
    (CKPT_DIR / f"metrics_{city_slug}{suffix}.json").write_text(json.dumps(metrics, indent=2))
    logger.info("DONE %s", metrics)
    return metrics


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train the ConvLSTM PM2.5 forecaster")
    parser.add_argument("city_slug", nargs="?", default="delhi-ncr")
    parser.add_argument("epochs", nargs="?", type=int, default=30)
    parser.add_argument("horizon", nargs="?", type=int, default=1)
    parser.add_argument(
        "--cubes-dir",
        default=None,
        help="train from a directory of .npy cubes instead of the Postgres manifest "
        "(portable remote/GPU training)",
    )
    args = parser.parse_args()
    train(args.city_slug, args.epochs, horizon=args.horizon, cubes_dir=args.cubes_dir)
