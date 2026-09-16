"""REAL end-to-end smoke test: actual OpenAI API calls + a real Postgres.

This is deliberately excluded from the default `pytest` run (see the `live`
marker + `addopts` in `pyproject.toml`). Run it explicitly with:

    export OPENAI_API_KEY=sk-...
    export DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/plant_ops
    cd backend
    pytest -m live tests/live/test_live_smoke.py -v -s

What it proves, with no mocks anywhere in the graph/LLM/DB path:
  1. The fictitious `C-201-DISCH-PRESS` slow-drift anomaly reading from
     `sample-data/sensor_readings.csv` is ingested (its historical window
     loaded from Postgres), classified CRITICAL by the deterministic
     anomaly-detection logic, investigated via a real Milvus Lite semantic
     search against the maintenance-manual/incident knowledge base plus a
     real `gpt-4o-mini` call, a draft work order assembled by a second real
     `gpt-4o-mini` call, and the run genuinely pauses at `engineer_review`
     (`interrupt()`).
  2. The checkpointer can be torn down and a BRAND NEW `AsyncPostgresSaver`
     + freshly-compiled graph (standing in for a shift handover / a new
     process) can resume that exact thread and finish the run (`finalize`),
     marking it `work_order_approved`.

Cost note: this makes at most TWO small `gpt-4o-mini` calls (root-cause
investigation, work-order drafting) plus a handful of small
`text-embedding-3-small` calls (knowledge-base collection seeding, ~30
short paragraphs, one-time, plus one query embedding for this request) --
cheap.

Platform note: `investigate`'s knowledge search silently returns no matches
if `milvus_lite` isn't installed/importable (see
`app/tools/knowledge_kb.py`'s broad except clause), which is expected on
native Windows -- in that case `investigate_node` falls back to its
no-matching-content path and skips the root-cause LLM call entirely (only
`draft_work_order` still calls the LLM). This test does NOT hard-assert
`retrieved_context` is non-empty for that reason -- it only asserts on the
deterministic anomaly classification and the drafted work order fields,
which do not depend on Milvus.
"""
from __future__ import annotations

import asyncio
import os
import sys

import pytest

if sys.platform == "win32":
    # psycopg's async mode cannot run on Windows' default ProactorEventLoop;
    # it needs a selector-based loop. This only matters for local dev on
    # Windows -- the backend Docker image (and CI) run on Linux, where this
    # is a no-op. See: https://www.psycopg.org/psycopg3/docs/advanced/async.html
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
from alembic import command
from alembic.config import Config
from langgraph.types import Command

from app.config import get_settings
from app.db.checkpointer import build_checkpointer
from app.graph.graph import build_graph
from app.prompts.seed_prompts import seed as seed_prompts
from app.tools.knowledge_kb import seed_plant_knowledge
from scripts.seed_readings import seed as seed_readings
from scripts.seed_tags import seed as seed_tags

pytestmark = pytest.mark.live

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _run_migrations() -> None:
    cfg = Config(os.path.join(BACKEND_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(BACKEND_DIR, "app", "db", "migrations"))
    command.upgrade(cfg, "head")


@pytest.fixture(scope="module", autouse=True)
def _prepare_schema():
    assert os.environ.get("OPENAI_API_KEY"), "OPENAI_API_KEY must be set for the live smoke test"
    assert os.environ.get("DATABASE_URL"), "DATABASE_URL must point at a real reachable Postgres"
    _run_migrations()
    seed_prompts()
    seed_tags()
    seed_readings()
    try:
        seed_plant_knowledge()
    except Exception as exc:  # noqa: BLE001 - see module docstring platform note
        print(f"[live smoke] plant knowledge seeding skipped/failed ({exc.__class__.__name__}): {exc}")
    yield


async def test_live_c201_drift_survives_checkpointer_restart_and_is_approved():
    settings = get_settings()

    thread_id = "live-smoke-thread"
    config = {"configurable": {"thread_id": thread_id}}
    graph_input = {
        "tag_id": "C-201-DISCH-PRESS",
        "reading_timestamp": "2026-09-15T19:00:00+00:00",
        "reading_value": 975.59,
    }

    # --- Phase 1: run until it pauses at engineer_review ----------------------
    async with build_checkpointer() as checkpointer_1:
        graph_1 = build_graph(checkpointer=checkpointer_1)

        saw_interrupt = False
        async for event in graph_1.astream(graph_input, config=config, stream_mode="updates"):
            print("EVENT:", list(event.keys()))
            if "__interrupt__" in event:
                saw_interrupt = True
                payload = event["__interrupt__"][0].value
                print("\n--- ANOMALY + INVESTIGATION + DRAFT WORK ORDER AT ENGINEER_REVIEW ---")
                print("anomaly_classification:", payload["anomaly_classification"])
                print("root_cause_hypothesis:", payload["root_cause_hypothesis"])
                print("draft_work_order:", payload["draft_work_order"])
                assert payload["anomaly_classification"] == "critical"
                assert payload["draft_work_order"]["title"], "expected a non-empty draft work order title"
                assert payload["draft_work_order"]["description"], "expected a non-empty draft description"
        assert saw_interrupt, "graph should have paused at engineer_review"

        state = await graph_1.aget_state(config)
        assert state.next == ("engineer_review",)
    # `async with` exits here -> checkpointer_1's connection pool is fully
    # closed, simulating the backend process shutting down (e.g. a shift
    # handover).

    # --- Phase 2: brand new checkpointer + graph, standing in for a --------
    # --- freshly-started process, resumes the SAME thread_id --------------
    async with build_checkpointer() as checkpointer_2:
        graph_2 = build_graph(checkpointer=checkpointer_2)

        # Prove the state genuinely persisted in Postgres, not in memory.
        resumed_state = await graph_2.aget_state(config)
        assert resumed_state.next == ("engineer_review",)
        assert resumed_state.values["anomaly_classification"] == "critical"

        finished = False
        async for event in graph_2.astream(
            Command(resume={"decision": "approve", "feedback": "Approved by live smoke test."}),
            config=config,
            stream_mode="updates",
        ):
            print("RESUME EVENT:", list(event.keys()))
            if "finalize" in event:
                finished = True

        assert finished, "graph should have reached finalize after resume"
        final_state = await graph_2.aget_state(config)
        assert final_state.next == ()
        assert final_state.values["status"] == "work_order_approved"
        assert final_state.values["final_status"] == "work_order_approved"
        print("\n--- FINAL STATE ---\n", {"final_status": final_state.values["final_status"]})
