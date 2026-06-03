"""Vector store interface and Oracle 23ai implementation.

Owner: Abdulqoyum
Status: EXTENSION POINT. Oracle 23ai Vector Search backend. Offline retrieval
uses an in-memory lexical index (`app/rag/embeddings.py`) and `row_fallback`
uses lexical similarity -- both swappable for this in production.

Stores **two indexed namespaces**:
  1. Schema descriptions — used by schema_retriever.py
  2. Example (question, SQL) pairs — used by few_shot_bank.py for dynamic
     few-shot prompt injection

TODO:
- Public interface:
    upsert(namespace: str, items: list[VectorItem]) -> None
    search(namespace: str, query_embedding: list[float], k: int) -> list[Hit]
- Use Oracle 23ai native VECTOR datatype
- Cosine similarity for scoring
- Write tests in tests/unit/test_vector_store.py

See also:
- src/sql_agent/retrieval/schema_retriever.py
- src/sql_agent/retrieval/few_shot_bank.py
- src/sql_agent/retrieval/row_fallback.py
"""
