# Repository structure

A map of the repo: what each directory is for, what belongs in it, and what doesn't. Read this before adding a new file — it'll save a debate later.

For *what the system does*, see [`ARCHITECTURE.md`](ARCHITECTURE.md). For *how we measure it*, see [`EVALUATION.md`](EVALUATION.md).

## Top-level layout

```
IADS-Agentic-SQL-Agent/
├── src/sql_agent/      Core Python package (the system itself)
├── frontend/           Streamlit UI
├── prompts/            Versioned prompt templates (Markdown)
├── evaluation/         Benchmark harness + golden query set + results
├── tests/              Unit + integration tests
├── scripts/            One-off operational scripts (seed DB, embed schema, run benchmark)
├── notebooks/          Exploration and prompt iteration
├── docs/               Architecture, ADRs, evaluation methodology, related work
├── data/               Local datasets — raw, processed, external (gitignored content)
├── deploy/             Deployment configuration and runbooks
├── observability/      OTel / Prometheus / Grafana config
├── examples/           Runnable usage examples
└── .github/            CI workflows, issue + PR templates
```

## `src/sql_agent/` — the package

Organised by **layer**, not by feature. Each module has a single responsibility and a typed contract.

| Module | Responsibility | Depends on |
|---|---|---|
| `core/` | Domain models (Pydantic), exceptions, logging. The shared vocabulary. | nothing internal |
| `config/` | Typed settings via `pydantic-settings`. Reads `.env`. | `core/` |
| `llm/` | OCI Generative AI client wrapper, prompt loader, token counter. | `core/`, `config/` |
| `retrieval/` | Embeddings, vector store, schema retriever. The RAG layer. | `core/`, `config/`, `llm/` |
| `database/` | Connection pool, safe executor, schema introspector. | `core/`, `config/` |
| `safety/` | SQL guard rails, PII filter. | `core/` |
| `agents/` | The five pipeline stages + orchestrator. | `core/`, `llm/`, `retrieval/`, `database/`, `safety/` |
| `api/` | FastAPI app, routes, request/response schemas. | `core/`, `agents/` |

**Dependency rule:** the table is ordered top-down. A module may import from modules above it, never below. The graph is acyclic.

## `prompts/`

One file per agent stage. Plain Markdown so prompts are reviewable in diffs and editable without touching Python.

```
prompts/
├── planner.md           Decide if the question is a data question
├── sql_generation.md    Convert question + schema → SQL
├── sql_correction.md    Generate corrected SQL given prior error
├── critic.md            Judge whether the result answers the question
└── summariser.md        Convert SQL result rows → natural-language answer
```

Prompts are loaded at runtime by `src/sql_agent/llm/prompts.py`. Never inline prompts in Python.

## `evaluation/`

Separate from `tests/` on purpose. Tests check that code works; evaluation checks that the *system* gives correct answers.

```
evaluation/
├── benchmark.py         Run agent against golden set, compute metrics
├── metrics.py           Execution accuracy, exact-set match, partial match
├── datasets/
│   ├── golden_queries.jsonl   Canonical question / SQL / expected-rows triples
│   └── demo_queries.jsonl     Subset rehearsed for the live demo
└── results/runs/        Timestamped JSON, one per benchmark run
```

See [`EVALUATION.md`](EVALUATION.md) for the row schema and metric definitions.

## `tests/`

```
tests/
├── conftest.py          Shared fixtures
├── unit/                Fast, isolated, no network/DB
└── integration/         End-to-end against a real (or testcontainer) DB
```

Unit tests run in CI on every push. Integration tests run nightly or on-demand.

## `scripts/`

Operational scripts, not library code. Each is runnable as `python scripts/<name>.py` or via the Makefile target:

| Script | Make target | Purpose |
|---|---|---|
| `seed_database.py` | `make seed-db` | Seed Autonomous DB with the demo dataset |
| `embed_schema.py` | `make embed-schema` | Embed schema descriptions into the vector store |
| `run_benchmark.py` | `make benchmark` | Execute the benchmark harness |

