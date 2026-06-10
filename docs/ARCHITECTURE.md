# Architecture

This document explains how the IADS SQL Agent is built today, the design choices behind it, and what the path to production-grade would look like.

## Design philosophy

We made three explicit trade-offs:

1. **Ship working code under 48 hours, not perfect code.** Where production quality and shippability conflicted, we chose shippability and documented the gap.
2. **Right patterns, simple implementations.** We adopted clean module boundaries, Pydantic models for typed contracts, and dependency injection — but kept implementations synchronous and minimal. A v2 would harden these without changing the architecture.
3. **Honest demos, measured outcomes.** No hardcoded "magic retry" tricks. The benchmark numbers in `evaluation/results/` are real.

## System overview

```
┌─────────────────┐         ┌──────────────────────────────────────────┐
│  Streamlit UI   │ ──HTTP─▶│             FastAPI Backend              │
└─────────────────┘         │                                          │
                            │  ┌──────────────────────────────────┐    │
                            │  │     ExecutionOrchestrator        │    │
                            │  │                                  │    │
                            │  │   Planner → SchemaRetriever      │    │
                            │  │       → SQLGenerator             │    │
                            │  │       → SQLValidator             │    │
                            │  │       → SafeExecutor             │    │
                            │  │       → Critic ─loop─┐           │    │
                            │  │       → Summariser   │           │    │
                            │  └──────────────────────┼───────────┘    │
                            │             │           │                │
                            │             ▼           ▼                │
                            │  ┌──────────────┐  ┌─────────────────┐   │
                            │  │  OCI GenAI   │  │ Autonomous DB   │   │
                            │  │   + Embed    │  │  (read-only)    │   │
                            │  └──────────────┘  └─────────────────┘   │
                            │                                          │
                            │  ┌──────────────────────────────────┐    │
                            │  │  Oracle 23ai Vector Store        │    │
                            │  │  (schema descriptions, indexed)  │    │
                            │  └──────────────────────────────────┘    │
                            └──────────────────────────────────────────┘
```

## Runtime composition (what actually runs)

The diagram above is the conceptual design (ADR-001). In this submission the
**live entrypoint is the `app/` package**, which composes those stages as one
synchronous pass — fast, observable, and easy to demo. `src/sql_agent/` holds
the typed stage *interfaces* (`agents/`), the production **Summariser**
(`agents/summariser.py`, imported directly by the running pipeline), and the
retrieval / safety / evaluation helpers. As-built flow:

```
Streamlit (frontend/streamlit_app.py)
   |  HTTP
FastAPI (app/main.py)  ->  FullPipeline.run()   [app/pipeline.py]
  1. Multi-turn resolve + glossary enrich   [app/pipeline.py, retrieval/glossary.py]
  2. RAG schema/KPI retrieval               [app/rag/retriever.py]      -- OCI GenAI embeddings / 23ai Vector*
  3. Text-to-SQL                            [app/sql/generator.py]      -- OCI Select AI -> OCI GenAI (Cohere)
  4. Validate: single read-only SELECT      [app/sql/validator.py, safety/sql_guard*]
  5. Execute                                [evaluation/local_db.py offline | OCI Autonomous DB live]
  6. If 0 rows -> VECTOR ROW-FALLBACK        [retrieval/row_fallback.py]  -- nearest real rows ("similar results")
  7. Summarise + insights + chart + confidence  [agents/summariser.py]
```

\* `23ai Vector` and direct GenAI embeddings are the pluggable production
backends; offline the same interfaces are served by an in-memory lexical index
and lexical row-similarity, so the demo runs with no cloud dependency. Raw seed
CSVs stage through **OCI Object Storage** before loading into Autonomous Database.

Two behaviours make this an **agent**, not a one-shot translator:

- **Multi-turn context** — a follow-up like "...and by category?" is resolved
  against the previous question within the session, not answered blind.
