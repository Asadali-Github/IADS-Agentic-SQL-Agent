"""Dynamic few-shot injector — vector-searches similar past queries for prompting.

Owner: Abdulqoyum + Marthi
Status: EXTENSION POINT. Dynamic vector-selected few-shots; the running
prompt builder uses curated RAG context today.

Why this exists:
  A fixed system prompt can't anticipate every question shape. Instead, keep
  a bank of high-quality (question, SQL) examples in the vector store. When
  a new question arrives, retrieve the 2-3 most similar examples and inject
  them into the SQL-generation prompt. This dramatically improves accuracy
  on complex JOINs and window functions without making the system prompt
  longer for every request.

Wiring:
  Called by `sql_generator.py` between schema retrieval and prompt assembly.

Data source:
  `evaluation/datasets/example_queries.jsonl` — same schema as the golden
  set, but curated for *teaching the model* (varied SQL patterns) rather
  than for benchmarking.

TODO:
- Public interface:
    get_few_shot_examples(question: str, k: int = 2) -> list[FewShotExample]
- Embed the question with cohere.embed-english-v3.0 (reuse vector_store)
- Index lives in the same Oracle 23ai vector store, under a separate namespace
- Each FewShotExample carries: nl_question, sql, brief_rationale
- Cache embeddings of the example bank — only re-embed when the file changes
- Write tests in tests/unit/test_few_shot_bank.py

See also:
- src/sql_agent/retrieval/vector_store.py — the underlying store
- evaluation/datasets/example_queries.jsonl — the example bank
"""
