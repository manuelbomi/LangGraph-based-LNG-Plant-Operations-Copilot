"""Load `sample-data/sensor_readings.csv` into the `sensor_readings` table.

Run with:
    python -m scripts.seed_readings

Safe to re-run: skips a tag entirely if it already has readings loaded
(bulk time-series data isn't upserted row-by-row for performance reasons --
if you need to reload, truncate `sensor_readings` first).

Requires `scripts/seed_tags.py` to have already run (readings reference
`sensor_tags.tag_id` via a foreign key).
"""
from __future__ import annotations

import csv
import os
from collections import defaultdict
from datetime import datetime

from app.config import get_settings
from app.db.models import SensorReading
from app.db.session import SessionLocal


def seed() -> None:
    settings = get_settings()
    csv_path = os.path.join(settings.sample_data_dir, "sensor_readings.csv")
    if not os.path.exists(csv_path):
        raise SystemExit(f"sensor_readings.csv not found at {csv_path!r}. Did you set SAMPLE_DATA_DIR correctly?")

    rows_by_tag: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ts = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
            rows_by_tag[row["tag_id"]].append((ts, float(row["value"])))

    with SessionLocal() as db:
        for tag_id, rows in rows_by_tag.items():
            existing = db.query(SensorReading).filter(SensorReading.tag_id == tag_id).count()
            if existing > 0:
                print(f"[skip] tag {tag_id!r} already has {existing} readings loaded")
                continue
            db.bulk_save_objects(
                [SensorReading(tag_id=tag_id, timestamp=ts, value=value) for ts, value in rows]
            )
            db.commit()
            print(f"[seeded] {len(rows)} readings for tag {tag_id!r}")


if __name__ == "__main__":
    seed()
