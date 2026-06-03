# Changelog

All notable changes to this project will be documented in this file.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning: [SemVer](https://semver.org/).

## [Unreleased]

### Added

- Initial scaffold for the IADS Agentic SQL Agent (Team 4, IADS Hackathon 2026).

#### Evaluation & datasets (Asad)

- `core/models.py`: seeded the cross-stage Pydantic contracts the eval/summariser
  slices need — `AnswerSummary`, `BenchmarkResult`, `Metric`, `CaseResult`,
  `GoldenQuery`, plus `Question`/`CandidateSQL`/`ExecutionResult`/`RetrievedSchema`
  (accepts both `text` and `question` keys).
- `evaluation/metrics.py`: execution accuracy (numeric/whitespace-normalised,
  order-aware), exact-set match, partial match, retry rate, latency p50/p95,
  token cost, and per-tier accuracy.
- `evaluation/metrics.py`: **semantic SQL comparison** — `sql_ast_match` (sqlglot
  AST canonicalisation, robust to alias/format/case/commutativity) and
  `sql_structural_similarity`; surfaced as the `ast_match` run metric.
- `evaluation/benchmark.py`: end-to-end harness — loads the golden set, runs an
  injected agent, scores, writes timestamped JSON to `results/runs/`, prints a
  pass/fail report. Includes `make_stub_agent`, a realistic `make_mock_agent`,
  and a `MockOrchestrator` drop-in for the real pipeline.
- `evaluation/datasets/golden_queries.jsonl`: 21 curated questions (7 easy /
  8 medium / 6 hard) spanning joins, aggregates, window functions, dates, CTEs.
- `evaluation/datasets/example_queries.jsonl`: 10 few-shot examples, disjoint
  from the golden set.
- `evaluation/datasets/synthetic_queries.jsonl` + `scripts/generate_synthetic_queries.py`:
  schema-driven stress-set generator (templates + edge cases: NULLs, empty
  constraints, extreme dates, FK joins), emitted in the golden schema.

#### Summariser & prompts (Asad)

- `agents/summariser.py`: rows → one-sentence answer + 2–4 plain-English bullets
  + tables-used (sqlglot). Works with or without an LLM (deterministic fallback).
- **Hybrid summarisation**: deterministic per-column profiling (shape, dtypes,
  min/max/sum/mean, distinct, top values) injected into the prompt instead of
  raw rows; configurable `max_preview_rows` context cap to prevent token bloat.
- `prompts/summariser.md`, `prompts/sql_explanation.md`, and `llm/prompts.py`
  (prompt loader with `${var}` substitution).

#### Cost & safety (Asad)

- `llm/token_counter.py`: token estimation + OCI GenAI pricing, accumulation,
  and **cost-aware guardrails** (`budget_usd`/`max_calls`, `BudgetExceeded`).
- `safety/pii_filter.py`: regex baseline (emails/phones/cards/SSNs/IPs) that
  never eats plain numbers; pluggable NER detectors with a **timeout-guarded
  fail-safe** to the regex floor; `strict` preset; dual-gate `scrub_rows`
  (inbound) + `scrub_summary` (outbound) + `PIIRedactingLogFilter` log gate.
- `safety/ner_presidio.py`: optional Microsoft Presidio adapter (lazy import,
  graceful degradation).

#### Retrieval glossary (Asad, consumed by Zayad)

- `db/glossary.yaml` (hierarchical) + `retrieval/glossary.py`: `GlossaryResolver`
  (exact → contains → fuzzy → optional embedder) with `expand_query_terms()` and
  `enrich_query_terms()` to widen vector-search recall.
- `db/schema_descriptions.yaml` + `scripts/build_schema_descriptions.py`
  (DDL → YAML sync, with `--from-db` Oracle `ALL_*_COMMENTS` scraping).

#### Tooling, docs & tests

- Scripts: `scripts/run_benchmark.py`, `scripts/preprocess_raw_data.py`,
  `scripts/demo_summariser.py`, `scripts/stress_summariser.py`; Makefile targets
  `benchmark`, `synth-queries`, `demo-summariser`, `stress-summariser`.
- Notebooks: `01_explore_dataset.ipynb` (dataset/schema profiling),
  `03_prompt_iteration.ipynb` (prompt-vs-score curve).
- Docs: `docs/EVALUATION.md`, `docs/RELATED_WORK.md`.
- Tests: 88 unit tests across metrics, benchmark, summariser (incl. adversarial),
  pii_filter, token_counter, glossary, ner_presidio.

#### End-to-end integration (Asad, integrator pass)

- **`app/pipeline.py`** (new): composes the whole flow — glossary enrich -> RAG
  retrieve -> SQL (live OCI / curated offline) -> read-only validate -> execute
  -> summarise -> QueryResponse-shaped result. Connects the `app/` runtime and the
  `src/sql_agent/` library without rewriting either.
- **`evaluation/local_db.py`** (new): offline read-only DuckDB executor over
  `db/seed/product_sales.csv` (Oracle-SQL in, transpiled) — fills the missing
  execution stage so the pipeline runs without OCI.
- Wired the FastAPI `/query` endpoint to the pipeline (stub kept as a defensive
  fallback) and `scripts/run_benchmark.py` `_real_agent` to drive the pipeline.
- `scripts/demo_pipeline.py` (+ `make demo-pipeline`): runnable end-to-end demo on
  the real data, offline. Improved the deterministic answer to name the leading
  result ("East had the highest revenue ($45.0M)...").
- `docs/PROJECT_REVIEW.md`: full architecture + status + how-to-run review.

#### Answer enrichment (Asad) — "explain, insight, chart, ask"

- `AnswerSummary` extended (additive) with `insights`, `chart` (`ChartSpec`),
  `clarification`, and a populated `confidence`.
- **Business insights**: deterministic, computed-in-code statements (top
  contributor + % share, concentration, top-3 share, time-series trend / peak) —
  no hallucinated numbers.
- **Auto chart suggestion**: `suggest_chart()` picks bar / line / pie / none from
  the result shape; `examples/chart_example.py` renders real PNGs.
- **Confidence + clarification**: glossary-based ambiguity detection asks a
  clarifying question for genuinely ambiguous terms (e.g. "margin" -> total
  profit vs profit margin) and lowers confidence accordingly.
- **Query suggestions**: `evaluation/datasets/suggested_questions.json` +
  `sql_agent.suggestions.suggest_questions()` (glossary-ranked by partial input)
  for the UI's "try one of these" buttons.

### Changed

- **Datasets migrated to the real `product_sales` dataset** (200k rows, USD).
  `schema_descriptions.yaml`, `glossary.yaml`, `golden_queries.jsonl` (22, with
  **real captured `expected_rows`**), `example_queries.jsonl` and the synthetic
  set were rebuilt against it. `scripts/preprocess_raw_data.py` cleans the raw
  CSV -> `db/seed/product_sales.csv`; `scripts/capture_golden_rows.py` captures
  expected rows via DuckDB. Drafted `db/ddl/01_create_tables.sql` for
  `product_sales` (co-owned with Abdul).
- Fixed a truncated `[tool.pytest.ini_options]` section in `pyproject.toml`.

### Notes

- Golden `expected_rows` are illustrative against the provisional `customers`/
  `orders` schema and must be recaptured on the seeded Oracle DB (see
  `docs/EVALUATION.md`).
