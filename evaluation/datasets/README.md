# Evaluation datasets

> Status: scaffold — populate during the hackathon.

## Files

- `golden_queries.jsonl` — canonical question / SQL / expected-rows triples used by the benchmark.
- `demo_queries.jsonl` — the queries we plan to run live in the demo. Smaller, hand-picked, well-tested.

## Row schema

```json
{
  "id": "q001",
  "question": "Which product category generated the most revenue last quarter in the UK?",
  "expected_sql": "SELECT product_category, SUM(revenue) AS total FROM sales WHERE region = 'UK' AND quarter = '2026-Q1' GROUP BY product_category ORDER BY total DESC FETCH FIRST 5 ROWS ONLY",
  "expected_rows": [["Electronics", 4200000]],
  "difficulty": "medium",
  "tags": ["aggregate", "filter", "order-by"]
}
```

## Adding a query

See [`../../docs/EVALUATION.md`](../../docs/EVALUATION.md).
