"""Assembles the LangGraph `StateGraph` for the LNG Plant Operations Copilot.

    START -> ingest_reading -> detect_anomaly --[normal]--> log_normal -> END
                                              \\-[warning/critical]-> investigate
                                                 -> draft_work_order -> engineer_review
                                                 -> finalize -> END

Unlike the straight-line pipelines used elsewhere in this tutorial series,
this graph has a genuine conditional branch: `detect_anomaly`'s output
routes to one of two very different continuations via
`add_conditional_edges`. This is a concrete example of a workflow shape a
linear chain/pipeline framework handles awkwardly -- most sensor readings
are perfectly normal and should be logged cheaply with no LLM calls at all,
while the minority that are abnormal need the full investigate/draft/
review pipeline. See the root README's "Why LangGraph" section.
"""
from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from app.graph.nodes import (
    detect_anomaly_node,
    draft_work_order_node,
    engineer_review_node,
    finalize_node,
    ingest_reading_node,
    investigate_node,
    log_normal_node,
    route_after_detect_anomaly,
)
from app.graph.state import PlantOpsState


def build_graph(checkpointer: BaseCheckpointSaver | None = None):
    """Build (and optionally compile-with-checkpointer) the plant-ops graph.

    Pass `checkpointer=None` to get an uncompiled-but-still-runnable graph
    with LangGraph's default in-memory checkpointing (handy for unit tests
    that don't need durability/interrupts across processes). Pass a real
    `AsyncPostgresSaver` in the FastAPI app for durable, resumable runs.
    """
    builder = StateGraph(PlantOpsState)

    builder.add_node("ingest_reading", ingest_reading_node)
    builder.add_node("detect_anomaly", detect_anomaly_node)
    builder.add_node("log_normal", log_normal_node)
    builder.add_node("investigate", investigate_node)
    builder.add_node("draft_work_order", draft_work_order_node)
    builder.add_node("engineer_review", engineer_review_node)
    builder.add_node("finalize", finalize_node)

    builder.add_edge(START, "ingest_reading")
    builder.add_edge("ingest_reading", "detect_anomaly")
    builder.add_conditional_edges(
        "detect_anomaly",
        route_after_detect_anomaly,
        {"log_normal": "log_normal", "investigate": "investigate"},
    )
    builder.add_edge("log_normal", END)
    builder.add_edge("investigate", "draft_work_order")
    builder.add_edge("draft_work_order", "engineer_review")
    builder.add_edge("engineer_review", "finalize")
    builder.add_edge("finalize", END)

    return builder.compile(checkpointer=checkpointer)