- **Vector/similarity decisioning** — when an exact match does not exist, the
  agent returns the nearest real rows flagged as *approximate* instead of "no
  results", directly satisfying the brief's "similar results" requirement.

## The agent stages

Each stage has a single responsibility and a typed input/output contract.

### 1. Planner

**Input:** user's natural-language question
**Output:** a `Plan` describing what to do (run SQL / ask for clarification / refuse).

Decides whether the question is actually a data question. Filters out chat ("what can you do?"), out-of-scope questions ("what's the weather?"), and ambiguous ones requiring clarification.

### 2. Schema Retriever (the RAG layer)

**Input:** the question
**Output:** top-k relevant table and column descriptions

Embeds the question with `cohere.embed-english-v3.0` and retrieves nearest schema descriptions from the Oracle 23ai vector store. This is **how we satisfy the brief's RAG requirement** — RAG over schema metadata, not over documents.

Why schema-aware retrieval matters: passing a 200-column schema to the LLM wastes tokens and confuses the model. Passing the 5 relevant columns produces dramatically better SQL.

### 3. SQL Generator

**Input:** question + retrieved schema + (optional) previous error
**Output:** candidate SQL

Calls OCI Generative AI with the prompt in `prompts/sql_generation.md`. If a previous attempt failed, the error is passed in as context so the model can self-correct.

### 4. SQL Validator

**Input:** candidate SQL + schema
**Output:** validation result (`valid` | `invalid` with reason)

**Static checks before we ever touch the DB:**
- Parses with `sqlglot` to confirm syntax
- Confirms referenced tables and columns exist in the schema
- Rejects DDL (`CREATE`, `DROP`, `ALTER`) and DML (`INSERT`, `UPDATE`, `DELETE`)
- Caps complexity (no more than N joins, no unbounded cartesian products)

This stage catches the most common LLM failure modes (hallucinated columns) cheaply, before they cost a DB round-trip.

### 5. Safe Executor

**Input:** validated SQL
**Output:** result rows or DB error

Runs against a **read-only DB user** with:
- 15-second query timeout
- 500-row result cap
- Connection from a managed pool

The read-only DB user is the most important safety property — even if every other layer fails, the database itself cannot be modified.

### 6. Critic (the agentic loop)

**Input:** question + SQL + result
**Output:** `accept` | `retry with feedback`

