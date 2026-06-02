# IADS SQL Agent

> Multi-stage agentic text-to-SQL system on Oracle Cloud Infrastructure.
> Team 4 · IADS Agentic AI Hackathon 2026.

**Status:** scaffold. Implementation begins at the hackathon kickoff (2 June 2026).

## What it does

Ask a question in plain English. Get back an answer, a table, and the SQL that produced it.

```
You: "Which product category generated the most revenue last quarter in the UK?"

Agent: Electronics generated £4.2M in Q1 2026, up 18% year-on-year.
       — based on 12,847 rows of sales data

       SQL: SELECT product_category, SUM(revenue) AS total
            FROM sales
            WHERE region = 'UK' AND quarter = '2026-Q1'
            GROUP BY product_category
            ORDER BY total DESC
            FETCH FIRST 5 ROWS ONLY;
```

## Architecture

A five-stage agentic pipeline. See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full design.

```
User question
   ↓
[Planner] → [Schema Retriever] → [SQL Generator]
                                      ↓
                                 [Validator]
                                      ↓
                                 [Safe Executor]
                                      ↓
                                 [Critic] ─── retry with feedback (max 3)
                                      ↓
                                 [Summariser]
                                      ↓
                                Response
```

## Quick start

```bash
# Install
make dev

# Configure
cp .env.example .env  # then edit with your OCI credentials

# Run
make run-api    # FastAPI at http://localhost:8000
make run-ui     # Streamlit at http://localhost:8501
```

## Repository layout

```
src/sql_agent/      Core package
  config/           Typed settings
  core/             Domain models, exceptions, logging
  llm/              OCI Generative AI client
  retrieval/        Schema embeddings + vector store (RAG)
  database/         Autonomous DB connection + safe executor
  agents/           Multi-stage pipeline + orchestrator
  safety/           SQL guard rails
  api/              FastAPI app

frontend/           Streamlit UI
evaluation/         Benchmark harness
tests/              Unit + integration tests
prompts/            Versioned prompt templates
docs/               Architecture + decision records
scripts/            Seed DB, embed schema, run benchmark
```

## Team

| Member | Role |
|---|---|
| Omar Khalel | Orchestrator + Critic + architecture |
| Hassan Mohamed | Database layer |
| Marthi Srivatsav | Schema retrieval (RAG) |
| Abdulqoyum Ahmed | Vector store + embeddings |
| Asad Ali | SQL Generator + Validator + Summariser + prompts |
| Mehdi Boussoura | FastAPI + Streamlit |
| Aneesh Bhojwani | Tests, README, slide deck |

## Documents

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — system design and path to production
- [`docs/decisions/`](docs/decisions/) — architecture decision records (ADRs)

## Licence

MIT
