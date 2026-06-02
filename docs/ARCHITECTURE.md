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

## The five-stage agent

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

**Input:** question + SQL + result rows
**Output:** natural-language summary

Produces a one-sentence answer plus a brief explanation. Returned alongside the raw table and SQL so the user can verify.

## Core design choices (ADRs)

Architecture Decision Records live in [`decisions/`](decisions/):

- [ADR-001: Multi-stage agent over single-shot prompt](decisions/001-multi-stage-agent.md)
- [ADR-002: Schema-aware retrieval as the RAG layer](decisions/002-schema-retrieval.md)
- [ADR-003: Safety guardrails at the database layer](decisions/003-safety-guardrails.md)

## Project structure

```
src/sql_agent/
├── config/           # Typed settings — Pydantic Settings reads .env
├── core/             # Domain models (Pydantic), exceptions, logging
├── llm/              # OCI GenAI client wrapper + prompt loader
├── retrieval/        # Embeddings + vector store + schema retriever
├── database/         # Connection pool + safe executor + introspection
├── agents/           # Each stage; orchestrator runs the pipeline
├── safety/           # SQL guard + PII filter
└── api/              # FastAPI app + routes
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
