"""Read-only sensor tag / equipment endpoints backing the plant dashboard:
current status per tag (the small denormalized "equipment health"
projection updated by the graph's `finalize`/`log_normal` nodes) and the
time-series readings that back the sensor detail chart."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.api.schemas import (
    ReadingPoint,
    ReadingsResponse,
    SensorTagDetail,
    SensorTagListResponse,
    SensorTagSummary,
)
from app.db.models import SensorReading, SensorTag
from app.db.session import SessionLocal

router = APIRouter(prefix="/tags", tags=["tags"])


def _to_summary(tag: SensorTag) -> SensorTagSummary:
    return SensorTagSummary(
        tag_id=tag.tag_id,
        name=tag.name,
        unit=tag.unit,
        equipment_id=tag.equipment_id,
        equipment_name=tag.equipment_name,
        normal_min=tag.normal_min,
        normal_max=tag.normal_max,
        critical_min=tag.critical_min,
        critical_max=tag.critical_max,
        current_status=tag.current_status,
        last_evaluated_at=tag.last_evaluated_at,
        last_work_order_id=tag.last_work_order_id,
    )


@router.get("", response_model=SensorTagListResponse)
async def list_tags() -> SensorTagListResponse:
    with SessionLocal() as db:
        rows = db.execute(select(SensorTag).order_by(SensorTag.tag_id)).scalars().all()
        return SensorTagListResponse(tags=[_to_summary(t) for t in rows])


@router.get("/{tag_id}", response_model=SensorTagDetail)
async def get_tag(tag_id: str) -> SensorTagDetail:
    with SessionLocal() as db:
        tag = db.get(SensorTag, tag_id)
        if tag is None:
            raise HTTPException(404, "sensor tag not found")
        summary = _to_summary(tag)
        return SensorTagDetail(**summary.model_dump(), description=tag.description, warning_z=tag.warning_z, warning_rate_per_hour=tag.warning_rate_per_hour)


@router.get("/{tag_id}/readings", response_model=ReadingsResponse)
async def get_tag_readings(
    tag_id: str,
    hours: int = Query(default=336, ge=1, le=2000),
    end: str | None = Query(default=None, description="ISO timestamp to end the window at (default: latest reading)"),
) -> ReadingsResponse:
    """Time-series readings for the sensor detail chart. `end` lets the
    frontend center the chart on a specific anomaly event (e.g. from a work
    order's `reading_timestamp`) rather than always showing the latest
    data."""
    with SessionLocal() as db:
        tag = db.get(SensorTag, tag_id)
        if tag is None:
            raise HTTPException(404, "sensor tag not found")

        if end:
            end_dt = datetime.fromisoformat(end)
        else:
            latest = (
                db.query(SensorReading)
                .filter(SensorReading.tag_id == tag_id)
                .order_by(SensorReading.timestamp.desc())
                .first()
            )
            end_dt = latest.timestamp if latest else datetime.now(timezone.utc)

        start_dt = end_dt - timedelta(hours=hours)
        rows = (
            db.query(SensorReading)
            .filter(
                SensorReading.tag_id == tag_id,
                SensorReading.timestamp >= start_dt,
                SensorReading.timestamp <= end_dt,
            )
            .order_by(SensorReading.timestamp.asc())
            .all()
        )
        return ReadingsResponse(
            tag_id=tag_id, readings=[ReadingPoint(timestamp=r.timestamp, value=r.value) for r in rows]
        )
