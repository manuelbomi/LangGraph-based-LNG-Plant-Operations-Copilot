"""SQLAlchemy models: the `prompts` registry, `sensor_tags` (fictitious
instrument/equipment metadata), `sensor_readings` (the hourly time series
loaded from `sample-data/sensor_readings.csv`), and `work_orders` (every
anomaly-investigation run ever started for a tag -- this doubles as both
the "run history" and the durable, status-tracked work order / incident
log record).

Note: LangGraph's `AsyncPostgresSaver` manages its own checkpoint tables
(`checkpoints`, `checkpoint_writes`, ...) via `checkpointer.setup()` -- those
are NOT modeled here and are intentionally left out of Alembic's autogenerate
scope (see `db/migrations/env.py`).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Prompt(Base):
    """A versioned prompt template.

    Only one version per `name` is `is_active` at a time; `get_prompt(name)`
    (see `app/prompts/registry.py`) resolves to that active version. There
    are exactly two prompts in this app: `investigate_anomaly` and
    `draft_work_order`.
    """

    __tablename__ = "prompts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    template: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (UniqueConstraint("name", "version", name="uq_prompts_name_version"),)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Prompt name={self.name!r} v{self.version} active={self.is_active}>"


class SensorTag(Base):
    """One fictitious monitored instrument (see `sample-data/README.md` --
    entirely synthetic, not a real facility). `current_status` /
    `last_evaluated_at` / `last_work_order_id` are a small denormalized
    "equipment health" projection updated by `finalize_node` /
    `log_normal_node`, so the plant dashboard can list every tag's current
    status without recomputing anomaly detection on every page load."""

    __tablename__ = "sensor_tags"

    tag_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    equipment_id: Mapped[str] = mapped_column(String(64), nullable=False)
    equipment_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")

    normal_min: Mapped[float] = mapped_column(Float, nullable=False)
    normal_max: Mapped[float] = mapped_column(Float, nullable=False)
    critical_min: Mapped[float] = mapped_column(Float, nullable=False)
    critical_max: Mapped[float] = mapped_column(Float, nullable=False)
    warning_z: Mapped[float] = mapped_column(Float, nullable=False, default=2.5)
    warning_rate_per_hour: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)

    # Denormalized "equipment health" projection for the dashboard.
    current_status: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown")
    # unknown | normal | warning | critical
    last_evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_work_order_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    work_orders: Mapped[list["WorkOrder"]] = relationship(
        back_populates="tag", cascade="all, delete-orphan", order_by="WorkOrder.created_at"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<SensorTag tag_id={self.tag_id!r} status={self.current_status!r}>"


class SensorReading(Base):
    """One hourly sensor reading, loaded from `sample-data/sensor_readings.csv`
    by `scripts/seed_readings.py`. This is the durable time-series store
    `ingest_reading_node` queries for a tag's recent historical window --
    the CSV itself is only the original source file, per the tutorial
    series' "run-history in Postgres" convention."""

    __tablename__ = "sensor_readings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tag_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sensor_tags.tag_id", ondelete="CASCADE"), nullable=False, index=True
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    value: Mapped[float] = mapped_column(Float, nullable=False)

    __table_args__ = (UniqueConstraint("tag_id", "timestamp", name="uq_sensor_readings_tag_timestamp"),)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<SensorReading tag_id={self.tag_id!r} timestamp={self.timestamp} value={self.value}>"


class WorkOrder(Base):
    """One end-to-end anomaly-investigation run, keyed by the LangGraph
    `thread_id`. Every warning/critical reading ever processed for a tag
    gets a row here -- this is both the "run history" for the frontend and
    the durable, status-tracked work order / incident log record
    `finalize_node` writes to.

    Nothing in `root_cause_hypothesis` / `recommended_response` /
    `draft_work_order` is an automated equipment-control action or a final
    decision until a qualified engineer has reviewed it via the
    `engineer_review` interrupt and this row's `final_status` reflects that
    decision. See the root README's "Scope & Safety" section.
    """

    __tablename__ = "work_orders"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    tag_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sensor_tags.tag_id", ondelete="CASCADE"), nullable=False, index=True
    )
    equipment_id: Mapped[str] = mapped_column(String(64), nullable=False)
    equipment_name: Mapped[str] = mapped_column(String(255), nullable=False)
    reading_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reading_value: Mapped[float] = mapped_column(Float, nullable=False)

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    # pending | running | awaiting_engineer_review | work_order_approved |
    # escalated | dismissed_benign | error
    final_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # work_order_approved | escalated | dismissed_benign (set once by finalize_node)

    anomaly_classification: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    # warning | critical (this table only ever holds non-"normal" events --
    # see log_normal_node, which never creates a WorkOrder row)
    anomaly_details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    retrieved_context: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    root_cause_hypothesis: Mapped[str] = mapped_column(Text, nullable=False, default="")
    recommended_response: Mapped[str] = mapped_column(Text, nullable=False, default="")
    citations: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    draft_work_order: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    human_decision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    human_feedback: Mapped[str] = mapped_column(Text, nullable=False, default="")

    trace: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    state_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    tag: Mapped[SensorTag] = relationship(back_populates="work_orders")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<WorkOrder id={self.id} tag_id={self.tag_id!r} status={self.status!r}>"
