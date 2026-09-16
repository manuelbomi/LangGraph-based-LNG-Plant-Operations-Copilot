"""End-to-end graph flow tests using LangGraph's in-memory checkpointer.

This proves both branches of the conditional routing after `detect_anomaly`
(normal -> log_normal -> END with no LLM calls at all; warning/critical ->
investigate -> draft_work_order -> engineer_review interrupt -> resume ->
finalize -> END), using the same API the FastAPI app uses against Postgres
in `app/db/checkpointer.py`, without needing a real database or LLM. The
equivalent test against a *real* Postgres checkpointer and a *real* OpenAI
key lives in `tests/live/test_live_smoke.py`.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from app.graph.graph import build_graph
from app.graph.schemas import DraftWorkOrder, RootCauseInvestigation
from app.tools.knowledge_kb import KnowledgeChunkResult

_BASE_TS = datetime(2026, 9, 15, 0, 0, 0, tzinfo=timezone.utc)


async def test_normal_reading_skips_straight_to_log_normal_and_end(fake_sensor_db, sample_tag):
    history = [(_BASE_TS + timedelta(hours=i), 905.0) for i in range(168)]
    fake_sensor_db(sample_tag, history=history)

    graph = build_graph(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "test-thread-normal"}}
    graph_input = {
        "tag_id": "C-201-DISCH-PRESS",
        "reading_timestamp": (_BASE_TS + timedelta(hours=168)).isoformat(),
        "reading_value": 906.0,
    }

    events = []
    async for event in graph.astream(graph_input, config=config, stream_mode="updates"):
        events.append(event)

    node_names = [n for e in events for n in e]
    assert "log_normal" in node_names
    assert "investigate" not in node_names
    assert "engineer_review" not in node_names

    final_state = await graph.aget_state(config)
    assert final_state.next == ()  # reached END directly
    assert final_state.values["status"] == "normal_logged"
    assert final_state.values["final_status"] == "normal"


async def test_critical_reading_pauses_at_engineer_review_and_resumes_to_completion(
    fake_sensor_db, sample_tag, fake_chat_model, fake_prompts, no_knowledge_io
):
    history = [(_BASE_TS + timedelta(hours=i), 905.0) for i in range(168)]
    fake_sensor_db(sample_tag, history=history)
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
            ),
            DraftWorkOrder(
                title="Investigate discharge pressure drift on C-201",
                description="Draft description for engineer review.",
                priority="urgent",
            ),
        ]
    )

    graph = build_graph(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "test-thread-critical"}}
    graph_input = {
        "tag_id": "C-201-DISCH-PRESS",
        "reading_timestamp": (_BASE_TS + timedelta(hours=168)).isoformat(),
        "reading_value": 975.59,
    }

    result = None
    async for event in graph.astream(graph_input, config=config, stream_mode="updates"):
        result = event

    assert result is not None
    assert "__interrupt__" in result, "graph should pause at engineer_review"
    interrupt_payload = result["__interrupt__"][0].value
    assert interrupt_payload["anomaly_classification"] == "critical"
    assert interrupt_payload["draft_work_order"]["priority"] == "urgent"

    state_before_resume = await graph.aget_state(config)
    assert state_before_resume.next == ("engineer_review",)

    final_event = None
    async for event in graph.astream(
        Command(resume={"decision": "approve", "feedback": "Looks correct."}),
        config=config,
        stream_mode="updates",
    ):
        final_event = event

    assert "finalize" in final_event
    final_state = await graph.aget_state(config)
    assert final_state.next == ()
    assert final_state.values["status"] == "work_order_approved"
    assert final_state.values["final_status"] == "work_order_approved"


async def test_escalate_decision_sets_escalated_status(fake_sensor_db, sample_tag, fake_chat_model, fake_prompts, no_knowledge_io):
    history = [(_BASE_TS + timedelta(hours=i), 905.0) for i in range(168)]
    fake_sensor_db(sample_tag, history=history)
    no_knowledge_io.default_results = []
    fake_chat_model([DraftWorkOrder(title="t", description="d", priority="urgent")])

    graph = build_graph(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "test-thread-escalate"}}
    graph_input = {
        "tag_id": "C-201-DISCH-PRESS",
        "reading_timestamp": (_BASE_TS + timedelta(hours=168)).isoformat(),
        "reading_value": 975.59,
    }

    async for _ in graph.astream(graph_input, config=config, stream_mode="updates"):
        pass

    async for _ in graph.astream(
        Command(resume={"decision": "escalate", "feedback": "Escalating to on-call engineer."}),
        config=config,
        stream_mode="updates",
    ):
        pass

    final_state = await graph.aget_state(config)
    assert final_state.values["final_status"] == "escalated"
    assert final_state.values["status"] == "escalated"


async def test_dismiss_benign_decision(fake_sensor_db, sample_tag, fake_chat_model, fake_prompts, no_knowledge_io):
    history = [(_BASE_TS + timedelta(hours=i), 14.0) for i in range(168)]
    fake_sensor_db(sample_tag, history=history)
    no_knowledge_io.default_results = []
    fake_chat_model([DraftWorkOrder(title="t", description="d", priority="low")])

    graph = build_graph(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "test-thread-dismiss"}}
    graph_input = {
        "tag_id": "C-201-DISCH-PRESS",
        "reading_timestamp": (_BASE_TS + timedelta(hours=168)).isoformat(),
        "reading_value": 970.0,  # forces warning/critical so it reaches engineer_review
    }

    async for _ in graph.astream(graph_input, config=config, stream_mode="updates"):
        pass

    async for _ in graph.astream(
        Command(resume={"decision": "dismiss_benign", "feedback": "Confirmed benign scheduled event."}),
        config=config,
        stream_mode="updates",
    ):
        pass

    final_state = await graph.aget_state(config)
    assert final_state.values["final_status"] == "dismissed_benign"
    assert final_state.values["status"] == "dismissed_benign"
