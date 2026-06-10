"""SQL validator stage - static safety and syntax checks.

Status: INTERFACE SPEC (see docs/decisions/003-safety-guardrails.md).

This is the target stage contract. Validation is *realized* in the shipped
runtime by:

- `app/sql/validator.py` - application-level checks before execution.
- `sql_agent/safety/sql_guard.py` - parses with `sqlglot` and enforces a
  single read-only SELECT (no DDL/DML, no multiple statements, no
  comment-smuggling), the last line of defence before the safe executor.

Contract: `validate(sql) -> {ok: bool, reason: str|None}`. A failed check
either feeds the generator's self-correction loop or surfaces a safe refusal.
"""
