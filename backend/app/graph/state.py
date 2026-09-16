"""Graph state schema.

A `TypedDict` (LangGraph's preferred state shape) rather than a Pydantic
model, so partial node returns (`{"anomaly_classification": "critical"}`)
merge cleanly via LangGraph's default "last write wins per key" reducer.
Only `trace` accumulates (via an `operator.add` reducer) since every other
field is written exactly once per run.

Unlike the straight-line pipelines in earlier tutorials in this series, this
graph has real conditional routing: after `detect_anomaly`, a `normal`
classification routes straight to a lightweight `log_normal` node and skips
investigation/drafting/review entirely, while `warning`/`critical` continues
through the full investigation -> draft -> engineer-review -> finalize path.
See `app/graph/graph.py`.
"""
from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class TraceEvent(TypedDict):
    node: str
    timestamp: str
    summary: str


class PlantOpsState(TypedDict, total=False):
    # --- input ---
    tag_id: str
    reading_timestamp: str  # ISO 8601
    reading_value: float

    # --- ingest_reading ---
    tag_meta: dict[str, Any]  # SensorTag fields
    history: list[dict[str, Any]]  # [{"timestamp": ..., "value": ...}, ...], ascending, excludes current reading

    # --- detect_anomaly ---
    anomaly_classification: str  # "normal" | "warning" | "critical"
    anomaly_details: dict[str, Any]  # rolling_mean, rolling_std, z_score, rate_per_hour, stuck_detected, threshold_breach

    # --- investigate (warning/critical only) ---
    retrieved_context: list[dict[str, Any]]  # dumped KnowledgeChunkResult list
    root_cause_hypothesis: str
    recommended_response: str
    citations: list[str]

    # --- draft_work_order (warning/critical only) ---
    draft_work_order: dict[str, Any]

    # --- engineer_review (human-in-the-loop, the mandatory safety gate) ---
    human_decision: str  # "approve" | "escalate" | "dismiss_benign" | ""
    human_feedback: str
    corrected_draft_work_order: dict[str, Any]

    # --- finalize / log_normal ---
    final_status: str  # "work_order_approved" | "escalated" | "dismissed_benign" | "normal"
    status: str  # mirrors app.db.models.WorkOrder.status (or "normal_logged")

    # --- observability (appended to, not replaced) ---
    trace: Annotated[list[TraceEvent], operator.add]
