# LangGraph Tutorial 06: LNG Plant Operations Copilot

A [LangGraph](https://langchain-ai.github.io/langgraph/)-powered decision-support
copilot for plant operations and maintenance staff at a fictitious LNG
processing facility: it classifies incoming sensor readings against real
statistical anomaly-detection logic, and for anything abnormal, semantically
searches the plant's own maintenance manuals and past-incident reports to
propose a root-cause hypothesis and a draft work order -- all subject to
mandatory engineer review before anything is logged as approved.

This is part of a tutorial series building small, production-shaped
LangGraph applications:

1. `langgraph-tutorial-01-research-report-assistant`
2. `langgraph-tutorial-02-invoice-audit-reconciliation`
3. `langgraph-tutorial-03-tax-document-intake`
4. `langgraph-tutorial-04-clinical-documentation-assistant`
5. `langgraph-tutorial-05-prior-authorization-assistant`
6. **`langgraph-tutorial-06-lng-plant-ops-copilot`** (this repo)

---

## Scope & Safety -- read this first

**This application is strictly a decision-support / documentation-drafting
copilot for plant operations and maintenance staff. It does NOT
autonomously control any equipment, and it does NOT make a final
safety-critical decision.**

- It never issues a command to any piece of equipment, opens or closes any
  valve, changes any setpoint, or takes any physical action of any kind.
  There is no code path in this repository that can reach a real control
  system -- it doesn't even have a concept of one.
- The deterministic anomaly classification (`normal` / `warning` /
  `critical`) is a triage aid, not a safety instrumented system trip. It is
  produced by ordinary statistics (rolling mean/std, rate-of-change, fixed
  thresholds, stuck-sensor detection) over historical data -- see
  `backend/app/tools/anomaly_detection.py`.
- The root-cause hypothesis produced by `investigate` is explicitly framed,
  in its own prompt text, as a **hypothesis for engineer confirmation**,
  grounded only in retrieved excerpts from the plant's own manuals/incident
  history -- never a certainty, and never medical-, legal-, or
  safety-instrumented-system advice.
- **Every drafted work order must be explicitly reviewed and
  approved, escalated, or dismissed as benign by a qualified engineer/
  operator** via the mandatory `engineer_review` step before it is ever
  considered an official work order. Nothing is dispatched to any real
  system automatically -- this app doesn't even have a "dispatch" button; a
  human logs the resulting decision as documentation.
- **All equipment, sensor data, maintenance manuals, and incident reports
  in this repository are entirely synthetic and fictitious.** There is no
  real operating facility, no real proprietary equipment or vendor data,
  and no real incident anywhere in this repo. The fictitious facility
  referenced throughout is "Northgate Point LNG Terminal" -- an invented
  name for demo purposes only. See `sample-data/README.md` for exactly
  what was invented and why.

This system prompt language is embedded directly in the seeded LLM prompts
(see `backend/app/prompts/seed_prompts.py`):

> "You are a decision-support copilot for plant operations and maintenance
> staff at an LNG processing facility. You help engineers and operators
> triage sensor anomalies faster by surfacing likely root causes and
> recommended next steps from the plant's own maintenance manuals and
> past-incident history. You do NOT autonomously control any equipment and
> you do NOT make a final safety-critical decision -- every hypothesis and
> recommendation you produce is a draft for a qualified engineer or
> operator to review, correct, and approve, escalate, or dismiss as benign
> before anything is acted on."

The frontend also displays a persistent "decision support only, does not
control equipment" banner on every page, and a second, more detailed safety
banner on the engineer review panel itself.

---

## What the app does

```mermaid
flowchart TD
    START([New sensor reading]) --> INGEST[ingest_reading\nload tag metadata + recent history from Postgres]
    INGEST --> DETECT{detect_anomaly\nDETERMINISTIC: z-score, rate-of-change,\nthreshold breach, stuck-sensor check}
    DETECT -->|normal| LOGNORMAL[log_normal\nlog + update dashboard status]
    LOGNORMAL --> END1([END -- no LLM calls])
    DETECT -->|warning / critical| INVESTIGATE[investigate\nMilvus Lite semantic search vs. manuals + past incidents\n+ LLM root-cause hypothesis]
    INVESTIGATE --> DRAFT[draft_work_order\nLLM: title, description, priority]
    DRAFT --> REVIEW{{engineer_review\ninterrupt -- SAFETY GATE}}
    REVIEW -->|approve / escalate / dismiss benign| FINALIZE[finalize\nrecord decision, update dashboard status]
    FINALIZE --> END2([END])

    style REVIEW fill:#fef3c7,stroke:#d97706,stroke-width:2px
    style DETECT fill:#eef4fc,stroke:#265d9c,stroke-width:1px
    style LOGNORMAL fill:#f1f5f9,stroke:#94a3b8,stroke-width:1px
```

Six real graph nodes plus a lightweight terminal node, run per sensor
reading (one LangGraph thread per processed reading), with **real
conditional routing** -- not a straight-line pipeline:

1. **ingest_reading** -- loads the tag's metadata (unit, normal/critical
   range) and its recent historical reading window from Postgres. No LLM
   call.
