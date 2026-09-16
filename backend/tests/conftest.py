"""Shared test fixtures.

All tests in `tests/` (excluding `tests/live/`) are fully mocked: no real
LLM calls, no real Postgres, no real network, no real Milvus Lite. This
keeps `pytest` free and fast to run in CI. The real end-to-end path is
exercised separately by `tests/live/test_live_smoke.py`, which is excluded
by default (see the `live` marker in `pyproject.toml`) and requires a real
`OPENAI_API_KEY` plus a reachable Postgres.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-dummy-key")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@localhost:5432/test")


class _FakeMessage:
    """Stands in for a LangChain `AIMessage` -- just needs `.content`."""

    def __init__(self, content: str):
        self.content = content


class _FakeStructuredRunnable:
    """Stands in for `chat_model.with_structured_output(Schema)`."""

    def __init__(self, parent: "FakeChatModel"):
        self._parent = parent

    async def ainvoke(self, prompt: Any, *args: Any, **kwargs: Any) -> Any:
        return self._parent._pop()


class FakeChatModel:
    """Stand-in for a LangChain chat model, supporting both
    `.with_structured_output(Schema).ainvoke(...)` (used by
    `investigate_node` and `draft_work_order_node`) and a direct
    `.ainvoke(...)` plain-text call.

    Construct with a list of canned responses: a pydantic model instance
    for a structured-output call, a plain `str` for a direct `.ainvoke()`
    call (auto-wrapped in a `_FakeMessage` so `.content` works), or an
    `Exception` instance to simulate a failure. Each call pops the next
    response in order, regardless of which method was used -- tests queue
    responses in the exact order the graph will call the model.
    """

    def __init__(self, responses: list[Any]):
        self._responses = list(responses)
        self.calls: list[Any] = []

    def _pop(self) -> Any:
        self.calls.append(True)
        if not self._responses:
            raise AssertionError("FakeChatModel called more times than responses were queued")
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def with_structured_output(self, schema: Any) -> _FakeStructuredRunnable:
        return _FakeStructuredRunnable(self)

    async def ainvoke(self, prompt: Any, *args: Any, **kwargs: Any) -> Any:
        item = self._pop()
        if isinstance(item, str):
            return _FakeMessage(item)
        return item


@pytest.fixture
def fake_chat_model(monkeypatch):
    """Patch `app.graph.nodes.get_chat_model` to return a FakeChatModel.

    Returns a factory: `make(responses=[...])` -> the FakeChatModel instance,
    so each test controls exactly what the "LLM" returns at each graph step.
    """
    holder: dict[str, FakeChatModel] = {}

    def make(responses: list[Any]) -> FakeChatModel:
        model = FakeChatModel(responses)
        holder["model"] = model
        return model

    def fake_get_chat_model(*args: Any, **kwargs: Any) -> FakeChatModel:
        return holder["model"]

    monkeypatch.setattr("app.graph.nodes.get_chat_model", fake_get_chat_model)
    return make


@pytest.fixture
def fake_prompts(monkeypatch):
    """Patch `app.graph.nodes.render_prompt` to a template-free passthrough.

    Node logic is what's under test here, not prompt wording (that's
    covered by the real templates in `app/prompts/seed_prompts.py`, which
    the live smoke test exercises against a real LLM). This just avoids
    requiring a Postgres-backed prompt registry in unit tests.
    """

    def fake_render_prompt(name: str, **kwargs: Any) -> str:
        return f"[[{name}]] {kwargs}"

    monkeypatch.setattr("app.graph.nodes.render_prompt", fake_render_prompt)


@pytest.fixture
def no_knowledge_io(monkeypatch):
    """Patch out the real Milvus Lite plant-knowledge search that
    `investigate_node` makes, so unit/flow/API tests never need
    milvus_lite installed or a seeded collection. Returns a small
    namespace: set `default_results` (a list of `KnowledgeChunkResult`-like
    objects) for every query, or key `results_by_query` for per-query
    control."""
    from app.tools.knowledge_kb import KnowledgeChunkResult

    class _Fakes:
        default_results: list[KnowledgeChunkResult] = []
        results_by_query: dict[str, list[KnowledgeChunkResult]] = {}
        calls: list[tuple[str, str | None]] = []

    fakes = _Fakes()

    def fake_search_plant_knowledge(query: str, equipment_id: str | None = None, top_k: int | None = None):
        fakes.calls.append((query, equipment_id))
        return fakes.results_by_query.get(query, fakes.default_results)

    monkeypatch.setattr("app.graph.nodes.search_plant_knowledge", fake_search_plant_knowledge)
    return fakes


class _FakeReadingRow:
    def __init__(self, timestamp: datetime, value: float):
        self.timestamp = timestamp
        self.value = value


class _FakeQuery:
    """Stands in for the `db.query(SensorReading).filter(...).order_by(...).limit(...).all()`
    chain used by `ingest_reading_node`. Filter args are accepted and
    ignored -- tests set the canned result list directly. Results are
    pre-sorted descending by timestamp at construction time (emulating
    `ORDER BY timestamp DESC`), since `ingest_reading_node` relies on that
    ordering before it reverses the (limited) result back to ascending."""

    def __init__(self, results: list[_FakeReadingRow]):
        self._results = sorted(results, key=lambda r: r.timestamp, reverse=True)

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, n, *args, **kwargs):
        limited = _FakeQuery.__new__(_FakeQuery)
        limited._results = self._results[:n]
        return limited

    def all(self):
        return self._results

    def count(self):
        return len(self._results)

    def first(self):
        return self._results[0] if self._results else None


class _FakeDbSession:
    def __init__(self, tags: dict, reading_rows: list[_FakeReadingRow]):
        self._tags = tags
        self._reading_rows = reading_rows

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, model, id_):
        from app.db.models import SensorTag

        if model is SensorTag:
            return self._tags.get(id_)
        return None

    def query(self, model):
        return _FakeQuery(list(self._reading_rows))

    def add(self, obj):
        pass

    def commit(self):
        pass


@pytest.fixture
def fake_sensor_db(monkeypatch):
    """Patch `app.graph.nodes.SessionLocal` (used by `ingest_reading_node`)
    with an in-memory fake. Returns a factory:
    `make(tag, history=[(timestamp, value), ...])`."""

    def make(tag, history: list[tuple[datetime, float]] | None = None):
        history = history or []
        rows = [_FakeReadingRow(ts, v) for ts, v in history]
        session = _FakeDbSession({tag.tag_id: tag}, rows)
        monkeypatch.setattr("app.graph.nodes.SessionLocal", lambda: session)
        return session

    return make


@pytest.fixture
def sample_tag():
    """A representative SensorTag-shaped object (not a real ORM instance --
    a lightweight namespace with the same attributes `ingest_reading_node`
    reads)."""

    class _Tag:
        tag_id = "C-201-DISCH-PRESS"
        name = "Compressor C-201 Discharge Pressure"
        unit = "psig"
        equipment_id = "C-201"
        equipment_name = "Process Gas Compressor C-201"
        description = "Discharge-side pressure transmitter on C-201."
        normal_min = 850.0
        normal_max = 930.0
        critical_min = 780.0
        critical_max = 960.0
        warning_z = 2.5
        warning_rate_per_hour = 0.35

    return _Tag()
