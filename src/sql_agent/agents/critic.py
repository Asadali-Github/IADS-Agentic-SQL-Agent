"""Critic stage — accept result or retry with feedback. Emits a confidence score.

Owner: Omar
Status: placeholder — implement during the hackathon.

Outputs:
- decision: accept | retry
- feedback: free-text shown to SQLGenerator on retry
- confidence: float in [0, 1] surfaced to the UI

Why the confidence score matters:
  A SQL query can be syntactically valid and execute cleanly, yet still answer
  the wrong question (silent failure). The critic estimates how well the
  result actually matches the user's intent. If confidence < threshold, the
  frontend shows a "double-check this" warning instead of presenting the
  result as definitive.

TODO:
- Public interface:
    review(question, plan, schema, sql, execution_result) -> CritiqueResult
- CritiqueResult fields: decision, feedback, confidence (0.0–1.0)
- Confidence inputs to weigh:
    * Did all WHERE filter values match real values in the data?
    * Did the SQL touch the tables the planner expected?
    * Did the result row count look plausible vs the question (e.g. "top 5"
      should return ≤ 5 rows)?
    * Did the obfuscator's alias map round-trip cleanly?
- Cap retries at AGENT_MAX_RETRIES
- Threshold: CONFIDENCE_WARNING_THRESHOLD (default 0.7) — below this, the
  API response includes a warning flag the UI renders
- Write tests in tests/unit/test_critic.py
"""
