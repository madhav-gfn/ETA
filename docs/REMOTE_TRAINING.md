# Remote GPU Training (Kaggle / Colab)

Local CPU training runs ~6 min/epoch; a free cloud GPU does the same epoch in
seconds. The training path was built to be portable: `--cubes-dir` trains
straight from a folder of `.npy` cubes with **no database and no pip
installs** (the training modules import only numpy + torch, both preinstalled
on Kaggle and Colab).

**Recommendation: Kaggle.** Free P100/T4 with ~30 GPU-hours/week, sessions up
to 12h, and — the team feature — the cube zip uploads once as a *Kaggle
Dataset* that every teammate attaches to their own notebook. Colab works too
(instructions below) but re-uploads/mounts Drive per person.

---

## 0. One-time prep (local, Docker running)

Cubes must be current and carry the full channel set (13 channels incl. the
`hod_sin`/`hod_cos` time-of-day encoding) before packaging:

```bash
cd backend
../evenv/python.exe -c "
from datetime import datetime, timedelta, timezone
from app.core.db import SessionLocal, init_db
from app.features.cube import build_cubes
from sqlalchemy import select, func
from app.ingestion.models import CAAQMSReading
init_db(); db = SessionLocal()
lo, hi = db.execute(select(func.min(CAAQMSReading.measured_at), func.max(CAAQMSReading.measured_at)).where(CAAQMSReading.city_slug=='delhi-ncr')).one()
print(build_cubes(db, 'delhi-ncr', lo, hi)); db.close()
"
../evenv/python.exe scripts/package_training_data.py delhi-ncr
```

This writes `training_cubes_delhi-ncr.zip` (~300 MB) at the repo root. The
script warns if the cubes are stale (channel count mismatch).

> Why rebuild first: the checkpoint stores normalization stats computed from
> the exact cubes it trained on. Train on the same vintage you'll serve.

## 1. Kaggle setup (recommended)

1. **Upload the zip once**: kaggle.com → *Datasets* → *New Dataset* → add
   `training_cubes_delhi-ncr.zip` (Kaggle auto-unzips). Set visibility
   *Private* and share with teammates' Kaggle accounts.
2. **New Notebook** → *Settings*: Accelerator = **GPU (T4/P100)**, Internet = On.
   Attach the dataset (*Add Input* → your dataset).
3. Notebook cells:

```python
# Cell 1 — get the code (public repo; for private, use a GitHub token)
!git clone https://github.com/<your-org>/<your-repo>.git eta
%cd eta/backend

# Cell 2 — sanity: GPU visible, cubes attached
import torch, glob
print("cuda:", torch.cuda.is_available(), torch.cuda.get_device_name(0))
CUBES = "/kaggle/input/<your-dataset-slug>"   # folder containing the .npy files
print(len(glob.glob(f"{CUBES}/*.npy")), "cubes")

# Cell 3 — 1h serving model (the rollout checkpoint)
!python -m app.models.train delhi-ncr 30 1 --cubes-dir $CUBES

# Cell 4 — 24h experiment matrix: run all, keep the best test RMSE
!python -m app.models.train delhi-ncr 30 24 --cubes-dir $CUBES
!python -m app.models.train delhi-ncr 30 24 --cubes-dir $CUBES --window 24
!python -m app.models.train delhi-ncr 30 24 --cubes-dir $CUBES --window 24 --residual

# Cell 5 — collect artifacts (metrics print at the end of each run too)
!cat checkpoints/metrics_delhi-ncr*.json
```

4. **Download from the notebook's output**: `checkpoints/convlstm_delhi-ncr.pt`,
   `metrics_delhi-ncr.json`, and the best 24h pair
   (`convlstm_delhi-ncr_24h.pt`, `metrics_delhi-ncr_24h.json`).

## 2. Colab alternative

Same commands; get the data in via Drive:

```python
from google.colab import drive; drive.mount("/content/drive")
!unzip -q /content/drive/MyDrive/training_cubes_delhi-ncr.zip -d /content/cubes
!git clone https://github.com/<your-org>/<your-repo>.git eta
%cd eta/backend
!python -m app.models.train delhi-ncr 30 1 --cubes-dir /content/cubes
```

Runtime → Change runtime type → T4 GPU first. Free Colab sessions can die
after ~90 idle minutes — fine for these runs (minutes each on GPU).

## 3. Bring the results home

Copy the downloaded files into `backend/checkpoints/`, overwriting the old
ones. **No restart needed** — the serving cache is keyed on checkpoint file
mtime and hot-reloads on the next request. `/forecast/metrics` immediately
reflects the new numbers.

Rules the pipeline enforces (don't fight them):

- A `--residual` checkpoint saved as the *base* model (`convlstm_<city>.pt`)
  is **refused by serving** with a log error — residual models are for
  horizon evaluation only. Keep the base model absolute.
- An old 11-channel checkpoint keeps serving on 13-channel cubes (trailing
  channels are sliced off automatically), so there's no downtime between
  rebuilding cubes and dropping in the retrained model.

## 4. The 24h experiment matrix, and why

The 24h-direct model currently loses to same-hour-yesterday persistence
(34.1 vs 31.7 RMSE) because that baseline gets the diurnal cycle for free.
Three attacks, in expected-payoff order — all included in Cell 4 above:

| Experiment | Change | Rationale |
|---|---|---|
| 13-channel retrain | `hod_sin`/`hod_cos` now in the cube | model finally *sees* time of day |
| `--window 24` | 24h input instead of 12h | a full daily cycle in every input |
| `--residual` | predict the correction to persistence | start from the baseline, learn only the delta |

Judge by `model_rmse_24h` vs `persistence_rmse_24h` in each run's metrics
JSON — the held-out comparison is honest (joint mask, purged chronological
split), so whichever wins, wins for real.
