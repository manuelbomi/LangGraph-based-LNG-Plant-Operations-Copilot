#!/usr/bin/env sh
set -e

echo "[entrypoint] running Alembic migrations..."
alembic upgrade head

echo "[entrypoint] seeding prompt registry (v1 prompts, no-op if already active)..."
python -m app.prompts.seed_prompts

echo "[entrypoint] loading fictitious sensor tags/equipment..."
python -m scripts.seed_tags

echo "[entrypoint] loading sensor readings time series..."
python -m scripts.seed_readings

echo "[entrypoint] seeding maintenance manuals / incident reports into Milvus Lite..."
python -m app.tools.knowledge_kb || echo "[entrypoint] plant knowledge seeding skipped/failed (needs OPENAI_API_KEY) -- continuing"

echo "[entrypoint] seeding example work orders..."
python -m scripts.seed_examples

echo "[entrypoint] starting API server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
