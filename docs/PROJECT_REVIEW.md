# Project review — IADS Agentic Text-to-SQL Agent (Team 4)

A deep, end-to-end review of the repository as it stands after everyone has
pushed, plus the integration work done to make it run as one product. Written by
Asad while wearing the integrator hat.

## 1. What this project is

A natural-language → SQL → answer system over a 200,000-row US retail sales
dataset (`product_sales`). A user asks a question in English; the system retrieves
the relevant schema/business context, generates safe SQL, runs it, and returns a
plain-English answer with an explanation, business insights, a recommended chart,
and a confidence signal.

## 2. The two code roots (important)

The repo grew **two** parallel trees. Understanding this is the key to the whole
codebase:

| Tree | What it is | State |
|------|-----------|-------|
| `app/` | The team's **runtime** pipeline: LangChain RAG retrieval → prompt builder → Oracle Select AI SQL generation | Implemented, runs |
| `src/sql_agent/` | The original **library** scaffold: typed contracts, summariser, evaluation, safety, glossary, plus many agent stubs | Mix of implemented + stubs |

`app/` is what actually executes today, but on its own it **stops at generating
SQL** — it never executed the query, summarised the result, or scored anything.
All of that lived, unconnected, in `src/sql_agent/`. The two halves did not talk
to each other.

### The bridge

`app/pipeline.py` (new) is the integration layer that connects them into one
flow, reusing every component without rewriting it:

```
question
  │
  ├─▶ glossary.enrich_query_terms()         (src/sql_agent/retrieval — Asad)
  │      widen recall: "turnover" → revenue, profit, product_sales.revenue
  ├─▶ LangChainRAGRetriever.retrieve()      (app/rag — team)
  │      pull schema + KPI + example docs from data/placeholder_docs.json
  ├─▶ SQLPromptBuilder.build_prompt()       (app/sql — team)
  ├─▶ SQL generation                        (app/sql Oracle Select AI — live;
  │      curated offline cache when no OCI creds)
  ├─▶ validate_sql()                        (app validator + sqlglot single-SELECT guard)
  ├─▶ execute                               (Oracle when configured; LocalDB/DuckDB offline)
  ├─▶ Summariser.summarise()                (src/sql_agent/agents — Asad:
  │      answer + explanation + insights + chart + confidence + clarification)
  └─▶ QueryResponse-shaped dict             (src/sql_agent/api/schemas — Mehdi)
```

The same flow runs **fully offline** on `db/seed/product_sales.csv` (via DuckDB)
for the curated demo questions, and switches to **live OCI + Oracle** automatically
when `SELECT_AI_PROFILE` / `ADB_*` environment variables are present. Offline →
live is a configuration change, not a code change.

## 3. Component status (honest census)

**Working end-to-end:** RAG retrieval, prompt building, offline SQL (curated) /
live SQL (OCI), read-only validation, execution (DuckDB offline / Oracle live),
summarisation (answer, explanation, insights, chart, confidence, clarification),
PII redaction, the benchmark harness + metrics, the golden set with real rows,
the glossary, and the FastAPI `/query` endpoint (now wired to the pipeline).

**Still stubbed in `src/sql_agent/` (owned by others, not on the critical path
now that `app/` is the runtime):** `agents/orchestrator.py`, `agents/critic.py`,
`agents/planner.py`, `agents/sql_generator.py`, `agents/sql_validator.py`,
`database/connection.py`, `database/safe_executor.py`,
`database/schema_introspector.py`, `llm/client.py`, `config/settings.py`,
`core/logging.py`, `retrieval/schema_retriever.py`, `retrieval/vector_store.py`,
`retrieval/embeddings.py`, `safety/sql_guard.py`. These are the original
multi-agent design; the team converged on the simpler `app/` pipeline instead.

## 4. Integration gaps closed in this pass

1. **No execution stage** → added `evaluation/local_db.py` (read-only DuckDB over
   the seed) as the offline executor; Oracle remains the live path.
2. **No summarisation in the runtime** → the pipeline now calls the summariser, so
   results come back as language + insights + a chart spec, not raw SQL.
3. **Two disconnected trees** → `app/pipeline.py` composes both.
4. **Offline demo impossible (generation needs OCI)** → a curated offline SQL
   cache (built from the golden + example sets) lets the whole thing run with no
   cloud credentials for the demo questions.
5. **API returned a stub** → `/query` now calls the real pipeline (the stub is kept
   as a defensive fallback so the API still boots if optional deps are missing).
6. **Benchmark had no real agent** → `scripts/run_benchmark.py` now drives the
   pipeline, executing and scoring each golden question end-to-end.

## 5. How to run it

```bash
# One-time: clean the raw CSV into the seed the offline path reads
python scripts/preprocess_raw_data.py            # data/raw -> db/seed/product_sales.csv

# End-to-end demo (offline, no OCI needed)
python scripts/demo_pipeline.py
python scripts/demo_pipeline.py "which regions made the most profit?"

# Benchmark the pipeline against the golden set
python scripts/run_benchmark.py                  # writes evaluation/results/runs/<ts>.json

# API + UI (needs: pip install fastapi uvicorn streamlit)
make run-api      # FastAPI /query now backed by the pipeline
make run-ui       # Streamlit calls the API

# Going live: set SELECT_AI_PROFILE + ADB_USER/PASSWORD/DSN in .env, then the
# pipeline uses Oracle Select AI for generation and Oracle for execution.
```

## 6. A note on the offline benchmark number

Run offline, the benchmark reports ~100% because the offline SQL source returns
the curated golden SQL for each golden question — so it measures the
**execution + scoring path**, not generation quality. The honest headline
accuracy number comes from running with `SELECT_AI_PROFILE` set, where the live
Oracle Select AI generator produces SQL the harness then scores against the real
`expected_rows`. The plumbing to produce that number is complete and tested; it
needs only the OCI credentials.

## 7. Recommendations / remaining work for the team

- **Capture the live accuracy number** (Hasan + Asad): run `make benchmark` with
  OCI configured; that is the slide headline.
- **Schema introspection** (Abdul): `database/schema_introspector.py` is still a
  stub; `scripts/build_schema_descriptions.py --from-db` is ready to pull Oracle
  `ALL_*_COMMENTS` once it exists.
- **Pick one tree** post-hackathon: either retire the `src/sql_agent/` agent stubs
  or fold the `app/` pipeline into them, so newcomers aren't confused by two roots.
- **UI enrichment** (Mehdi): the pipeline already returns `insights` and a `chart`
  spec; surfacing them as a chart + an insight panel is a quick, high-impact win
  (see `examples/chart_example.py` for rendering).
- **Confidence calibration** (Omar): the summariser's confidence is a simple
  heuristic today; tie it to the critic/retry signal when that lands.

## 8. Test status

105 unit tests pass across metrics, benchmark, summariser (incl. adversarial),
pii_filter, token_counter, glossary, ner_presidio, suggestions, and the new
end-to-end pipeline tests.
