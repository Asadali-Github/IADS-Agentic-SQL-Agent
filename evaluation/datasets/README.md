# Evaluation datasets

Owner: Asad. See [`../../docs/EVALUATION.md`](../../docs/EVALUATION.md) for the
full methodology.

## Files

- `golden_queries.jsonl` — the curated benchmark. 21 question / SQL / expected-row
  triples across easy/medium/hard tiers. The single source of truth for accuracy.
- `example_queries.jsonl` — 10 few-shot examples for the retriever's example bank.
  **Disjoint** from the golden set on purpose: the few-shot retriever must never
  be shown a benchmark answer.
- `synthetic_queries.jsonl` — auto-generated stress set
  (`scripts/generate_synthetic_queries.py`, `make synth-queries`). Template +
  edge-case queries (NULLs, empty constraints, extreme dates, FK joins) derived
  from `db/schema_descriptions.yaml`. A breadth/robustness net, not the headline.
- `demo_queries.jsonl` — hand-picked, well-tested queries for the live demo.

## Golden row schema

```json
{
  "id": "q001",
  "question": "Which product category generated the most revenue last quarter?",
  "expected_sql": "SELECT ... FETCH FIRST 5 ROWS ONLY",
  "expected_rows": [["Electronics", 4200000]],
  "expected_tables": ["orders", "products"],
  "difficulty": "medium",
  "order_matters": true,
  "tags": ["aggregate", "filter", "order-by"]
}
```

`order_matters` makes scoring order-sensitive (top-N / ranking). `expected_rows`
must be **recaptured against the seeded Oracle DB** — they are illustrative until
then (current files target the provisional `customers`/`orders` schema).

## Example / synthetic row schema

```json
{"id": "ex01", "question": "...", "sql": "...", "tags": ["join"], "difficulty": "medium"}
```

## Adding a query

Append a row to `golden_queries.jsonl`, capture `expected_rows` on the seeded DB,
run `make benchmark`, commit the row + the result JSON. Keep `example_queries.jsonl`
disjoint from the golden set.