Reviews the result against the question. If the result looks wrong (empty when it shouldn't be, columns mismatched, etc.), it returns feedback that the Generator uses on the next iteration.

Capped at 3 retries to prevent runaway loops.

### 7. Summariser

**Input:** question + SQL + result rows (+ retrieved schema)
**Output:** `AnswerSummary` — one-sentence answer, 2–4 plain-English bullets, and the tables used

Turns rows back into language. Two design choices make it demo-safe:

- **Hybrid summarisation.** Large result sets are never dumped into the prompt.
  We compute per-column aggregates deterministically in code (row count, dtypes,
  min/max/sum/mean, distinct, top values) and feed those to the model alongside a
  small row sample, with an explicit instruction to trust the computed numbers
  over its own arithmetic. A configurable `max_preview_rows` caps how many raw
  rows ever reach the prompt — preventing token bloat and hallucinated maths on
  500-row results.
- **Always returns something.** The LLM client is injected and optional; with no
  client (offline, rate-limited, or under test) the stage falls back to a
  deterministic template summary, so the pipeline never returns nothing.

All user-facing and logged output passes through the PII filter (`safety/`), and
token usage is metered by `llm/token_counter.py`. The explanation panel uses a
separate prompt (`prompts/sql_explanation.md`) so the "how it works" text stays
in business language with no SQL jargon.

## Core design choices (ADRs)

Architecture Decision Records live in [`decisions/`](decisions/):

- [ADR-001: Multi-stage agent over single-shot prompt](decisions/001-multi-stage-agent.md)
- [ADR-002: Schema-aware retrieval as the RAG layer](decisions/002-schema-retrieval.md)
- [ADR-003: Safety guardrails at the database layer](decisions/003-safety-guardrails.md)

## Project structure

```
app/                   # >>> LIVE RUNTIME <<<
├── main.py            # FastAPI entrypoint
├── pipeline.py        # FullPipeline.run() — composes the stages (single pass)
├── rag/               # RAG retrieval + embeddings over schema/KPI docs
├── sql/               # Select AI text-to-SQL, prompt builder, validator
└── agents/            # request orchestration

frontend/              # Streamlit chat UI (insights, chart, confidence, clarify)

src/sql_agent/         # typed interfaces + shared libraries
├── core/              # Domain models (Pydantic), exceptions
├── agents/            # stage interface specs (ADR-001) + production Summariser
├── retrieval/         # glossary, row_fallback (vector fallback), vector-store iface
├── safety/            # PII filter (+ SQL-guard / obfuscator interfaces)
└── api/               # FastAPI app + typed schemas

evaluation/            # benchmark harness, metrics, offline LocalDB (DuckDB)
```

**Boundaries:**
- `core/` has no internal dependencies — it's the shared vocabulary
- `agents/` depends on `llm/`, `retrieval/`, `database/`, `safety/`
- `api/` depends only on `agents/` and `core/`
- The dependency graph is acyclic — no circular imports

## Path to production

What we'd add given another two weeks. **None of this is in the current code; this section is honest about the gap.**

### Async throughout

Today the pipeline is synchronous. LLM and DB calls can take 1–3 seconds each — under load this blocks the FastAPI event loop. Production version would:
- Use `oracledb`'s async API for DB calls
- Use OCI GenAI's streaming/async client where available
- Move blocking calls behind `asyncio.to_thread` as a fallback

### Observability

Today we use `structlog` for structured logs. Production version would add:
- **OpenTelemetry tracing** — propagate trace IDs across every stage
- **Prometheus metrics** — query count, latency p50/p95/p99, retry rate, success rate, token cost per query
- **Sentry or similar** for error aggregation
- **Cost tracking** per query (prompt + completion tokens × price)

### Reliability patterns

- **Retry decorators** (`tenacity`) with exponential backoff for LLM and DB calls
- **Circuit breaker** so a failing LLM doesn't take down the API
- **Bulkhead** — connection pool size limits prevent one slow query starving others
- **Idempotency keys** so retried requests don't double-execute

### Evaluation pipeline

Today we have a one-shot benchmark script. Production version would:
- Run the benchmark on every PR via CI
- Track accuracy over time (regression detection)
- Compare against held-out test queries the model has never seen
- Generate cost-vs-accuracy plots for different model sizes

### Security hardening

- **Authentication** (OAuth2 / API keys) — currently the API is unauthenticated
- **Per-user rate limiting** — currently uncapped
- **Audit log** of every query, with the SQL run and who asked it
- **Row-level security** for multi-tenant deployments
- **Prompt injection defences** — the question is treated as untrusted input today, but we don't have an explicit defence layer

### Deployment

- Today: `docker-compose up` (provided)
- Production: Kubernetes with horizontal pod autoscaling, separate replicas for API and async workers, blue/green deploys

### Data layer

- Today: a single Autonomous DB instance
- Production: read replica for the agent, primary for ingestion, sharded vector store for very large schemas

### Caching

- **Semantic cache** on questions — same question with similar phrasing returns cached SQL
- **Schema embedding cache** — embeddings re-computed only when schema changes

## Why this honesty matters

When a hiring manager reviews this repo, they should see two things:

1. The code we **did ship** is clean, tested, properly structured, and honest about its scope.
2. The architecture we **understand** — and could ship given more time — is documented in this file.

That's a far stronger signal than over-engineered code that nobody understands or over-claimed capabilities that don't survive a five-minute conversation.
