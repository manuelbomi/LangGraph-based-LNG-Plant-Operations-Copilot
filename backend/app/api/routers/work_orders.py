"""REST + SSE API for anomaly-investigation work orders: the bundled-
sample-anomaly catalog (for a zero-setup demo), starting/streaming/resuming
a reading's graph run, and listing/inspecting work orders.

Concurrency model (intentionally simple for a tutorial app): each active run
gets one `asyncio.Queue` in `request.app.state.run_queues`, fed by a
background `asyncio.Task` that drives `graph.astream(...)`. The SSE
endpoint just relays whatever lands on that queue. Every event is also
persisted to the `work_orders` table as it happens, so a client that
reconnects (or a run that finished while nobody was watching) can still be
inspected via `GET /work-orders/{id}` / replayed via
`GET /work-orders/{id}/stream`.

Every reading processed here -- normal or not -- gets one `WorkOrder` row
(even a `normal` classification, with status `normal_logged` and empty
investigation/draft fields) so a single durable, per-run record and a
single SSE stream mechanism cover both branches of the graph's conditional
routing.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from langgraph.types import Command
from sqlalchemy import select

from app.api.schemas import (
    HumanDecisionRequest,
    RunReadingRequest,
    SampleAnomaly,
    SamplesResponse,
    WorkOrderCreateResponse,
    WorkOrderDetail,
    WorkOrderListResponse,
    WorkOrderSummary,
)
from app.db.models import SensorTag, WorkOrder
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/work-orders", tags=["work-orders"])

# The catalog backing the "or trigger one of the bundled sample anomalies"
# zero-setup demo path -- see sample-data/README.md for exactly what each
# one is and how it was generated. `expected_classification` is purely
# descriptive (a label for the picker); the actual classification always
# comes from the live deterministic anomaly-detection logic.
SAMPLE_CATALOG: list[dict[str, str]] = [
    {
        "id": "c201-discharge-pressure-drift",
        "label": "C-201 discharge pressure -- slow drift toward high alarm",
        "tag_id": "C-201-DISCH-PRESS",
        "timestamp": "2026-09-15T19:00:00+00:00",
        "expected_classification": "critical",
    },
    {
        "id": "e101-temperature-spike",
        "label": "E-101 temperature differential -- sudden spike",
        "tag_id": "E-101-DELTA-T",
        "timestamp": "2026-08-31T02:00:00+00:00",
        "expected_classification": "critical",
    },
    {
        "id": "p401-vibration-stuck",
        "label": "P-401 vibration -- sensor flat/stuck",
        "tag_id": "P-401-VIB",
        "timestamp": "2026-09-05T20:00:00+00:00",
        "expected_classification": "critical",
    },
    {
        "id": "t101-pressure-benign-bump",
        "label": "T-101 tank pressure -- brief benign venting bump",
        "tag_id": "T-101-PRESS",
        "timestamp": "2026-08-25T08:00:00+00:00",
        "expected_classification": "warning",
    },
    {
        "id": "bog-flow-normal",
        "label": "BOG recovery flow -- healthy, normal reading",
        "tag_id": "BOG-FLOW-301",
        "timestamp": "2026-09-02T16:00:00+00:00",
        "expected_classification": "normal",
    },
]
_SAMPLE_BY_ID = {s["id"]: s for s in SAMPLE_CATALOG}


def _to_summary(wo: WorkOrder) -> WorkOrderSummary:
    return WorkOrderSummary(
        id=wo.id,
        tag_id=wo.tag_id,
        equipment_id=wo.equipment_id,
        equipment_name=wo.equipment_name,
        reading_timestamp=wo.reading_timestamp,
        reading_value=wo.reading_value,
        status=wo.status,  # type: ignore[arg-type]
        final_status=wo.final_status,
        anomaly_classification=wo.anomaly_classification,
        created_at=wo.created_at,
        updated_at=wo.updated_at,
    )


def _sse(event_type: str, data: dict[str, Any]) -> str:
    return f"event: {event_type}\ndata: {json.dumps(data, default=str)}\n\n"


async def _run_graph(request: Request, thread_id: str, graph_input: Any) -> None:
    """Background task: drive the graph, persist + broadcast each step."""
    graph = request.app.state.graph
    queue: asyncio.Queue = request.app.state.run_queues[thread_id]
    config = {"configurable": {"thread_id": thread_id}}

    def _set_status(status: str, **extra: Any) -> None:
        with SessionLocal() as db:
            wo = db.get(WorkOrder, thread_id)
            if wo is None:
                return
            wo.status = status
            for k, v in extra.items():
                setattr(wo, k, v)
            db.commit()

    def _record_event(node_output: dict[str, Any]) -> None:
        trace_items = node_output.get("trace", [])
        with SessionLocal() as db:
            wo = db.get(WorkOrder, thread_id)
            if wo is None:
                return
            wo.trace = [*wo.trace, *trace_items]
            merged_snapshot = {**wo.state_snapshot, **{k: v for k, v in node_output.items() if k != "trace"}}
            wo.state_snapshot = merged_snapshot
            if "anomaly_classification" in node_output:
                wo.anomaly_classification = node_output["anomaly_classification"]
            if "anomaly_details" in node_output:
                wo.anomaly_details = node_output["anomaly_details"]
            if "retrieved_context" in node_output:
                wo.retrieved_context = node_output["retrieved_context"]
            if "root_cause_hypothesis" in node_output:
                wo.root_cause_hypothesis = node_output["root_cause_hypothesis"]
            if "recommended_response" in node_output:
                wo.recommended_response = node_output["recommended_response"]
            if "citations" in node_output:
                wo.citations = node_output["citations"]
            if "draft_work_order" in node_output:
                wo.draft_work_order = node_output["draft_work_order"]
            if "human_decision" in node_output:
                wo.human_decision = node_output["human_decision"]
            if "human_feedback" in node_output:
                wo.human_feedback = node_output["human_feedback"]
            db.commit()

    def _update_tag_health(status: str, final_status: str | None) -> None:
        with SessionLocal() as db:
            wo = db.get(WorkOrder, thread_id)
            if wo is None:
                return
            tag = db.get(SensorTag, wo.tag_id)
            if tag is None:
                return
            tag.current_status = wo.anomaly_classification or "unknown"
            tag.last_evaluated_at = wo.reading_timestamp
            tag.last_work_order_id = wo.id if wo.anomaly_classification != "normal" else None
            db.commit()

    try:
        _set_status("running")
        async for event in graph.astream(graph_input, config=config, stream_mode="updates"):
            if "__interrupt__" in event:
                interrupt_obj = event["__interrupt__"][0]
                payload = dict(interrupt_obj.value)
                with SessionLocal() as db:
                    wo = db.get(WorkOrder, thread_id)
                    if wo is not None:
                        wo.status = "awaiting_engineer_review"
                        wo.state_snapshot = {**wo.state_snapshot, "interrupt": payload}
                        db.commit()
                await queue.put(_sse("interrupt", payload))
                continue

            for node_name, node_output in event.items():
                if not isinstance(node_output, dict):
                    continue
                _record_event(node_output)
                await queue.put(
                    _sse(
                        "node",
                        {
                            "node": node_name,
                            "output": {k: v for k, v in node_output.items() if k != "trace"},
                            "trace": node_output.get("trace", []),
                        },
                    )
                )
                if node_name not in ("engineer_review",):
                    _set_status("running")

        # Loop ended without an interrupt -> graph ran to completion (END).
        state = await graph.aget_state(config)
        if not state.next:  # no pending nodes => finished
            values = state.values
            status = values.get("status", "work_order_approved")
            final_status = values.get("final_status")
            with SessionLocal() as db:
                wo = db.get(WorkOrder, thread_id)
                if wo is not None:
                    wo.status = status
                    wo.final_status = final_status
                    merged_snapshot = {**wo.state_snapshot, **values}
                    wo.state_snapshot = merged_snapshot
                    db.commit()
            _update_tag_health(status, final_status)
            await queue.put(_sse("done", {"status": status, "final_status": final_status}))
    except Exception as exc:  # noqa: BLE001
        logger.exception("work order run %s failed", thread_id)
        with SessionLocal() as db:
            wo = db.get(WorkOrder, thread_id)
            if wo is not None:
                wo.status = "error"
                wo.error = str(exc)
                db.commit()
        await queue.put(_sse("error", {"message": str(exc)}))
    finally:
        await queue.put(None)  # sentinel: close the SSE stream


def _start_background_run(request: Request, thread_id: str, graph_input: Any) -> None:
    queue: asyncio.Queue = asyncio.Queue()
    request.app.state.run_queues[thread_id] = queue
    task = asyncio.create_task(_run_graph(request, thread_id, graph_input))
    request.app.state.run_tasks[thread_id] = task


async def _start_run(request: Request, *, tag_id: str, timestamp: str) -> WorkOrderCreateResponse:
    with SessionLocal() as db:
        tag = db.get(SensorTag, tag_id)
        if tag is None:
            raise HTTPException(404, f"sensor tag {tag_id!r} not found")

    try:
        reading_dt = datetime.fromisoformat(timestamp)
        with SessionLocal() as db:
            from app.db.models import SensorReading

            row = (
                db.query(SensorReading)
                .filter(SensorReading.tag_id == tag_id, SensorReading.timestamp == reading_dt)
                .first()
            )
        if row is None:
            raise HTTPException(404, f"no reading found for tag {tag_id!r} at {timestamp!r}")
        reading_value = row.value
    except ValueError as exc:
        raise HTTPException(400, f"invalid timestamp {timestamp!r}") from exc

    run_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        wo = WorkOrder(
            id=run_id,
            tag_id=tag_id,
            equipment_id=tag.equipment_id,
            equipment_name=tag.equipment_name,
            reading_timestamp=reading_dt,
            reading_value=reading_value,
            status="pending",
            final_status=None,
            anomaly_classification="",
            anomaly_details={},
            retrieved_context=[],
            root_cause_hypothesis="",
            recommended_response="",
            citations=[],
            draft_work_order={},
            human_decision=None,
            human_feedback="",
            trace=[],
            state_snapshot={},
            error=None,
            created_at=now,
            updated_at=now,
        )
        db.add(wo)
        db.commit()

    _start_background_run(
        request,
        run_id,
        {"tag_id": tag_id, "reading_timestamp": timestamp, "reading_value": reading_value},
    )
    return WorkOrderCreateResponse(id=run_id, tag_id=tag_id, status="pending")


@router.get("/samples", response_model=SamplesResponse)
async def list_samples() -> SamplesResponse:
    return SamplesResponse(samples=[SampleAnomaly(**s) for s in SAMPLE_CATALOG])


@router.post("/samples/{sample_id}/run", response_model=WorkOrderCreateResponse)
async def run_sample_anomaly(sample_id: str, request: Request) -> WorkOrderCreateResponse:
    entry = _SAMPLE_BY_ID.get(sample_id)
    if entry is None:
        raise HTTPException(404, "unknown sample id")
    return await _start_run(request, tag_id=entry["tag_id"], timestamp=entry["timestamp"])


@router.post("/run", response_model=WorkOrderCreateResponse)
async def run_reading(body: RunReadingRequest, request: Request) -> WorkOrderCreateResponse:
    """Trigger processing of an arbitrary (tag, timestamp) reading already
    present in `sensor_readings` -- the general-purpose "process this
    reading" action a tag detail page can offer, in addition to the curated
    sample catalog above."""
    return await _start_run(request, tag_id=body.tag_id, timestamp=body.timestamp)


@router.post("/{work_order_id}/resume", response_model=WorkOrderCreateResponse)
async def resume_work_order(work_order_id: str, body: HumanDecisionRequest, request: Request) -> WorkOrderCreateResponse:
    with SessionLocal() as db:
        wo = db.get(WorkOrder, work_order_id)
        if wo is None:
            raise HTTPException(404, "work order not found")
        if wo.status != "awaiting_engineer_review":
            raise HTTPException(409, f"work order is not awaiting engineer review (status={wo.status})")
        tag_id = wo.tag_id

    _start_background_run(
        request,
        work_order_id,
        Command(
            resume={
                "decision": body.decision,
                "feedback": body.feedback,
                "corrected_draft_work_order": body.corrected_draft_work_order,
            }
        ),
    )
    return WorkOrderCreateResponse(id=work_order_id, tag_id=tag_id, status="running")


@router.get("/{work_order_id}/stream")
async def stream_work_order(work_order_id: str, request: Request) -> StreamingResponse:
    async def event_source():
        queue: asyncio.Queue | None = request.app.state.run_queues.get(work_order_id)

        if queue is None:
            # No live background task (already finished, or the server was
            # restarted after this run reached a terminal/awaiting state).
            # Replay what's durably stored instead of streaming live.
            with SessionLocal() as db:
                wo = db.get(WorkOrder, work_order_id)
            if wo is None:
                yield _sse("error", {"message": "work order not found"})
                return
            yield _sse(
                "replay",
                {
                    "status": wo.status,
                    "trace": wo.trace,
                    "state_snapshot": wo.state_snapshot,
                    "final_status": wo.final_status,
                },
            )
            if wo.status == "awaiting_engineer_review":
                interrupt_payload = wo.state_snapshot.get("interrupt", {})
                yield _sse("interrupt", interrupt_payload)
            yield _sse("done", {"status": wo.status, "final_status": wo.final_status})
            return

        while True:
            item = await queue.get()
            if item is None:
                break
            yield item

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("", response_model=WorkOrderListResponse)
async def list_work_orders(tag_id: str | None = None, status: str | None = None) -> WorkOrderListResponse:
    with SessionLocal() as db:
        stmt = select(WorkOrder).order_by(WorkOrder.created_at.desc())
        if tag_id:
            stmt = stmt.where(WorkOrder.tag_id == tag_id)
        if status:
            stmt = stmt.where(WorkOrder.status == status)
        rows = db.execute(stmt).scalars().all()
        return WorkOrderListResponse(work_orders=[_to_summary(r) for r in rows])


@router.get("/{work_order_id}", response_model=WorkOrderDetail)
async def get_work_order(work_order_id: str) -> WorkOrderDetail:
    with SessionLocal() as db:
        wo = db.get(WorkOrder, work_order_id)
        if wo is None:
            raise HTTPException(404, "work order not found")
        return WorkOrderDetail(
            **_to_summary(wo).model_dump(),
            anomaly_details=wo.anomaly_details,
            retrieved_context=wo.retrieved_context,
            root_cause_hypothesis=wo.root_cause_hypothesis,
            recommended_response=wo.recommended_response,
            citations=wo.citations,
            draft_work_order=wo.draft_work_order,
            human_decision=wo.human_decision,
            human_feedback=wo.human_feedback,
            trace=wo.trace,
            state_snapshot=wo.state_snapshot,
            error=wo.error,
        )
