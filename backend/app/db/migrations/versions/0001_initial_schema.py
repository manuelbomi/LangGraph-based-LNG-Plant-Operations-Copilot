"""Initial schema: prompts registry, sensor_tags (fictitious instrument/
equipment metadata), sensor_readings (hourly time series), work_orders
(per-tag anomaly-investigation history).

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-09-16
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prompts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("template", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_prompts_name", "prompts", ["name"])
    op.create_unique_constraint("uq_prompts_name_version", "prompts", ["name", "version"])

    op.create_table(
        "sensor_tags",
        sa.Column("tag_id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("unit", sa.String(length=32), nullable=False),
        sa.Column("equipment_id", sa.String(length=64), nullable=False),
        sa.Column("equipment_name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("normal_min", sa.Float(), nullable=False),
        sa.Column("normal_max", sa.Float(), nullable=False),
        sa.Column("critical_min", sa.Float(), nullable=False),
        sa.Column("critical_max", sa.Float(), nullable=False),
        sa.Column("warning_z", sa.Float(), nullable=False, server_default="2.5"),
        sa.Column("warning_rate_per_hour", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("current_status", sa.String(length=16), nullable=False, server_default="unknown"),
        sa.Column("last_evaluated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_work_order_id", sa.String(length=36), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "sensor_readings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "tag_id",
            sa.String(length=64),
            sa.ForeignKey("sensor_tags.tag_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
    )
    op.create_index("ix_sensor_readings_tag_id", "sensor_readings", ["tag_id"])
    op.create_index("ix_sensor_readings_timestamp", "sensor_readings", ["timestamp"])
    op.create_unique_constraint(
        "uq_sensor_readings_tag_timestamp", "sensor_readings", ["tag_id", "timestamp"]
    )

    op.create_table(
        "work_orders",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "tag_id",
            sa.String(length=64),
            sa.ForeignKey("sensor_tags.tag_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("equipment_id", sa.String(length=64), nullable=False),
        sa.Column("equipment_name", sa.String(length=255), nullable=False),
        sa.Column("reading_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reading_value", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("final_status", sa.String(length=32), nullable=True),
        sa.Column("anomaly_classification", sa.String(length=16), nullable=False, server_default=""),
        sa.Column(
            "anomaly_details",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "retrieved_context",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("root_cause_hypothesis", sa.Text(), nullable=False, server_default=""),
        sa.Column("recommended_response", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "citations",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "draft_work_order",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("human_decision", sa.String(length=32), nullable=True),
        sa.Column("human_feedback", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "trace",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "state_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_work_orders_tag_id", "work_orders", ["tag_id"])
    op.create_index("ix_work_orders_created_at", "work_orders", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_work_orders_created_at", table_name="work_orders")
    op.drop_index("ix_work_orders_tag_id", table_name="work_orders")
    op.drop_table("work_orders")
    op.drop_constraint("uq_sensor_readings_tag_timestamp", "sensor_readings", type_="unique")
    op.drop_index("ix_sensor_readings_timestamp", table_name="sensor_readings")
    op.drop_index("ix_sensor_readings_tag_id", table_name="sensor_readings")
    op.drop_table("sensor_readings")
    op.drop_table("sensor_tags")
    op.drop_constraint("uq_prompts_name_version", "prompts", type_="unique")
    op.drop_index("ix_prompts_name", table_name="prompts")
    op.drop_table("prompts")
