# ADR-004: Semantic evaluation over SQL string matching

**Status:** Accepted
**Date:** 2026-06-03
**Deciders:** Asad (evaluation owner), Team 4

## Context

We need a benchmark that tells us, honestly and hourly, whether the agent is
getting better. The naive way to score a generated query is to string-compare it
to a reference SQL. That breaks constantly for reasons that have nothing to do
with correctness:

- a renamed alias (`SUM(o.total_gbp) AS revenue` vs `AS total`)
- reflowed whitespace or different casing
- commutative reordering (`a = b` vs `b = a`, reordered `AND`s)
- harmless dialect differences

Worse, a *static* reference result set (`expected_rows`) goes stale the moment the
schema or seed data changes — and during this hackathon the database is built in
parallel with the evaluation harness, so for a while we cannot execute at all.

## Decision

Score on **meaning, not text**, using three layers (in `evaluation/metrics.py`):

1. **Execution accuracy (headline).** Run both queries; compare result sets.
   Comparison is multiset-based and order-insensitive by default, order-sensitive
   when the golden row sets `order_matters`. Cells are normalised first (ints vs
   floats, float rounding to 4 dp, trimmed strings) so cosmetic differences don't
   cause false failures.
2. **AST match (`sql_ast_match`).** Parse both queries with `sqlglot`, strip
   column aliases, lower-case identifiers, standardise formatting, and sort the
   operands of commutative operators. Logically equivalent queries reduce to the
   same canonical string. This is robust to schema/format churn and is the *only*
   correctness signal available before the database can be executed against.
3. **Partial credit (`partial_match`, `sql_structural_similarity`).** Row recall
   and a tables/functions/clauses fingerprint, for triaging near-misses and
   showing progress between hourly runs instead of a binary pass/fail.

We also report retry rate, latency p50/p95, and token cost per request, plus
per-tier (easy/medium/hard) execution accuracy.

The golden set (`evaluation/datasets/golden_queries.jsonl`, ≥20 questions across
tiers) is the source of truth; the few-shot example bank is kept strictly
disjoint from it. A schema-driven synthetic generator
(`scripts/generate_synthetic_queries.py`) provides an additional edge-case stress
set in the same format.

## Consequences

**Positive:**

- The benchmark survives alias/format/dialect changes and schema migrations.
- We can measure SQL correctness (via AST) before the DB is even seeded.
- Partial-match and per-tier signals make tuning a feedback loop, not a coin flip.
- The harness is decoupled from the generator (injected agent), so it was fully
  built and tested against a `MockOrchestrator` before the real pipeline existed.

**Negative / limits:**

- AST canonicalisation is best-effort: deeply different-but-equivalent rewrites
  (e.g. a join expressed as a correlated subquery) may not canonicalise to the
  same tree. Execution accuracy remains the arbiter when the DB is available.
- `expected_rows` for the golden set must be recaptured once the real schema is
  seeded (they are illustrative against the provisional schema until then).

## References

Metric definitions follow the text-to-SQL literature (Spider, BIRD); see
[`../RELATED_WORK.md`](../RELATED_WORK.md) and [`../EVALUATION.md`](../EVALUATION.md).
