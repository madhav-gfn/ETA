"""One-shot historical backfill: 90 days of Open-Meteo meteorology and
CAAQMS sensor history (OpenAQ /sensors/{id}/hours). Run directly:

    python scripts/backfill.py [days]

Independent of the API server so it can run while uvicorn serves traffic.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text
from app.core.db import SessionLocal, init_db  # noqa: E402
from app.ingestion.caaqms_openaq import pull_caaqms_readings  # noqa: E402
from app.ingestion.meteo_openmeteo import backfill_meteo  # noqa: E402


def main() -> None:
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 90
    init_db()

    db = SessionLocal()
    try:
        # Increase statement timeout to 15 minutes for massive backfill queries
        db.execute(text("SET statement_timeout = '15min'"))
        db.commit()
        meteo_rows = asyncio.run(backfill_meteo(db, "delhi-ncr", days=days))
        print(f"meteo backfill: {meteo_rows} rows")

        caaqms_rows = pull_caaqms_readings(db, "delhi-ncr", hours_back=days * 24)
        print(f"caaqms backfill: {caaqms_rows} rows")
    finally:
        db.close()


if __name__ == "__main__":
    main()
