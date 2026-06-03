# Evaluation methodology

Owner: Asad. This document defines how we measure the agent. It is the contract
behind the headline number on the demo slide, so every metric here is computed by
code in `evaluation/metrics.py` and exercised by `tests/unit/test_metrics.py` —
nothing here is hand-waved.

## The golden query set

`evaluation/datasets/golden_queries.jsonl` is the single most important dataset
in the project: without it nothing can be measured. Each line is one
`GoldenQuery` (see `src/sql_agent/core/models.py`):

| field | meaning |
|-------|---------|
| `id` | stable identifier, e.g. `q001` |
| `question` | the natural-language question |
| `expected_sql` | canonical reference SQL (Oracle dialect) |
| `expected_rows` | the reference result set, as ordered rows |
| `expected_tables` | tables the reference SQL touches |
| `difficulty` | `easy` \| `medium` \| `hard` |
| `order_matters` | `true` when the reference query has a meaningful `ORDER BY` (top-N, ranking) |
| `tags` | SQL patterns exercised, e.g. `["join","window"]` |

The current file holds 22 questions (7 easy / 8 medium / 7 hard) spanning counts,
filters, group-by, date logic, `HAVING`, subqueries and window functions, built
against the real **`product_sales`** dataset (200,000 rows, USD). The
`expected_rows` are **real** — captured by executing each reference query against
the cleaned seed (`db/seed/product_sales.csv`) via `scripts/capture_golden_rows.py`.

## Metrics

All metrics are computed per question and then aggregated across the run.

**Execution accuracy** (headline). Does the generated SQL, when executed, return
the same rows as the reference SQL? Comparison is multiset-based and
order-insensitive by default, becoming order-sensitive when `order_matters` is
set. Cells are normalised first: integers and floats are compared numerically
with rounding to 4 decimals (so `5` == `5.0` and rounding noise from `SUM`/`AVG`
does not cause spurious failures), and strings are trimmed. This is the
pass/fail signal.

**Exact-set match.** Do the two result sets contain the same rows ignoring order
*and* duplicates (set equality)? Slightly more forgiving than execution accuracy
on duplicate handling; useful for diagnosing near-misses.

**Partial match.** What fraction of the expected rows appear in the actual
result (recall over the expected row set, in `[0, 1]`)? Lets us award partial
credit and show progress between hourly runs instead of a binary number.

**Retry rate.** Fraction of questions that needed at least one correction loop.
A proxy for how often the generator gets it wrong on the first attempt.

**Latency p50 / p95.** Median and tail end-to-end wall-clock latency per
question, via linear-interpolated percentiles.

**Token cost per request.** Mean USD cost across calls, priced by
`src/sql_agent/llm/token_counter.py` against the OCI Generative AI rate card.
Reported with the run total so the model-router savings can be quantified.

Per-tier execution accuracy (`execution_accuracy_easy/medium/hard`) is also
emitted for the slide breakdown.

## How to run

```bash
make benchmark                       # real pipeline against the golden set
python scripts/run_benchmark.py --stub        # harness self-check (perfect agent)
python scripts/run_benchmark.py --threshold 0.8   # exit non-zero below 80% pass rate
```

Each run writes a timestamped `BenchmarkResult` to
`evaluation/results/runs/<run_id>.json` and prints a pass/fail report. Runs are
cheap and idempotent — intended to be run hourly during Day 2.

## Capturing expected rows

`expected_rows` are generated reproducibly by `scripts/capture_golden_rows.py`,
which loads `db/seed/product_sales.csv` into DuckDB and executes each query's
Oracle reference SQL (transpiled oracle->duckdb via sqlglot). Aggregates that
aren't exact (`AVG`, margins) are wrapped in `ROUND(..., 2)` in the reference SQL
so the captured rows match Oracle regardless of engine.

To regenerate after editing the golden queries or reseeding:

```bash
python scripts/capture_golden_rows.py     # rewrites golden_queries.jsonl with fresh rows
make benchmark                            # score the agent and commit the result JSON
```

Once Abdul has seeded the same cleaned data into Oracle, the captured rows should
match the live database; differences would themselves be a finding worth flagging.

## How to add a query

Append a `GoldenQuery` line to `golden_queries.jsonl`, capture its
`expected_rows` as above, run `make benchmark`, and commit the row with the
updated result. Keep the example bank (`example_queries.jsonl`) **disjoint** from
the golden set — the few-shot retriever must never be shown a benchmark answer.

## Semantic correctness over string matching

A static reference SQL string breaks the moment someone renames an alias,
reflows whitespace, or the dialect shifts - yet the query still *means* the same
thing. We therefore never score on raw SQL string equality. Two complementary,
schema-change-robust checks back up execution accuracy:

- **`ast_match`** (`metrics.sql_ast_match`). Both the reference and generated SQL
  are parsed to an Abstract Syntax Tree with `sqlglot` and canonicalised:
  column aliases are stripped, identifiers lower-cased, formatting standardised,
  and the operands of commutative operators (`=`, `AND`, `OR`, `+`, `*`) sorted.
  Two queries that are logically equivalent reduce to the same canonical string.
  This is the only correctness signal available when the database cannot be
  executed against (e.g. before the seed data lands), and it is robust to the
  cosmetic differences that defeat string matching.
- **`sql_structural_similarity`** gives partial credit by comparing a structural
  fingerprint (tables, functions, presence of join/where/group/order/having,
  projection arity) - useful for triaging near-misses.

Execution accuracy remains the headline; AST/structure checks make the harness
resilient to schema churn and give signal when execution is impossible.

## The glossary as a feature-engineering layer

In text-to-SQL, the descriptions and synonyms attached to the schema are the
"features": richer business context at retrieval time yields better SQL. Two
artifacts in `db/` carry that context, and a resolver turns it into a live
retrieval signal:

- `schema_descriptions.yaml` - per-column business descriptions plus units,
  timezones, currencies and sample values, embedded by the RAG layer.
- `glossary.yaml` (hierarchical) - canonical business terms with variations and a
  `maps_to` physical target (e.g. revenue / sales / turnover / ARR -> `orders.total_gbp`).
  `retrieval/glossary.py` resolves a user phrase to these terms (exact -> contains
  -> fuzzy -> optional embedder) and exposes `expand_query_terms()`, which appends
  the matched synonyms and targets to the text the retriever embeds - directly
  widening vector-search recall so "what was our turnover?" still retrieves the
  `total_gbp` column it never names.

This is the highest-leverage, lowest-cost accuracy work in the project: every
synonym and description added here compounds through retrieval into the generated
SQL.

## Reference benchmarks

Our metric definitions follow the text-to-SQL literature; see
[`RELATED_WORK.md`](RELATED_WORK.md).
