"""Build feature cubes over the full backfilled range, then train the
ConvLSTM and report RMSE vs persistence:

    python scripts/build_and_train.py [city_slug] [epochs]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select  # noqa: E402

from app.core.db import SessionLocal, init_db  # noqa: E402
from app.features.cube import build_cubes  # noqa: E402
from app.ingestion.models import CAAQMSReading  # noqa: E402
from app.models.train import train  # noqa: E402

if __name__ == "__main__":
    city = sys.argv[1] if len(sys.argv) > 1 else "delhi-ncr"
    epochs = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    init_db()
    db = SessionLocal()
    try:
        lo, hi = db.execute(
            select(func.min(CAAQMSReading.measured_at), func.max(CAAQMSReading.measured_at))
            .where(CAAQMSReading.city_slug == city)
        ).one()
        print(f"cube range: {lo} .. {hi}", flush=True)
        result = build_cubes(db, city, lo, hi)
        print(f"cubes: {result['built']} built, {result['skipped_empty_hours']} skipped", flush=True)
    finally:
        db.close()

    metrics = train(city, epochs)
    print(f"METRICS {metrics}", flush=True)
