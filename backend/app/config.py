"""Centralized application settings.

All configuration is read from environment variables (see `.env.example` at
the repo root). We use `pydantic-settings` so misconfiguration fails fast and
loudly at process startup instead of deep inside a graph node.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- LLM provider ---------------------------------------------------
    llm_provider: str = "openai"  # "openai" | "anthropic"
    llm_model: str = "gpt-4o-mini"
    anthropic_model: str = "claude-3-5-haiku-latest"
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    embedding_model: str = "text-embedding-3-small"
    # Root-cause investigation and work-order drafting should stay close to
    # deterministic -- this is decision-support documentation, not creative
    # writing, and every output is explicitly a recommendation for a human
    # engineer to review, never an automated equipment-control decision.
    llm_temperature: float = 0.0

    # --- Postgres (prompts, sensor tags/readings, work-order history, LangGraph checkpoints) --
    # SQLAlchemy (sync engine) uses the psycopg3 dialect: postgresql+psycopg://
    database_url: str = (
        "postgresql+psycopg://postgres:postgres@localhost:5432/plant_ops"
    )
    # AsyncPostgresSaver needs a plain psycopg-style DSN (no "+psycopg" driver
    # suffix); we strip it in db/checkpointer.py.

    # --- Sample data -------------------------------------------------------
    # Where the bundled synthetic sensor readings / equipment metadata /
    # maintenance manuals / incident reports live, so the seed scripts and
    # the zero-setup demo can find them. Defaults to the repo-root
    # `sample-data/` folder one level up from `backend/`; overridden to
    # `/app/sample-data` in Docker (see docker-compose.yml, which mounts it
    # read-only).
    sample_data_dir: str = "../sample-data"

    # --- Anomaly detection ---------------------------------------------
    # How many prior hourly readings `ingest_reading` loads from Postgres as
    # the statistical baseline/history window for `detect_anomaly`.
    history_window_hours: int = 168  # 7 days

    # --- Milvus Lite (embedded vector store, no server/docker needed) ---
    # Used for semantic maintenance-manual / past-incident lookup only -- see
    # app/tools/knowledge_kb.py. Retrieved content always feeds a root-cause
    # HYPOTHESIS for engineer review, never an automated action.
    milvus_lite_path: str = "./data/milvus_plant_knowledge.db"
    milvus_collection: str = "plant_knowledge_base"
    knowledge_search_top_k: int = 6

    # --- API ---------------------------------------------------------------
    cors_allow_origins: str = "http://localhost:5173,http://localhost:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
