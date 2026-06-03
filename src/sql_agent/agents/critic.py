"""Critic stage - accept result or retry with feedback. Emits a confidence score.

Status: INTERFACE SPEC (see docs/decisions/001-multi-stage-agent.md).

The confidence + clarification behaviour described here is *realized* in the
shipped runtime inline in `app/pipeline.py` and `agents/summariser.py`:
confidence is surfaced to the UI as a badge, and low-confidence / ambiguous
questions raise a clarification prompt instead of presenting a guess as fact.

Why the confidence score matters:
  A SQL query can be syntactically valid and execute cleanly, yet still answer
  the wrong question (silent failure). The critic estimates how well the
  result actually matches the user's intent. If confidence < threshold, the
  frontend shows a "double-check this" warning instead of presenting the
  result as definitive.

Contract:
    review(question, plan, schema, sql, execution_result) -> CritiqueResult
    CritiqueResult fields: decision (accept|retry), feedback, confidence [0,1]

How the shipped confidence is computed (deterministic, no extra LLM call):
    * Did all WHERE filter values match real values in the data? (an
      approximate row-fallback substitution lowers confidence and is flagged)
    * Did the SQL touch the tables the planner/retriever expected?
    * Did the row count look plausible vs the question (e.g. "top 5" <= 5 rows)?
    * Below CONFIDENCE_WARNING_THRESHOLD (default 0.7) the API response carries
      a warning flag the UI renders.

Documented extension: replace the deterministic estimate with an LLM critic
that also drives a bounded retry loop (<= AGENT_MAX_RETRIES) feeding free-text
feedback back into the SQL generator.
"""
