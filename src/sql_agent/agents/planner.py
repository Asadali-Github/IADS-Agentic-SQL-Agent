"""Planner stage - decides SQL / clarify / refuse.

Status: INTERFACE SPEC (see docs/decisions/001-multi-stage-agent.md).

This is the target stage contract. The decision is *realized* in the shipped
runtime, split across:

- `app/pipeline.py` - multi-turn follow-up resolution (`_resolve_followup`)
  and glossary-driven ambiguity detection that emits a clarification prompt
  instead of guessing (e.g. "margin = profit total or profit %?").
- `sql_agent/retrieval/glossary.py` - maps user phrasing to schema targets
  and flags ambiguous business terms.
- `app/sql/validator.py` + `sql_agent/safety/sql_guard.py` - the *refuse*
  path: anything that is not a single read-only SELECT is rejected.

Contract: `plan(question, history) -> {action: sql|clarify|refuse, ...}`.
"""
