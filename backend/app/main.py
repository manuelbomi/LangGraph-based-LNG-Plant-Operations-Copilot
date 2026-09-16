"""FastAPI application entrypoint.

Wires up (for the lifetime of the process):
  - a single `AsyncPostgresSaver` (LangGraph's durable Postgres checkpointer)
  - the compiled anomaly-investigation graph, built against that checkpointer
  - in-memory registries for active SSE queues / background run tasks

This is what makes `engineer_review` resumable across restarts: the
checkpointer's connection pool is opened once here, `saver.setup()` ensures
its tables exist, and every graph invocation anywhere in the app uses
`app.state.graph`, which is bound to that one durable checkpointer.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers.tags import router as tags_router
from app.api.routers.work_orders import router as work_orders_router
from app.config import get_settings
from app.db.checkpointer import build_checkpointer
from app.graph.graph import build_graph

logging.basicConfig(level=logging.INFO)

if sys.platform == "win32":
    # psycopg's async mode requires a selector-based event loop; Windows'
    # default ProactorEventLoop doesn't support it. No-op on Linux/macOS
    # (i.e. inside the backend Docker image and in CI).
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.run_queues = {}
    app.state.run_tasks = {}

    async with build_checkpointer() as checkpointer:
        app.state.checkpointer = checkpointer
        app.state.graph = build_graph(checkpointer=checkpointer)
        logging.info("Plant-ops anomaly-investigation graph compiled with AsyncPostgresSaver checkpointer.")
        yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="LNG Plant Operations Copilot API",
        description=(
            "LangGraph-powered decision-support copilot for plant operations and maintenance "
            "staff: ingest_reading -> detect_anomaly -> (normal: log_normal | warning/critical: "
            "investigate -> draft_work_order -> engineer_review -> finalize), with durable "
            "Postgres checkpointing and a mandatory human-in-the-loop interrupt before anything is "
            "logged as an approved work order. This app does NOT autonomously control any "
            "equipment and does NOT make a final safety-critical decision -- see the root README's "
            "Scope & Safety section."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(tags_router)
    app.include_router(work_orders_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
