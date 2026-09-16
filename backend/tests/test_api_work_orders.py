"""API contract tests for the /tags and /work-orders endpoints.

Uses a lightweight in-memory fake in place of the Postgres-backed
`SessionLocal`, and an `InMemorySaver` in place of the Postgres checkpointer,
so these run without any real database. LLM + knowledge-base lookup calls
are mocked exactly as in `test_graph_nodes.py` / `test_graph_flow.py`.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from langgraph.checkpoint.memory import InMemorySaver

from app.api.routers.tags import router as tags_router
from app.api.routers.work_orders import router as work_orders_router
from app.db.models import SensorReading, SensorTag, WorkOrder
from app.graph.graph import build_graph
from app.graph.schemas import DraftWorkOrder


class _FakeResultSet:
    def __init__(self, rows: list):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _FakeReadingQuery:
    """Best-effort SQLAlchemy filter emulation: handles simple `column ==
    value` comparisons (enough for `_start_run`'s tag_id+timestamp lookup)
    by introspecting the binary expression's left column name and bound
    value. Comparisons it can't parse are left un-filtered rather than
    raising, since the readings-range endpoint isn't exercised by these
    tests."""

    def __init__(self, rows: list[SensorReading]):
        self._rows = rows

    def filter(self, *args, **kwargs):
        rows = self._rows
        for expr in args:
            try:
                col_name = expr.left.name
                value = expr.right.value
                if expr.operator.__name__ == "eq":
                    rows = [r for r in rows if getattr(r, col_name) == value]
            except AttributeError:
                pass
        return _FakeReadingQuery(rows)

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, n, *args, **kwargs):
        return _FakeReadingQuery(self._rows[:n])

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return self._rows

    def count(self):
        return len(self._rows)


class _FakeSession:
    def __init__(self, tags: dict, work_orders: dict, readings: list[SensorReading]):
        self._tags = tags
        self._work_orders = work_orders
        self._readings = readings

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def add(self, obj) -> None:
        if isinstance(obj, SensorTag):
            self._tags[obj.tag_id] = obj
        elif isinstance(obj, WorkOrder):
            self._work_orders[obj.id] = obj

    def commit(self) -> None:
        pass

    def get(self, model, id_):
        if model is SensorTag:
            return self._tags.get(id_)
        if model is WorkOrder:
            return self._work_orders.get(id_)
        return None

    def query(self, model):
        if model is SensorReading:
            return _FakeReadingQuery(self._readings)
        return _FakeReadingQuery([])

    def execute(self, stmt):
        entity = stmt.column_descriptions[0]["entity"]
        if entity is SensorTag:
            rows = sorted(self._tags.values(), key=lambda t: t.tag_id)
        else:
            rows = sorted(self._work_orders.values(), key=lambda w: w.created_at, reverse=True)
        return _FakeResultSet(rows)


def _seed_tag(tags: dict, tag_id="C-201-DISCH-PRESS") -> SensorTag:
    now = datetime.now(timezone.utc)
    tag = SensorTag(
        tag_id=tag_id,
        name="Compressor C-201 Discharge Pressure",
        unit="psig",
        equipment_id="C-201",
        equipment_name="Process Gas Compressor C-201",
        description="",
        normal_min=850.0,
        normal_max=930.0,
        critical_min=780.0,
        critical_max=960.0,
        warning_z=2.5,
        warning_rate_per_hour=0.35,
        current_status="unknown",
        last_evaluated_at=None,
        last_work_order_id=None,
        created_at=now,
        updated_at=now,
    )
    tags[tag_id] = tag
    return tag


@pytest.fixture
def api_app(monkeypatch, fake_chat_model, fake_prompts, no_knowledge_io):
    tags: dict[str, SensorTag] = {}
    work_orders: dict[str, WorkOrder] = {}
    _seed_tag(tags)

    base_ts = datetime(2026, 9, 15, 0, 0, 0, tzinfo=timezone.utc)
    readings = [SensorReading(tag_id="C-201-DISCH-PRESS", timestamp=base_ts + timedelta(hours=i), value=905.0) for i in range(168)]
    readings.append(SensorReading(tag_id="C-201-DISCH-PRESS", timestamp=base_ts + timedelta(hours=168), value=975.59))

    session = _FakeSession(tags, work_orders, readings)
    monkeypatch.setattr("app.api.routers.tags.SessionLocal", lambda: session)
    monkeypatch.setattr("app.api.routers.work_orders.SessionLocal", lambda: session)
    monkeypatch.setattr("app.graph.nodes.SessionLocal", lambda: session)

    app = FastAPI()
    app.state.run_queues = {}
    app.state.run_tasks = {}
    app.state.graph = build_graph(checkpointer=InMemorySaver())
    app.include_router(tags_router)
    app.include_router(work_orders_router)
    return app, tags, work_orders


async def _client(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_list_tags_returns_seeded_tag(api_app):
    app, _, _ = api_app
    async with await _client(app) as client:
        resp = await client.get("/tags")
        assert resp.status_code == 200
        ids = {t["tag_id"] for t in resp.json()["tags"]}
        assert "C-201-DISCH-PRESS" in ids


async def test_get_tag_detail(api_app):
    app, _, _ = api_app
    async with await _client(app) as client:
        resp = await client.get("/tags/C-201-DISCH-PRESS")
        assert resp.status_code == 200
        assert resp.json()["equipment_name"] == "Process Gas Compressor C-201"


async def test_get_unknown_tag_404(api_app):
    app, _, _ = api_app
    async with await _client(app) as client:
        resp = await client.get("/tags/does-not-exist")
        assert resp.status_code == 404


async def test_list_samples_returns_catalog(api_app):
    app, _, _ = api_app
    async with await _client(app) as client:
        resp = await client.get("/work-orders/samples")
        assert resp.status_code == 200
        ids = {s["id"] for s in resp.json()["samples"]}
        assert "c201-discharge-pressure-drift" in ids


async def test_run_reading_reaches_engineer_review(api_app, fake_chat_model, no_knowledge_io):
    app, _, _ = api_app
    fake_chat_model([DraftWorkOrder(title="t", description="Draft description.", priority="urgent")])

    async with await _client(app) as client:
        resp = await client.post(
            "/work-orders/run",
            json={"tag_id": "C-201-DISCH-PRESS", "timestamp": "2026-09-22T00:00:00+00:00"},
        )
        assert resp.status_code == 200
        wo_id = resp.json()["id"]

        await app.state.run_tasks[wo_id]

        detail = await client.get(f"/work-orders/{wo_id}")
        assert detail.status_code == 200
        body = detail.json()
        assert body["status"] == "awaiting_engineer_review"
        assert body["anomaly_classification"] == "critical"
        assert len(body["trace"]) >= 3


async def test_run_reading_unknown_tag_404(api_app):
    app, _, _ = api_app
    async with await _client(app) as client:
        resp = await client.post("/work-orders/run", json={"tag_id": "does-not-exist", "timestamp": "2026-09-22T00:00:00+00:00"})
        assert resp.status_code == 404


async def test_run_unknown_sample_404(api_app):
    app, _, _ = api_app
    async with await _client(app) as client:
        resp = await client.post("/work-orders/samples/does-not-exist/run")
        assert resp.status_code == 404


async def test_resume_work_order_completes(api_app, fake_chat_model):
    app, _, _ = api_app
    fake_chat_model([DraftWorkOrder(title="t", description="Draft description.", priority="urgent")])

    async with await _client(app) as client:
        resp = await client.post(
            "/work-orders/run",
            json={"tag_id": "C-201-DISCH-PRESS", "timestamp": "2026-09-22T00:00:00+00:00"},
        )
        wo_id = resp.json()["id"]
        await app.state.run_tasks[wo_id]

        resume_resp = await client.post(
            f"/work-orders/{wo_id}/resume", json={"decision": "approve", "feedback": "Looks good."}
        )
        assert resume_resp.status_code == 200
        await app.state.run_tasks[wo_id]

        detail = await client.get(f"/work-orders/{wo_id}")
        body = detail.json()
        assert body["status"] == "work_order_approved"
        assert body["final_status"] == "work_order_approved"
        # Regression check: the engineer's decision/feedback from
        # engineer_review_node's return value must be persisted onto the
        # WorkOrder row, not silently dropped (see _record_event).
        assert body["human_decision"] == "approve"
        assert body["human_feedback"] == "Looks good."


async def test_resume_rejects_when_not_found(api_app):
    app, _, _ = api_app
    async with await _client(app) as client:
        resp = await client.post("/work-orders/does-not-exist/resume", json={"decision": "approve", "feedback": ""})
        assert resp.status_code == 404


async def test_list_work_orders_returns_summaries(api_app):
    app, _, work_orders = api_app
    now = datetime.now(timezone.utc)
    work_orders["w1"] = WorkOrder(
        id="w1", tag_id="C-201-DISCH-PRESS", equipment_id="C-201", equipment_name="Process Gas Compressor C-201",
        reading_timestamp=now, reading_value=975.0, status="work_order_approved", final_status="work_order_approved",
        anomaly_classification="critical", anomaly_details={}, retrieved_context=[], root_cause_hypothesis="",
        recommended_response="", citations=[], draft_work_order={}, human_decision="approve", human_feedback="",
        trace=[], state_snapshot={}, error=None, created_at=now, updated_at=now,
    )
    work_orders["w2"] = WorkOrder(
        id="w2", tag_id="C-201-DISCH-PRESS", equipment_id="C-201", equipment_name="Process Gas Compressor C-201",
        reading_timestamp=now, reading_value=940.0, status="awaiting_engineer_review", final_status=None,
        anomaly_classification="warning", anomaly_details={}, retrieved_context=[], root_cause_hypothesis="",
        recommended_response="", citations=[], draft_work_order={}, human_decision=None, human_feedback="",
        trace=[], state_snapshot={}, error=None, created_at=now, updated_at=now,
    )

    async with await _client(app) as client:
        resp = await client.get("/work-orders")
        assert resp.status_code == 200
        ids = {w["id"] for w in resp.json()["work_orders"]}
        assert ids == {"w1", "w2"}


async def test_get_unknown_work_order_404(api_app):
    app, _, _ = api_app
    async with await _client(app) as client:
        resp = await client.get("/work-orders/nope")
        assert resp.status_code == 404
