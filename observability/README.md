# Observability

How we see what the agent is doing: structured logs, the privacy gate on those
logs, per-request cost accounting, and the benchmark metrics that quantify
quality. The production tracing/metrics stack (OTel, Prometheus, Grafana) is
designed below but not yet wired — this README marks the line between what runs
today and what is planned.

## What exists today

### Structured logging

The system logs through `structlog`. Every stage emits structured events rather
than free-text lines, so logs are queryable (by `question_id`, `stage`,
`latency_ms`, ...).

### PII redaction on logs (privacy gate)

Logs are a common PII leak path: a stray `logger.info("user %s", email)` writes
cleartext personal data to disk. `safety/pii_filter.py` closes this with a
logging filter:

```python
from sql_agent.safety.pii_filter import install_log_redaction

install_log_redaction()   # attach once at startup (root logger + handlers)
```

`PIIRedactingLogFilter` scrubs each record's message and args **before** they are
written — emails/phones/cards/etc. become `[EMAIL]`, `[PHONE]`, ... while plain
numbers (revenue, counts) are left intact. This is the *inbound* half of a
bi-directional gate; `scrub_summary()` is the *outbound* half (toward the UI).

### Cost accounting

`llm/token_counter.py` counts prompt/completion tokens and prices them against
the OCI Generative AI rate card (`PRICING`). A `TokenCounter` accumulates across
the calls of one request and exposes:

- `total_tokens`, `total_cost_usd`, `as_metric()`
- cost-aware guardrails: `budget_usd` / `max_calls`, `over_budget`,
  `would_exceed()`, and `check()` raising `BudgetExceeded` — so a runaway retry
  loop backs off instead of inflating the bill.

### Quality metrics (the benchmark)

`evaluation/` is the quality-observability surface. `make benchmark` writes a
timestamped `BenchmarkResult` to `evaluation/results/runs/<run_id>.json`
containing, per run:

| Metric | Meaning |
|---|---|
| `execution_accuracy` | rows match the reference (headline) |
| `ast_match` | logic-level SQL equivalence (schema-change robust) |
| `exact_set_match` / `partial_match` | set equality / row recall |
| `retry_rate` | fraction needing a correction loop |
| `latency_p50_ms` / `latency_p95_ms` | median / tail latency |
| `token_cost_per_request_usd` | mean USD per request (+ run total) |

`notebooks/03_prompt_iteration.ipynb` reads these run files and plots the
accuracy/latency/cost curve over time.

## Planned production stack (not yet implemented)

This directory will hold the collector/scrape/dashboard config:

```
observability/
├── otel/         # OpenTelemetry collector config (trace ids across every stage)
├── prometheus/   # scrape config + alert rules
└── grafana/      # dashboard JSON
```

- **OpenTelemetry tracing** — one trace per `/query`, a span per stage
  (planner → retriever → generator → validator → executor → critic → summariser),
  with `question_id` and model id as attributes.
- **Prometheus metrics** — request count, latency p50/p95/p99, retry rate,
  success rate, and token cost per query (the `TokenCounter` numbers above,
  exported as counters/histograms).
- **Grafana dashboard** — accuracy and cost trends fed from the benchmark runs
  plus live request metrics.
- **Error aggregation** — Sentry (or similar) for exception grouping.

See the "Observability" section of [`../docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md)
for how this fits the wider production path.
