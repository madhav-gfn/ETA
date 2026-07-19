"""Package the feature cubes for remote GPU training:

    python scripts/package_training_data.py [city_slug]

Writes training_cubes_<city>.zip at the repo root — upload it as a Kaggle
Dataset (or to Drive for Colab) and train with:

    python -m app.models.train <city> 30 1 --cubes-dir <unzipped dir>

See docs/REMOTE_TRAINING.md for the full walkthrough.
"""

import shutil
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

if __name__ == "__main__":
    city = sys.argv[1] if len(sys.argv) > 1 else "delhi-ncr"
    cube_dir = BACKEND / "data" / "cubes" / city
    cubes = sorted(cube_dir.glob("*.npy"))
    if not cubes:
        raise SystemExit(f"No cubes in {cube_dir} — run POST /features/build first")

    # Sanity: warn when cubes predate the current channel layout.
    import numpy as np

    from app.features.channels import CHANNELS

    sample = np.load(cubes[-1])
    if sample.shape[-1] != len(CHANNELS):
        print(
            f"WARNING: newest cube has {sample.shape[-1]} channels but the code "
            f"defines {len(CHANNELS)} — rebuild cubes before packaging, or the "
            f"remote model will train without the new channels."
        )

    out = shutil.make_archive(str(REPO_ROOT / f"training_cubes_{city}"), "zip", cube_dir)
    size_mb = Path(out).stat().st_size / 1e6
    print(f"wrote {out} ({size_mb:.0f} MB, {len(cubes)} cubes, "
          f"{sample.shape[-1]} channels, span {cubes[0].stem} .. {cubes[-1].stem})")
    print("next: upload as a Kaggle Dataset — see docs/REMOTE_TRAINING.md")
