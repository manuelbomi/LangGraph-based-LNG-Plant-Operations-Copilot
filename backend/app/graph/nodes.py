"""LangGraph node implementations for the LNG Plant Operations Copilot.

Six real (non-stub) nodes plus one lightweight terminal node, wired with
real conditional routing (not a straight line -- see `app/graph/graph.py`):

    ingest_reading -> detect_anomaly -> [conditional]
        normal            -> log_normal -> END
        warning/critical  -> investigate -> draft_work_order
                             -> engineer_review -> finalize -> END

  ingest_reading    - loads the tag's metadata and recent historical
                      reading window from Postgres (no LLM call)
  detect_anomaly    - DETERMINISTIC statistical classification (rolling
                      mean/std z-score, smoothed rate-of-change, fixed
                      threshold breach, stuck-sensor detection) -- see
                      `app/tools/anomaly_detection.py`. No LLM call.
  log_normal        - lightweight terminal node for the "normal" branch;
                      logs the reading and updates the tag's cached
                      dashboard status. No LLM call, no work order created.
  investigate       - semantic search (Milvus Lite) over the maintenance-
                      manual / past-incident knowledge base, then an LLM
                      synthesizes a root-cause HYPOTHESIS + recommended
                      response with citations -- decision support only.
  draft_work_order  - LLM drafts a structured work order (trusted
                      equipment/tag/severity fields from state, plus an
                      LLM-written title/description/priority) ready for
                      engineer review.
  engineer_review   - interrupt() pauses the graph for a qualified
                      engineer to edit/approve/escalate/dismiss-as-benign
                      before anything is logged as an official work order.
                      The mandatory safety gate -- see the root README's
                      "Scope & Safety" section.
  finalize          - records the engineer's decision; nothing here
                      controls any equipment or takes any physical action.

This application is strictly a decision-support / documentation-drafting
copilot for plant operations and maintenance staff. It never autonomously
controls equipment and never makes a final safety-critical decision --
every anomaly classification, root-cause hypothesis, and drafted work order
must be reviewed and approved by a qualified engineer/operator before being
acted on.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from langgraph.types import interrupt

from app.db.models import SensorReading, SensorTag
from app.db.session import SessionLocal
from app.graph.schemas import DraftWorkOrder, RootCauseInvestigation
from app.graph.state import PlantOpsState, TraceEvent
from app.llm import get_chat_model
from app.prompts import render_prompt
from app.tools.anomaly_detection import Reading, classify_reading
from app.tools.knowledge_kb import search_plant_knowledge

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _trace(node: str, summary: str) -> list[TraceEvent]:
    return [{"node": node, "timestamp": _now(), "summary": summary}]


# --------------------------------------------------------------------------
# 1. ingest_reading
# --------------------------------------------------------------------------
async def ingest_reading_node(state: PlantOpsState) -> dict:
    tag_id = state["tag_id"]
    reading_timestamp = state["reading_timestamp"]
    ts = datetime.fromisoformat(reading_timestamp)

    with SessionLocal() as db:
        tag = db.get(SensorTag, tag_id)
        if tag is None:
            raise ValueError(f"unknown sensor tag {tag_id!r}")
        tag_meta = {
            "tag_id": tag.tag_id,
            "name": tag.name,
            "unit": tag.unit,
            "equipment_id": tag.equipment_id,
            "equipment_name": tag.equipment_name,
            "description": tag.description,
            "normal_min": tag.normal_min,
            "normal_max": tag.normal_max,
            "critical_min": tag.critical_min,
            "critical_max": tag.critical_max,
            "warning_z": tag.warning_z,
            "warning_rate_per_hour": tag.warning_rate_per_hour,
        }

        from app.config import get_settings

        window = get_settings().history_window_hours
        rows = (
            db.query(SensorReading)
            .filter(SensorReading.tag_id == tag_id, SensorReading.timestamp < ts)
            .order_by(SensorReading.timestamp.desc())
            .limit(window)
            .all()
        )
        history = [{"timestamp": r.timestamp.isoformat(), "value": r.value} for r in reversed(rows)]

    return {
        "tag_meta": tag_meta,
        "history": history,
        "trace": _trace(
            "ingest_reading",
            f"Loaded {tag_meta['name']} ({tag_id}) reading at {reading_timestamp} "
            f"with {len(history)} prior reading(s) of history.",
        ),
    }


# --------------------------------------------------------------------------
# 2. detect_anomaly (deterministic -- no LLM call)
# --------------------------------------------------------------------------
async def detect_anomaly_node(state: PlantOpsState) -> dict:
    tag_meta = state["tag_meta"]
    history = [Reading(timestamp=h["timestamp"], value=h["value"]) for h in state.get("history", [])]

    result = classify_reading(
        current_value=state["reading_value"],
        history=history,
        normal_min=tag_meta["normal_min"],
        normal_max=tag_meta["normal_max"],
        critical_min=tag_meta["critical_min"],
        critical_max=tag_meta["critical_max"],
        warning_z=tag_meta["warning_z"],
        warning_rate_per_hour=tag_meta["warning_rate_per_hour"],
    )

    return {
        "anomaly_classification": result.classification,
        "anomaly_details": result.to_dict(),
        "trace": _trace(
            "detect_anomaly",
            f"Classified as {result.classification.upper()}: {'; '.join(result.reasons)}",
        ),
    }


def route_after_detect_anomaly(state: PlantOpsState) -> str:
    """Conditional edge: `normal` readings skip straight to a lightweight
    log-and-end path; `warning`/`critical` readings continue to root-cause
    investigation. This is the one genuinely branching decision in this
    graph -- see the root README's "Why LangGraph" section for why that
    matters."""
    return "investigate" if state.get("anomaly_classification") in ("warning", "critical") else "log_normal"


# --------------------------------------------------------------------------
# 3a. log_normal (terminal branch for "normal" -- no LLM call, no work order)
# --------------------------------------------------------------------------
async def log_normal_node(state: PlantOpsState) -> dict:
    return {
        "final_status": "normal",
        "status": "normal_logged",
        "trace": _trace(
            "log_normal",
            f"{state['tag_meta']['name']} reading of {state['reading_value']} {state['tag_meta']['unit']} "
            "is within normal parameters; logged, no investigation needed.",
        ),
    }


# --------------------------------------------------------------------------
# 3b. investigate
# --------------------------------------------------------------------------
def _format_retrieved_context(chunks) -> str:
    lines = []
    for c in chunks:
        label = "Manual" if c.doc_type == "manual" else "Incident"
        lines.append(f"[{label}: {c.title}] {c.text}")
    return "\n\n".join(lines)


async def investigate_node(state: PlantOpsState) -> dict:
    tag_meta = state["tag_meta"]
    anomaly_details = state.get("anomaly_details", {})
    classification = state.get("anomaly_classification", "warning")

    query = (
        f"{tag_meta['equipment_name']} {tag_meta['name']} {classification} "
        f"{anomaly_details.get('threshold_breach', '')} "
        f"{'stuck or flat sensor' if anomaly_details.get('stuck_detected') else ''}"
    ).strip()

    chunks = search_plant_knowledge(query, equipment_id=tag_meta["equipment_id"])
    retrieved_context = [
        {
            "chunk_id": c.chunk_id,
            "doc_type": c.doc_type,
            "title": c.title,
            "equipment_id": c.equipment_id,
            "equipment_name": c.equipment_name,
            "text": c.text,
            "score": c.score,
        }
        for c in chunks
    ]

    if not chunks:
        return {
            "retrieved_context": [],
            "root_cause_hypothesis": (
                "No matching maintenance-manual or past-incident content was found for this "
                "equipment/anomaly combination. An engineer should investigate manually using "
                "standard troubleshooting procedures for this equipment."
            ),
            "recommended_response": "Dispatch an engineer for manual investigation; no automated guidance available.",
            "citations": [],
            "trace": _trace(
                "investigate",
                f"No matching manual/incident content found for {tag_meta['equipment_name']}; "
                "flagged for manual engineer investigation.",
            ),
        }

    context_text = _format_retrieved_context(chunks)
    reasons_text = "; ".join(anomaly_details.get("reasons", []))

    llm = get_chat_model()
    structured_llm = llm.with_structured_output(RootCauseInvestigation)
    try:
        prompt_text = render_prompt(
            "investigate_anomaly",
            equipment_name=tag_meta["equipment_name"],
            tag_name=tag_meta["name"],
            unit=tag_meta["unit"],
            reading_value=state["reading_value"],
            classification=classification,
            anomaly_reasons=reasons_text,
            retrieved_context=context_text,
        )
        result = await structured_llm.ainvoke(prompt_text)
        root_cause_hypothesis = result.root_cause_hypothesis
        recommended_response = result.recommended_response
        citations = result.citations
        trace_summary = f"Investigated via {len(chunks)} retrieved manual/incident excerpt(s); drafted root-cause hypothesis."
    except Exception as exc:  # noqa: BLE001
        logger.exception("investigate_node: LLM synthesis failed")
        root_cause_hypothesis = (
            "Automatic root-cause synthesis failed. Relevant manual/incident excerpts were retrieved "
            "(see below) but must be reviewed manually by an engineer."
        )
        recommended_response = "Review the retrieved manual/incident excerpts manually; automatic synthesis failed."
        citations = [f"{c.doc_type.title()}: {c.title}" for c in chunks]
        trace_summary = f"Retrieved {len(chunks)} excerpt(s) but LLM synthesis failed ({exc.__class__.__name__})."

    return {
        "retrieved_context": retrieved_context,
        "root_cause_hypothesis": root_cause_hypothesis,
        "recommended_response": recommended_response,
        "citations": citations,
        "trace": _trace("investigate", trace_summary),
    }


# --------------------------------------------------------------------------
# 4. draft_work_order
# --------------------------------------------------------------------------
async def draft_work_order_node(state: PlantOpsState) -> dict:
    tag_meta = state["tag_meta"]
    classification = state.get("anomaly_classification", "warning")
    anomaly_details = state.get("anomaly_details", {})
    reasons_text = "; ".join(anomaly_details.get("reasons", []))

    observed_anomaly = (
        f"{tag_meta['name']} reading of {state['reading_value']} {tag_meta['unit']} at "
        f"{state['reading_timestamp']}, classified {classification.upper()}: {reasons_text}"
    )

    llm = get_chat_model()
    structured_llm = llm.with_structured_output(DraftWorkOrder)
    try:
        prompt_text = render_prompt(
            "draft_work_order",
            equipment_name=tag_meta["equipment_name"],
            equipment_id=tag_meta["equipment_id"],
            tag_name=tag_meta["name"],
            observed_anomaly=observed_anomaly,
            classification=classification,
            root_cause_hypothesis=state.get("root_cause_hypothesis", ""),
            recommended_response=state.get("recommended_response", ""),
            citations_json=json.dumps(state.get("citations", [])),
        )
        result = await structured_llm.ainvoke(prompt_text)
        title = result.title
        description = result.description
        priority = result.priority
        trace_summary = "Drafted work order with LLM-written title/description/priority."
    except Exception as exc:  # noqa: BLE001
        logger.exception("draft_work_order_node: drafting failed")
        title = f"Investigate {classification} condition on {tag_meta['equipment_name']}"
        description = (
            f"{observed_anomaly}\n\nRoot-cause hypothesis: {state.get('root_cause_hypothesis', '(none)')}\n\n"
            f"Recommended response: {state.get('recommended_response', '(none)')}\n\n"
            "A detailed draft description could not be generated automatically. This is a draft "
            "recommendation requiring engineer review and approval; it does not authorize any "
            "automatic equipment action."
        )
        priority = "high" if classification == "critical" else "medium"
        trace_summary = f"Drafting failed ({exc.__class__.__name__}); used fallback template text."

    draft_work_order = {
        "tag_id": tag_meta["tag_id"],
        "tag_name": tag_meta["name"],
        "equipment_id": tag_meta["equipment_id"],
        "equipment_name": tag_meta["equipment_name"],
        "observed_anomaly": observed_anomaly,
        "severity": classification,
        "title": title,
        "description": description,
        "recommended_action": state.get("recommended_response", ""),
        "priority": priority,
    }

    return {"draft_work_order": draft_work_order, "trace": _trace("draft_work_order", trace_summary)}


# --------------------------------------------------------------------------
# 5. engineer_review
# --------------------------------------------------------------------------
async def engineer_review_node(state: PlantOpsState) -> dict:
    """Pause the graph and wait for a qualified engineer's decision.

    `interrupt()` raises a `GraphInterrupt` the first time this node runs
    for a given thread; LangGraph's Postgres checkpointer persists state up
    to (but not including) this node's completion, so the process can exit
    entirely and be resumed later via `Command(resume=...)` against the
    same `thread_id` -- see `app/api/routers/work_orders.py::resume_work_order`.

    This is the mandatory safety gate for the whole application: nothing
    produced by `detect_anomaly`/`investigate`/`draft_work_order` is an
    approved work order, a confirmed root cause, or an equipment-control
    action until a qualified engineer explicitly approves, escalates, or
    dismisses it here. Investigating an anomaly can easily span a shift
    handover -- which is exactly why this graph needs a durable,
    Postgres-backed checkpointer rather than in-process state.
    """
    payload = interrupt(
        {
            "tag_meta": state.get("tag_meta", {}),
            "reading_value": state.get("reading_value"),
            "reading_timestamp": state.get("reading_timestamp"),
            "anomaly_classification": state.get("anomaly_classification"),
            "anomaly_details": state.get("anomaly_details", {}),
            "retrieved_context": state.get("retrieved_context", []),
            "root_cause_hypothesis": state.get("root_cause_hypothesis", ""),
            "recommended_response": state.get("recommended_response", ""),
            "citations": state.get("citations", []),
            "draft_work_order": state.get("draft_work_order", {}),
        }
    )
    decision = str(payload.get("decision", "approve")).lower()
    feedback = str(payload.get("feedback", ""))
    corrected_draft_work_order = payload.get("corrected_draft_work_order")
    if decision not in {"approve", "escalate", "dismiss_benign"}:
        decision = "approve"

    update: dict = {
        "human_decision": decision,
        "human_feedback": feedback,
        "trace": _trace("engineer_review", f"Engineer decision={decision} | {feedback[:200]}"),
    }

    if corrected_draft_work_order:
        update["draft_work_order"] = corrected_draft_work_order
        update["corrected_draft_work_order"] = corrected_draft_work_order

    return update


# --------------------------------------------------------------------------
# 6. finalize
# --------------------------------------------------------------------------
async def finalize_node(state: PlantOpsState) -> dict:
    decision = state.get("human_decision", "approve")

    if decision == "escalate":
        final_status, status = "escalated", "escalated"
        summary = (
            "Escalated by engineer for immediate senior/on-call attention. This status change is "
            "documentation only and does not trigger any automatic equipment action."
        )
    elif decision == "dismiss_benign":
        final_status, status = "dismissed_benign", "dismissed_benign"
        summary = "Dismissed by engineer as benign; no work order created."
    else:
        final_status, status = "work_order_approved", "work_order_approved"
        summary = (
            "Work order approved by engineer and logged. This status change is documentation only "
            "and does not dispatch any automatic equipment action -- a human must act on it."
        )

    return {"final_status": final_status, "status": status, "trace": _trace("finalize", summary)}
