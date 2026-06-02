"""Summariser stage — result → natural-language summary + SQL explanation.

Owner: Asad
Status: placeholder — implement during the hackathon.

Two outputs:
  1. answer — one-sentence direct answer to the user
  2. explanation — non-technical "how did the AI calculate this?" breakdown
     used by the frontend's expandable "SQL Explainer" panel

TODO:
- Public interface:
    summarise(question, sql, schema_used, rows) -> AnswerSummary
- AnswerSummary fields:
    answer: str            # one-sentence
    explanation: str       # 2–4 bullets, business language, no SQL jargon
    sql: str               # echoed for the UI
    tables_used: list[str] # for the explainer expander
- Use prompts/summariser.md for the answer
- Use prompts/sql_explanation.md for the explanation
- Strip PII via safety/pii_filter.py before returning
- Write tests in tests/unit/test_summariser.py

See also:
- prompts/sql_explanation.md
- frontend/streamlit_app.py — renders the SQL Explainer expander
"""
