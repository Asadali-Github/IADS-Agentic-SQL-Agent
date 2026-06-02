# Ownership & task allocation

Team of 6. Each person owns a vertical slice that plays to their background,
with comparable scope: 1 agent stage or equivalent + supporting infra +
prompts/scripts/tests for their slice.

| Member | Background | Slice |
|---|---|---|
| Omar | AI | Orchestration, critic, model routing |
| Hasan | AI | Planner, SQL generator, prompts |
| Zayad | AI | Retrieval / RAG layer (schema, few-shot, row fallback) |
| Asad | Data Science (MSc) | Summariser, evaluation harness, golden datasets |
| Mehdi | CS (undergrad) | FastAPI service, Streamlit UI, deployment |
| Abdul Qayyum | CS (undergrad) | Database, vector store, safety/obfuscation |

## Why this split

- **AI background → LLM-heavy work**: prompt engineering, agentic loop,
  routing, RAG orchestration. Touches the model the most.
- **Data science → evaluation & data**: golden set curation, benchmark
  metrics, statistical reporting, the summariser (where data is shaped
  back into language).
- **CS undergrads → engineering plumbing**: FastAPI, Streamlit, Docker,
  Oracle DB integration, Oracle 23ai vector store, safety/obfuscation
  string manipulation. High-leverage, well-bounded engineering work.

Every person owns: their code, their tests, their section of
`ARCHITECTURE.md`, and their TODO closure.

---

## Omar — Orchestration & critic (AI)

**Why this slice:** the orchestrator is the conductor of the agentic loop —
needs strong reasoning about state machines and LLM-call contracts. Critic
is the highest-judgement LLM stage.

**Owns:**
- `src/sql_agent/agents/orchestrator.py`
- `src/sql_agent/agents/critic.py`
- `src/sql_agent/llm/model_router.py`
- `prompts/critic.md`
- ADR-001 (multi-stage agent) — already drafted, owns updates
- `tests/unit/test_orchestrator.py`, `tests/unit/test_critic.py`,
  `tests/unit/test_model_router.py`

**Day 1 morning (critical path):** lead the 30-minute alignment on
`core/models.py` — interfaces between every stage. Nothing else can start
until these typed contracts are agreed.

**Day 2:** integrate the retry loop end-to-end. Wire confidence score into
the API response.

**Day 3:** tune retry/confidence thresholds based on Asad's benchmark
numbers.

---

## Hasan — Planning & SQL generation (AI)

**Why this slice:** the two stages where prompt quality dominates output
quality. Needs to iterate fast on prompts using OCI GenAI.

**Owns:**
- `src/sql_agent/agents/planner.py`
- `src/sql_agent/agents/sql_generator.py`
- `src/sql_agent/llm/client.py` (OCI Generative AI wrapper)
- `prompts/planner.md`, `prompts/sql_generation.md`, `prompts/sql_correction.md`
- `tests/unit/test_planner.py`, `tests/unit/test_sql_generator.py`

**Day 1 afternoon:** stand up a minimal client.py → smoke-test OCI GenAI
end-to-end. Once that works, everyone else is unblocked.

**Day 2:** iterate prompts against Asad's golden set. Aim for ≥70% on the
easy tier by end of day.

**Day 3:** add the SQL-correction retry path with Omar's critic feedback.

---

## Zayad — Retrieval / RAG (AI)

**Why this slice:** RAG is the brief's headline requirement. Three retrieval
surfaces (schema, few-shot, row fallback) all flow through the same vector
infrastructure.

**Owns:**
- `src/sql_agent/retrieval/schema_retriever.py`
- `src/sql_agent/retrieval/few_shot_bank.py`
- `src/sql_agent/retrieval/row_fallback.py`
- `src/sql_agent/retrieval/embeddings.py`
- `src/sql_agent/llm/prompts.py` (prompt loader/registry)
- `scripts/embed_schema.py`
- ADR-002 (schema retrieval) — owns updates
- `tests/unit/test_schema_retriever.py`, `test_few_shot_bank.py`,
  `test_row_fallback.py`

**Day 1 afternoon:** define the Embedding interface with Abdul Qayyum so
his vector store and your retriever talk cleanly. Run `embed_schema.py`
against the seed DB.

