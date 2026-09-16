"""Pydantic request/response schemas for the REST + SSE API.

Keep these in sync with `frontend/src/api/types.ts` -- that file is a
hand-written TypeScript mirror of this one.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

WorkOrderStatus = Literal[
    "pending",
    "running",
    "awaiting_engineer_review",
    "work_order_approved",
    "escalated",
    "dismissed_benign",
    "normal_logged",
    "error",
]

HumanDecision = Literal["approve", "escalate", "dismiss_benign"]


class SensorTagSummary(BaseModel):
    tag_id: str
    name: str
    unit: str
    equipment_id: str
    equipment_name: str
    normal_min: float
    normal_max: float
    critical_min: float
    critical_max: float
    current_status: str
    last_evaluated_at: datetime | None
    last_work_order_id: str | None


class SensorTagDetail(SensorTagSummary):
    description: str
    warning_z: float
    warning_rate_per_hour: float


class SensorTagListResponse(BaseModel):
    tags: list[SensorTagSummary]


class ReadingPoint(BaseModel):
    timestamp: datetime
    value: float


class ReadingsResponse(BaseModel):
    tag_id: str
    readings: list[ReadingPoint]


class SampleAnomaly(BaseModel):
    id: str
    label: str
    tag_id: str
    timestamp: str
    expected_classification: str


class SamplesResponse(BaseModel):
    samples: list[SampleAnomaly]


class RunReadingRequest(BaseModel):
    tag_id: str
    timestamp: str


class WorkOrderCreateResponse(BaseModel):
    id: str
    tag_id: str
    status: WorkOrderStatus


class HumanDecisionRequest(BaseModel):
    decision: HumanDecision
    feedback: str = ""
    corrected_draft_work_order: dict[str, Any] | None = None


class TraceEventOut(BaseModel):
    node: str
    timestamp: datetime
    summary: str


class WorkOrderSummary(BaseModel):
    id: str
    tag_id: str
    equipment_id: str
    equipment_name: str
    reading_timestamp: datetime
    reading_value: float
    status: WorkOrderStatus
    final_status: str | None
    anomaly_classification: str
    created_at: datetime
    updated_at: datetime


class WorkOrderDetail(WorkOrderSummary):
    anomaly_details: dict[str, Any]
    retrieved_context: list[dict[str, Any]]
    root_cause_hypothesis: str
    recommended_response: str
    citations: list[str]
    draft_work_order: dict[str, Any]
    human_decision: str | None
    human_feedback: str
    trace: list[TraceEventOut]
    state_snapshot: dict[str, Any]
    error: str | None


class WorkOrderListResponse(BaseModel):
    work_orders: list[WorkOrderSummary]
