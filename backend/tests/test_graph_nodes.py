"""Unit tests for individual graph nodes.

Everything here is mocked: LLM calls go through `FakeChatModel` (see
conftest.py), plant-knowledge search I/O is monkeypatched via the
`no_knowledge_io` fixture, and Postgres reads in `ingest_reading_node` go
through the `fake_sensor_db` fixture. No network, no real Postgres, no real
Milvus, no API key spend.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.graph import nodes
from app.graph.schemas import DraftWorkOrder, RootCauseInvestigation
from app.tools.knowledge_kb import KnowledgeChunkResult


# ---------------------------------------------------------------------
# ingest_reading_node
# ---------------------------------------------------------------------
async def test_ingest_reading_node_loads_tag_and_history(fake_sensor_db, sample_tag):
    base = datetime(2026, 9, 15, 0, 0, 0, tzinfo=timezone.utc)
    history = [(base + timedelta(hours=i), 900.0 + i) for i in range(5)]
    fake_sensor_db(sample_tag, history=history)

    result = await nodes.ingest_reading_node(
        {"tag_id": "C-201-DISCH-PRESS", "reading_timestamp": (base + timedelta(hours=5)).isoformat(), "reading_value": 906.0}
    )

    assert result["tag_meta"]["tag_id"] == "C-201-DISCH-PRESS"
    assert result["tag_meta"]["normal_max"] == 930.0
    assert len(result["history"]) == 5
    assert result["history"][0]["value"] == 900.0
    assert len(result["trace"]) == 1


# ---------------------------------------------------------------------
# detect_anomaly_node
# ---------------------------------------------------------------------
async def test_detect_anomaly_node_normal():
    tag_meta = {
        "normal_min": 850.0,
        "normal_max": 930.0,
        "critical_min": 780.0,
        "critical_max": 960.0,
        "warning_z": 2.5,
        "warning_rate_per_hour": 0.35,
    }
    history = [{"timestamp": f"t{i}", "value": 905.0} for i in range(168)]
    result = await nodes.detect_anomaly_node({"tag_meta": tag_meta, "reading_value": 906.0, "history": history})
    assert result["anomaly_classification"] == "normal"
    assert result["trace"][0]["node"] == "detect_anomaly"


async def test_detect_anomaly_node_critical():
    tag_meta = {
        "normal_min": 850.0,
        "normal_max": 930.0,
        "critical_min": 780.0,
        "critical_max": 960.0,
        "warning_z": 2.5,
        "warning_rate_per_hour": 0.35,
    }
    history = [{"timestamp": f"t{i}", "value": 905.0} for i in range(168)]
    result = await nodes.detect_anomaly_node({"tag_meta": tag_meta, "reading_value": 975.59, "history": history})
    assert result["anomaly_classification"] == "critical"
    assert result["anomaly_details"]["threshold_breach"] == "critical_high"


def test_route_after_detect_anomaly():
    assert nodes.route_after_detect_anomaly({"anomaly_classification": "normal"}) == "log_normal"
    assert nodes.route_after_detect_anomaly({"anomaly_classification": "warning"}) == "investigate"
    assert nodes.route_after_detect_anomaly({"anomaly_classification": "critical"}) == "investigate"


# ---------------------------------------------------------------------
# log_normal_node
# ---------------------------------------------------------------------
async def test_log_normal_node():
    result = await nodes.log_normal_node(
        {"tag_meta": {"name": "Compressor C-201 Discharge Pressure", "unit": "psig"}, "reading_value": 906.0}
    )
    assert result["final_status"] == "normal"
    assert result["status"] == "normal_logged"


# ---------------------------------------------------------------------
# investigate_node
# ---------------------------------------------------------------------
async def test_investigate_node_with_retrieved_context(fake_chat_model, fake_prompts, no_knowledge_io):
    no_knowledge_io.default_results = [
        KnowledgeChunkResult(
            chunk_id="c201-manual-1",
            doc_type="manual",
            title="Compressor C-201 Discharge Pressure High: Possible Causes and Response Procedure",
            equipment_id="C-201",
            equipment_name="Process Gas Compressor C-201",
            chunk_index=1,
            text="A gradual upward drift is most commonly associated with progressive fouling.",
            score=0.9,
        )
    ]
    fake_chat_model(
        [
            RootCauseInvestigation(
                root_cause_hypothesis="Likely progressive fouling downstream of the compressor.",
                recommended_response="Inspect the discharge check valve and strainers.",
                citations=["Manual: Compressor C-201 Discharge Pressure High: Possible Causes and Response Procedure"],
            )
        ]
    )

    result = await nodes.investigate_node(
        {
            "tag_meta": {
                "equipment_id": "C-201",
                "equipment_name": "Process Gas Compressor C-201",
                "name": "Compressor C-201 Discharge Pressure",
                "unit": "psig",
            },
            "anomaly_classification": "critical",
            "anomaly_details": {"threshold_breach": "critical_high", "reasons": ["value breaches critical threshold"]},
            "reading_value": 975.59,
        }
    )

    assert len(result["retrieved_context"]) == 1
    assert "fouling" in result["root_cause_hypothesis"].lower()
    assert result["citations"]


async def test_investigate_node_no_matches(no_knowledge_io):
    no_knowledge_io.default_results = []

    result = await nodes.investigate_node(
        {
            "tag_meta": {"equipment_id": "X-999", "equipment_name": "Unknown Equipment", "name": "Unknown Tag"},
            "anomaly_classification": "warning",
            "anomaly_details": {"threshold_breach": "warning_high", "reasons": []},
            "reading_value": 1.0,
        }
    )

    assert result["retrieved_context"] == []
    assert result["citations"] == []
    assert "manual" in result["trace"][0]["summary"].lower() or "manual" in result["root_cause_hypothesis"].lower()


async def test_investigate_node_handles_llm_failure(fake_chat_model, fake_prompts, no_knowledge_io):
    no_knowledge_io.default_results = [
        KnowledgeChunkResult(
            chunk_id="c-1",
            doc_type="manual",
            title="Some Manual",
            equipment_id="C-201",
            equipment_name="Process Gas Compressor C-201",
            chunk_index=0,
            text="text",
            score=0.5,
        )
    ]
    fake_chat_model([RuntimeError("model refused")])

    result = await nodes.investigate_node(
        {
            "tag_meta": {"equipment_id": "C-201", "equipment_name": "Process Gas Compressor C-201", "name": "Tag", "unit": "psig"},
            "anomaly_classification": "critical",
            "anomaly_details": {"threshold_breach": "critical_high", "reasons": []},
            "reading_value": 975.0,
        }
    )

    assert len(result["retrieved_context"]) == 1
    assert "failed" in result["trace"][0]["summary"].lower() or "manually" in result["root_cause_hypothesis"].lower()


# ---------------------------------------------------------------------
# draft_work_order_node
# ---------------------------------------------------------------------
async def test_draft_work_order_node_success(fake_chat_model, fake_prompts):
    fake_chat_model(
        [
            DraftWorkOrder(
                title="Investigate discharge pressure drift on C-201",
                description="Draft description referencing root cause and recommended action.",
                priority="urgent",
            )
        ]
    )

    result = await nodes.draft_work_order_node(
        {
            "tag_meta": {
                "tag_id": "C-201-DISCH-PRESS",
                "name": "Compressor C-201 Discharge Pressure",
                "unit": "psig",
                "equipment_id": "C-201",
                "equipment_name": "Process Gas Compressor C-201",
            },
            "reading_value": 975.59,
            "reading_timestamp": "2026-09-15T19:00:00+00:00",
            "anomaly_classification": "critical",
            "anomaly_details": {"reasons": ["value breaches critical threshold"]},
            "root_cause_hypothesis": "Progressive fouling.",
            "recommended_response": "Inspect valves.",
            "citations": ["Manual: X"],
        }
    )

    draft = result["draft_work_order"]
    assert draft["tag_id"] == "C-201-DISCH-PRESS"
    assert draft["severity"] == "critical"
    assert draft["priority"] == "urgent"
    assert "Draft description" in draft["description"]


async def test_draft_work_order_node_handles_failure(fake_chat_model, fake_prompts):
    fake_chat_model([RuntimeError("model refused")])

    result = await nodes.draft_work_order_node(
        {
            "tag_meta": {
                "tag_id": "C-201-DISCH-PRESS",
                "name": "Compressor C-201 Discharge Pressure",
                "unit": "psig",
                "equipment_id": "C-201",
                "equipment_name": "Process Gas Compressor C-201",
            },
            "reading_value": 975.59,
            "reading_timestamp": "2026-09-15T19:00:00+00:00",
            "anomaly_classification": "critical",
            "anomaly_details": {"reasons": []},
        }
    )

    draft = result["draft_work_order"]
    assert draft["priority"] == "high"
    assert "requires engineer review" in draft["description"].lower() or "draft recommendation" in draft["description"].lower()
    assert "failed" in result["trace"][0]["summary"].lower()


# ---------------------------------------------------------------------
# finalize_node
# ---------------------------------------------------------------------
async def test_finalize_node_approved():
    result = await nodes.finalize_node({"human_decision": "approve"})
    assert result["final_status"] == "work_order_approved"
    assert result["status"] == "work_order_approved"


async def test_finalize_node_escalated():
    result = await nodes.finalize_node({"human_decision": "escalate"})
    assert result["final_status"] == "escalated"
    assert result["status"] == "escalated"


async def test_finalize_node_dismissed_benign():
    result = await nodes.finalize_node({"human_decision": "dismiss_benign"})
    assert result["final_status"] == "dismissed_benign"
    assert result["status"] == "dismissed_benign"
