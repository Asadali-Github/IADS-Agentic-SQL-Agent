# Evaluation methodology

> Status: scaffold — content to be added during the hackathon.

## Golden query set

Path: `evaluation/datasets/golden_queries.jsonl`

Row schema:

- `id` — stable identifier (e.g. `q001`)
- `question` — natural-language question
- `expected_sql` — canonical SQL answer
- `expected_rows` — small reference result set (or row count)
- `difficulty` — `easy` | `medium` | `hard`
- `tags` — e.g. `["aggregate", "join", "subquery"]`

## Metrics

- **Execution accuracy** — does the generated SQL produce the same rows as the expected SQL?
- **Exact-set match** — are the two result sets identical (order-insensitive)?
- **Partial match** — column overlap, row overlap.
- **Retry rate** — average critic loops per query.
- **Latency p50 / p95** — wall-clock time per query.
- **Token cost** — prompt + completion tokens × OCI price.

## How to run

```bash
make benchmark   # runs against golden set, writes evaluation/results/runs/<timestamp>.json
```

## How to add a query

1. Append a row to `evaluation/datasets/golden_queries.jsonl`.
2. Run `make benchmark` and verify pass/fail.
3. Commit the new row and the updated result.

## Reference benchmarks

See [`RELATED_WORK.md`](RELATED_WORK.md).
