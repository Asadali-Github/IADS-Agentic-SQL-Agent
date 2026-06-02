"""Vector-based row fallback — retrieve similar rows when SQL returns 0.

Owner: Marthi + Abdulqoyum
Status: scaffold — implement during the hackathon.

Why this exists:
  When the agent generates valid SQL but the exact filter yields zero rows
  (e.g. "show me sales for product X" where product X has a typo or is
  unstocked), we don't want to surface "No results." Instead, embed the
  filter values, search the vector store for nearest matches in the relevant
  column, and return those rows with a clear "approximate match" label.

Wiring:
  `agents/critic.py` triggers this path when ExecutionResult.row_count == 0
  AND ValidationResult.valid is True. The fallback rows are returned alongside
  the original SQL so the summariser can be transparent: "No exact match for
  'X'. Closest results: Y, Z."

TODO:
- Public interface:
    find_similar_rows(
        question: str,
        sql: str,
        empty_result_context: ExecutionResult,
        top_k: int = 5,
    ) -> RowFallbackResult
- Identify the filter column(s) from the SQL WHERE clause via sqlglot
- Embed the filter value with cohere.embed-english-v3.0
- Query the Oracle 23ai vector store for nearest neighbours
- Re-run a relaxed SQL with the matched values
- Return rows + similarity scores + a "this is an approximate match" flag
- Add RowFallbackResult to core/models.py
- Write tests in tests/unit/test_row_fallback.py

Brief reference:
  The hackathon brief states: "if exact data doesn't exist, make vector-based
  decisions to yield similar rows." This module is that requirement.
"""