## `notebooks/`

Numbered in dependency order. Notebooks are for exploration; promote anything reusable into `src/`.

```
01_explore_dataset.ipynb     Profile the seed data
02_test_oci_genai.ipynb      Verify OCI credentials and model availability
03_prompt_iteration.ipynb    Iterate on prompts before promoting them to prompts/
```

## `docs/`

```
docs/
├── ARCHITECTURE.md       System design + path to production
├── STRUCTURE.md          This file
├── EVALUATION.md         Benchmark methodology, golden set schema, metrics
├── RELATED_WORK.md       Reference benchmarks + methods we draw from
├── agents/README.md      Inter-agent contracts (Pydantic message types)
└── decisions/            Architecture Decision Records (ADRs)
    ├── 001-multi-stage-agent.md
    ├── 002-schema-retrieval.md
    └── 003-safety-guardrails.md
```

New ADRs go in `decisions/` numbered sequentially. Never edit a merged ADR — supersede it with a new one.

## `data/`

```
data/
├── raw/         Source data, never modified
├── processed/   Cleaned / transformed outputs of the pipeline
└── external/    Third-party reference datasets
```

Content is gitignored. Place a `.gitkeep` and document provenance in each subdir's README before adding files larger than 1 MB.

## `deploy/`

Deployment configuration for OCI and any auxiliary targets. Includes runbooks, environment variable manifests, and any Terraform / Kubernetes config.

## `observability/`

OpenTelemetry collector config, Prometheus scrape rules, Grafana dashboards. See `ARCHITECTURE.md#observability`.

## `examples/`

Self-contained runnable examples for the README. Each example imports from `sql_agent` and hits the local API.

## Root-level files

| File | Purpose |
|---|---|
| `pyproject.toml` | Canonical dependency + tooling config (ruff, mypy, pytest) |
| `requirements.txt` | Runtime deps, unpinned (mirror of `pyproject.toml`) |
| `requirements.lock` | Runtime deps, pinned — install with `pip install -r requirements.lock` |
| `requirements-dev.txt` | Runtime + dev deps, unpinned |
| `requirements-dev.lock` | Runtime + dev deps, pinned |
| `Makefile` | Task runner — `make help` lists targets |
| `Dockerfile` | Image build |
| `docker-compose.yml` | Local stack: API + UI + (optional) local DB |
| `.dockerignore` | Build-context exclusions |
| `.env.example` | Template for required OCI / DB credentials |
| `.pre-commit-config.yaml` | Lint + format on commit |
| `.editorconfig` | Cross-editor formatting baseline |
| `CONTRIBUTING.md` | How to contribute, run tests, open a PR |
| `SECURITY.md` | Threat model + mitigations |
| `CHANGELOG.md` | Notable changes per release |
| `LICENSE` | MIT |

## Where to put a new file

| You want to add… | Put it in… |
|---|---|
| Domain model used by multiple modules | `src/sql_agent/core/models.py` |
| New agent stage | `src/sql_agent/agents/<stage>.py` + entry in orchestrator |
| New prompt | `prompts/<name>.md` |
| Configuration knob | `src/sql_agent/config/settings.py` + `.env.example` |
| Operational one-off | `scripts/<name>.py` + Makefile target |
| Exploratory analysis | `notebooks/NN_<name>.ipynb` |
| New eval query | append to `evaluation/datasets/golden_queries.jsonl` |
| Architectural choice | new ADR in `docs/decisions/` |
| Test for a module | mirror the path in `tests/unit/` |

## What does not go in this repo

- Secrets, credentials, OCI keys — use `.env` (gitignored).
- Trained model weights or large embeddings — store in OCI Object Storage, reference by URI.
- Generated artifacts (build output, `.pyc`, `__pycache__`, coverage reports) — gitignored.
- Personal scratch work — keep it on a feature branch.
