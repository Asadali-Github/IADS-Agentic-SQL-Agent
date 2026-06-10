# Examples

Short, runnable examples of the SQL agent's components.

## Runnable now (no API / database required)

These exercise the summariser, evaluation and safety layers directly against the
Python package — handy while the live pipeline is still being wired up.

```bash
python examples/summariser_example.py    # rows -> plain-English answer + explanation
python examples/benchmark_example.py     # score a mock agent against the golden set
python examples/glossary_example.py      # enrich a query with business synonyms
python examples/pii_example.py           # scrub text, result rows, and logs
```

## Coming with the live pipeline (need the API at http://localhost:8000)

- `01_basic_query.py` — single question, single answer
- `02_with_retries.py` — question that triggers the critic loop
- `03_refused_question.py` — out-of-scope question, agent refuses
- `04_pii_filtered.py` — question whose answer would expose PII