2. **detect_anomaly** -- a **deterministic** statistical check: rolling
   mean/std z-score against the historical baseline, a smoothed
   rate-of-change (early-warning for a developing drift), a fixed
   threshold breach against the tag's configured normal/critical range,
   and a stuck/flat-sensor check (a frozen sensor can look numerically
   "normal" while providing zero real information). Classifies the
   reading `normal` / `warning` / `critical`. No LLM call anywhere in this
   node -- see `backend/app/tools/anomaly_detection.py`.
3. **Conditional edge**: `normal` readings route straight to `log_normal`
   and skip everything else (no LLM calls, cheapest possible path for the
   large majority of readings). `warning`/`critical` readings continue to
   investigation.
4. **investigate** -- semantic search (a local, embedded **Milvus Lite**
   collection, no server/Docker container needed) over the plant's
   maintenance-manual and past-incident knowledge base, filtered to the
   relevant equipment. An LLM call (`gpt-4o-mini` by default) then
   synthesizes a root-cause **hypothesis** and recommended response, with
   citations back to the specific retrieved manual section or incident
   report -- explicitly framed as a hypothesis for engineer confirmation.
5. **draft_work_order** -- an LLM call assembles a structured work order:
   trusted fields from state (equipment, tag, observed anomaly, severity)
   plus an LLM-written title, description, and priority, always ending
   with an explicit "draft recommendation requiring engineer review" note.
6. **engineer_review** (LangGraph `interrupt()`) -- **the mandatory safety
   gate.** Presents the anomaly, the investigation, and the draft work
   order for a qualified engineer to edit and Approve / Escalate / Dismiss
   as Benign. Nothing is finalized without this step.
7. **finalize** -- records the engineer's decision and updates the tag's
   cached dashboard status. Purely a documentation update -- it never
   controls any equipment.

---

## Why LangGraph specifically: conditional routing + durable checkpointing + mandatory human review

This app is a good showcase for three things a linear chain/pipeline
framework handles awkwardly, and LangGraph handles natively:

- **Real conditional branching, not just a linear chain.** The large
  majority of sensor readings in a real plant are perfectly normal and
  should be logged as cheaply as possible -- no LLM calls, no semantic
  search, nothing. Only the minority that are abnormal need the full
  investigate/draft/review pipeline. `add_conditional_edges` after
  `detect_anomaly` expresses this directly as a graph shape: one node's
  output routes to one of two entirely different continuations. Bolting
  this onto a linear prompt-chaining library means either always running
  every step (wasteful and slow) or hand-rolling your own branching
  control flow outside the framework -- LangGraph's state machine makes it
  a first-class, inspectable part of the graph definition itself.
- **Durable, resumable checkpointing across a shift handover.**
  Investigating a warning/critical reading and getting a qualified
  engineer's sign-off is not guaranteed to happen in the same shift it was
  detected in -- alarm queues get triaged asynchronously, and a
  reliability engineer may not review a flagged anomaly until hours later,
  possibly after a full shift change. LangGraph's `interrupt()` combined
  with the Postgres-backed checkpointer (`AsyncPostgresSaver`) means every
  investigation's graph run pauses durably at `engineer_review`, with the
  full state (readings, anomaly classification, retrieved manual/incident
  context, draft work order) persisted to Postgres, not held in server
  memory. The FastAPI process can restart or redeploy, and an anomaly can
  simply sit untouched in the queue for as long as needed; when an
  engineer comes back (even from an entirely new process), `Command(resume=...)`
  against the same `thread_id` picks up exactly where it left off. This is
  proven end-to-end by `backend/tests/live/test_live_smoke.py`, which
  tears down and rebuilds the checkpointer + graph between the interrupt
  and the resume, simulating an engineer returning to the queue in a fresh
  process after a shift change.
- **Mandatory human-in-the-loop, never fully autonomous.** Safety-critical
  industrial actions must never be taken by a fully autonomous system on
  its own inference. `engineer_review`'s `interrupt()` is not an
  optimization or a UX nicety here -- it is the load-bearing safety
  mechanism of the entire application. There is no code path from a
  drafted work order to any real action that does not pass through this
  gate.

---

## Sample data / zero-setup demo

Everything needed for a working out-of-the-box demo is bundled and
entirely synthetic -- see `sample-data/README.md` for full provenance:

- `sample-data/sensor_readings.csv` -- a synthetic 30-day hourly time
  series (3,600 rows) across 5 fictitious instrument tags, with three
  realistic anomalies deliberately injected: a **slow drift** toward the
  high alarm threshold on a compressor discharge pressure tag, a **sudden
  spike** on a cryogenic heat exchanger temperature-differential tag, and
  a **stuck/flat sensor** on a rotating pump's vibration tag (frozen at a
  numerically plausible value) -- plus one healthy control tag and one
  tag with a brief, benign pressure bump.
- `sample-data/equipment/*.json` -- 5 fictitious sensor tag/equipment
  records (unit, normal/critical thresholds).
