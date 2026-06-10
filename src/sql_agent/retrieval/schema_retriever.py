"""Schema-aware RAG — finds relevant tables for a question.

Owner: Marthi
Status: INTERFACE SPEC. Realized in `app/rag/retriever.py` (RAG over the
schema and KPI descriptions).

TODO:
- Define the public interface here
- Implement the logic:
    1. Embed the question with cohere.embed-english-v3.0
    2. Query Oracle 23ai vector store for nearest schema descriptions
    3. Return top-k tables with their column descriptions
- Write tests in tests/unit/test_schema_retriever.py

See also:
- src/sql_agent/retrieval/row_fallback.py — vector fallback for similar rows
  when the generated SQL yields 0 results.
"""
