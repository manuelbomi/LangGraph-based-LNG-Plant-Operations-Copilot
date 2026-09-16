"""Load the bundled fictitious sensor tag / equipment records
(`sample-data/equipment/*.json`) into the `sensor_tags` table.

Run with:
    python -m scripts.seed_tags

Safe to re-run: upserts by `tag_id` rather than inserting duplicates.
"""
from __future__ import annotations

import glob
import json
import os

from app.config import get_settings
from app.db.models import SensorTag
from app.db.session import SessionLocal


def seed() -> None:
    settings = get_settings()
    equipment_dir = os.path.join(settings.sample_data_dir, "equipment")
    paths = sorted(glob.glob(os.path.join(equipment_dir, "*.json")))
    if not paths:
        raise SystemExit(
            f"No sensor tag records found in {equipment_dir!r}. Did you set SAMPLE_DATA_DIR correctly?"
        )

    with SessionLocal() as db:
        for path in paths:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)

            tag = db.get(SensorTag, data["tag_id"])
            if tag is None:
                tag = SensorTag(
                    tag_id=data["tag_id"],
                    name=data["name"],
                    unit=data["unit"],
                    equipment_id=data["equipment_id"],
                    equipment_name=data["equipment_name"],
                    description=data.get("description", ""),
                    normal_min=data["normal_min"],
                    normal_max=data["normal_max"],
                    critical_min=data["critical_min"],
                    critical_max=data["critical_max"],
                    warning_z=data.get("warning_z", 2.5),
                    warning_rate_per_hour=data.get("warning_rate_per_hour", 1.0),
                    current_status="unknown",
                )
                db.add(tag)
                print(f"[seeded] sensor tag {data['tag_id']!r} ({data['name']})")
            else:
                tag.name = data["name"]
                tag.unit = data["unit"]
                tag.equipment_id = data["equipment_id"]
                tag.equipment_name = data["equipment_name"]
                tag.description = data.get("description", "")
                tag.normal_min = data["normal_min"]
                tag.normal_max = data["normal_max"]
                tag.critical_min = data["critical_min"]
                tag.critical_max = data["critical_max"]
                tag.warning_z = data.get("warning_z", 2.5)
                tag.warning_rate_per_hour = data.get("warning_rate_per_hour", 1.0)
                print(f"[updated] sensor tag {data['tag_id']!r} ({data['name']})")
        db.commit()


if __name__ == "__main__":
    seed()