**Day 2:** add few-shot retrieval (depends on Asad's example_queries.jsonl)
and row fallback (depends on Abdul Qayyum's executor returning empty).

**Day 3:** tune top-k values; document recall numbers for the pitch.

---

## Asad — Summariser, evaluation, data (Data Science)

**Why this slice:** the data science end of the project — evaluation rigour
is the strongest signal to judges, and curating the golden + example sets
is genuine analytical work. The summariser is where rows become language.

**Owns:**
- `src/sql_agent/agents/summariser.py`
- `src/sql_agent/llm/token_counter.py`
- `src/sql_agent/safety/pii_filter.py`
- `prompts/summariser.md`, `prompts/sql_explanation.md`
- `evaluation/benchmark.py`
- `evaluation/metrics.py` (execution accuracy, exact-set match, latency)
- `evaluation/datasets/golden_queries.jsonl` — curate ≥20 questions
- `evaluation/datasets/example_queries.jsonl` — curate ~10 examples for
  few-shot (different from golden set)
- `scripts/run_benchmark.py`
- `notebooks/01_explore_dataset.ipynb` (profile the seed data)
- `notebooks/03_prompt_iteration.ipynb` (track prompt → score curve)
- `docs/EVALUATION.md` — fill in the methodology
- `docs/RELATED_WORK.md` — cite Spider, BIRD, DAIL-SQL
- `tests/unit/test_summariser.py`, `test_metrics.py`, `test_benchmark.py`

**Day 1 afternoon:** draft `golden_queries.jsonl` against the seed DB
schema. Without this, nobody can measure anything.

**Day 2:** run benchmark hourly; share results with Hasan (prompts) and
Omar (retries) so they tune in feedback loop.

**Day 3:** produce the headline number for the slides
("X% execution accuracy on Y queries"). Generate cost/accuracy chart.

---

## Mehdi — API & frontend (CS undergrad)

**Why this slice:** clean, well-bounded engineering work that turns the
backend into a demo-able product. FastAPI + Streamlit are exactly the right
tools for an undergrad CS portfolio.

**Owns:**
- `src/sql_agent/api/main.py`
- `src/sql_agent/api/routes.py`
- `src/sql_agent/api/schemas.py` (HTTP request/response models)
- `frontend/streamlit_app.py` — all four UI surfaces:
    1. Question/answer panel
    2. Confidence badge + warning banner
    3. "How did the AI calculate this?" expander
    4. Friendly error states + approximate-match notice
- `Dockerfile`, `docker-compose.yml` — verify everything boots
- `.github/workflows/ci.yml` — keep green
- `tests/unit/test_api_routes.py`, `tests/integration/test_end_to_end.py`

**Day 1 afternoon:** API skeleton with a single `/query` endpoint that
takes a question and returns a stubbed `AnswerSummary`. This unblocks
Mehdi's Streamlit work AND gives Omar a target to wire the orchestrator into.

**Day 2:** all four UI surfaces working against the real backend.

**Day 3:** polish copy, syntax highlighting, demo rehearsal mode (with
Abdul Qayyum's demo_cache toggle).

---

## Abdul Qayyum — Database, vector store, safety (CS undergrad)

**Why this slice:** Oracle 23ai integration is the most "real engineering"
component — driver setup, connection pooling, SQL execution, vector store
wiring. Schema obfuscation is pure string manipulation. All well-bounded.

**Owns:**
- `src/sql_agent/database/connection.py` (connection pool to Autonomous DB)
- `src/sql_agent/database/safe_executor.py` (timeout, row cap, read-only)
- `src/sql_agent/database/schema_introspector.py` (extract table/col metadata)
- `src/sql_agent/database/demo_cache.py` (fail-safe fallback)
- `src/sql_agent/retrieval/vector_store.py` (Oracle 23ai VECTOR datatype)
- `src/sql_agent/safety/sql_guard.py` (sqlglot static checks: no DDL/DML, joins capped)
- `src/sql_agent/safety/schema_obfuscator.py` (alias map round-trip)
- `scripts/seed_database.py` (load demo data)
- `notebooks/02_test_oci_genai.ipynb` (verify OCI access — Day 1 critical)
- ADR-003 (safety guardrails) — owns updates
- `tests/unit/test_safe_executor.py`, `test_sql_validator.py`,
  `test_vector_store.py`, `test_schema_obfuscator.py`

**Day 1 morning (critical path):** verify OCI access in
`notebooks/02_test_oci_genai.ipynb`. If credentials don't work, nothing
else matters. Then `seed_database.py` so others have data to work against.

**Day 1 afternoon:** `connection.py` + `safe_executor.py` end-to-end. Zayad
and Mehdi need this.

**Day 2:** vector store (with Zayad) + schema obfuscator (with Hasan, since
his generator is the LLM consumer).

**Day 3:** populate `demo_cache.json` from a rehearsal run. This is the
silent demo-saver.

---

## Cross-cutting / shared

- **`src/sql_agent/core/models.py`** — Pydantic contracts between stages.
  Whole team agrees Day 1 morning. Once frozen, changes require team chat.
  Omar arbitrates.
- **`README.md`** — each owner updates the section that references their
  module.
- **`ARCHITECTURE.md`** — each owner fills in the section describing their
  stage.
- **`CHANGELOG.md`** — Asad keeps it updated each evening.
- **Slide deck** — Asad drafts (he has the metrics); Omar reviews;
  Hasan/Zayad add the AI architecture diagrams; Mehdi adds UI screenshots;
  Abdul Qayyum adds the Oracle integration diagram.

## Standup cadence

Every 4 hours during the hackathon. 5 minutes max. Per the protocol in
`CONTRIBUTING.md`. Omar runs it.

## Dependency graph (who blocks whom)

```
Abdul Qayyum (OCI verified, DB seeded)
    │
    ├──▶ Hasan (LLM client smoke test → prompts)
    │       │
    │       └──▶ Omar (orchestrator end-to-end)
    │
    ├──▶ Zayad (schema embed → retriever)
    │       │
    │       └──▶ Asad (benchmark → metrics → slides)
    │
    └──▶ Mehdi (API → Streamlit → demo)
```

Critical path: **Abdul Qayyum** on Day 1 morning. If OCI access breaks, the
project stalls. Everything else parallelises after.