- `sample-data/manuals/*.txt` -- 5 synthetic equipment
  maintenance-manual/troubleshooting excerpts, one per piece of equipment,
  embedded into a local Milvus Lite collection.
- `sample-data/incidents/*.txt` -- 3 synthetic past incident reports
  mirroring the three injected anomaly patterns, also embedded for
  "similar past incident" citation.

On first boot (`docker-entrypoint.sh`, or the manual steps below), the
backend runs migrations, seeds the two LLM prompts, loads the fictitious
sensor tags and the full readings time series into Postgres, embeds the
manuals/incidents into Milvus Lite, and seeds 4 already-processed example
work orders spanning different equipment, severities, and engineer
decisions (including one for each of the drift/spike/stuck-sensor
anomalies). You can then trigger processing of any bundled sample reading
(including a healthy one, to see the `normal` branch) straight from the
Plant Dashboard and watch the live graph execution end to end.

---

## Repo structure

```
langgraph-tutorial-06-lng-plant-ops-copilot/
├── backend/            FastAPI + LangGraph app (Python 3.11+)
│   ├── app/
│   │   ├── api/         REST + SSE routers (tags, work-orders)
│   │   ├── db/          SQLAlchemy models, session, Postgres checkpointer, Alembic migrations
│   │   ├── graph/        LangGraph state, pydantic schemas, nodes, graph assembly (with conditional routing)
│   │   ├── prompts/      Postgres-backed prompt registry + v1 seed prompts
│   │   └── tools/        Deterministic anomaly detection, manual/incident parsing, Milvus Lite plant-knowledge lookup
│   ├── scripts/          seed_tags.py, seed_readings.py, seed_examples.py
│   └── tests/            Mocked unit/flow/API tests + tests/live/ (real OpenAI + Postgres)
├── frontend/           Vite + React 18 + TypeScript + Tailwind
│   └── src/
│       ├── api/          Typed API client (mirrors backend/app/api/schemas.py)
│       ├── components/   GraphView (branching reactflow), SensorChart (recharts), ReviewForm, StatusBadge, FindingsPanel
│       ├── hooks/         useWorkOrderStream (SSE)
│       └── pages/         Plant Dashboard, Sensor Detail, Work Order Queue, Work Order Detail
├── sample-data/        Synthetic sensor readings, equipment metadata, manuals, incident reports
├── docker-compose.yml  postgres + backend + frontend (Milvus Lite is embedded, no extra container)
└── .github/workflows/ci.yml
```

---

## Prompt registry

Both LLM prompts (`investigate_anomaly`, `draft_work_order`) live in the
Postgres `prompts` table, versioned, with exactly one `is_active` version
per name at a time (`backend/app/prompts/registry.py`). Seed or roll a new
version with:

```bash
cd backend
python -m app.prompts.seed_prompts
```

or call `app.prompts.registry.add_prompt_version(name, new_template)` to
add and activate a new version programmatically (e.g. from a script or an
admin-only route) without redeploying code.

---

## Setup & run

### Option A: Docker Compose (recommended)

```bash
cp .env.example .env   # fill in OPENAI_API_KEY
docker compose up --build
```

- Frontend: http://localhost:8080
- Backend API: http://localhost:8000 (docs at `/docs`)
- Postgres: localhost:5432

Milvus Lite is **embedded** (a local file under the backend's `/app/data`
volume) -- there is no separate Milvus container, matching the pattern used
in `langgraph-tutorial-01-research-report-assistant` and
`langgraph-tutorial-05-prior-authorization-assistant`.

### Option B: Local dev (no Docker)

Requires a local/reachable Postgres. **Note:** `pymilvus[milvus_lite]`'s
native binary is published for Linux/macOS only -- on native Windows,
`investigate` will gracefully degrade to an empty retrieved-context list
(it catches the import/connection failure and returns an empty list, and
skips the root-cause LLM call, going straight to a "recommend manual
investigation" fallback) rather than crashing; run the backend via Docker
or WSL on Windows if you need working semantic search locally. Anomaly
detection itself is pure Python/statistics and works identically
everywhere.

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
cp ../.env.example ../.env   # edit as needed; also copy to backend/.env if you prefer per-service env files
alembic upgrade head
python -m app.prompts.seed_prompts
python -m scripts.seed_tags
python -m scripts.seed_readings
python -m app.tools.knowledge_kb   # embeds sample-data/manuals + incidents into Milvus Lite
python -m scripts.seed_examples
uvicorn app.main:app --reload
```

```bash
cd frontend
npm install
npm run dev
```

### Running tests

```bash
# Backend -- mocked unit/flow/API tests (no real API calls, no live Postgres)
cd backend && pytest -v

# Backend -- REAL end-to-end smoke test (real OpenAI calls + real Postgres)
export OPENAI_API_KEY=sk-...
export DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/plant_ops
pytest -m live tests/live/test_live_smoke.py -v -s

# Frontend
cd frontend
npm run typecheck
npm run build
npm run test
```

---

## License

MIT License, Copyright (c) 2026 Emmanuel Oyekanlu. See [`LICENSE`](./LICENSE).
