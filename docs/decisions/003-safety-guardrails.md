# ADR-003: Safety guardrails at the database layer

**Status:** Accepted
**Date:** 2026-06-02
**Deciders:** Team 4

## Context

A text-to-SQL system is a security risk. The LLM could be tricked (prompt injection) or simply confused into generating destructive SQL: `DROP TABLE`, `DELETE`, `UPDATE`, or unbounded scans that lock the database.

We need safety guarantees that hold even when every other layer fails.

## Decision

Defence in depth, with the strongest guarantee at the database layer.

**Layer 1 — Prompt:** Instruct the LLM to produce read-only queries only.
**Layer 2 — Static SQL validation:** Parse the generated SQL with `sqlglot`. Reject if it contains DDL (`CREATE`, `DROP`, `ALTER`), DML (`INSERT`, `UPDATE`, `DELETE`), or system commands (`GRANT`, `REVOKE`).
**Layer 3 — Complexity caps:** Reject queries with > 5 joins or no `WHERE` / `LIMIT` clause when the table is large.
**Layer 4 — Read-only DB user:** The DB connection uses a user with `SELECT`-only privileges. Even if every other layer is bypassed, the database refuses non-`SELECT` statements.
**Layer 5 — Query timeout:** 15-second statement timeout. Prevents accidental cartesian products from hanging the system.
**Layer 6 — Row cap:** Max 500 rows returned to the user. Prevents accidental "select all from billion-row table".

## Consequences

**Positive:**
- A bug in the LLM, prompt, or validator cannot harm the database
- Demo is safe to run on real data
- We can credibly claim the system is production-relevant, not a toy

**Negative:**
- Layer 4 (read-only user) means we can't support legitimate write operations later without architectural changes
- Complexity caps may reject some legitimate complex queries
- Row cap may truncate results the user actually wants

**Mitigations:**
- For future write support, add a separate orchestrator with a different (still scoped) DB user and human-in-the-loop approval
- When truncating to 500 rows, show the user that the result is truncated and offer a "show me a sample" alternative

## Why this matters for the demo

Most hackathon text-to-SQL demos run as a database admin. They work, but they're fundamentally unsafe. We can say in the pitch:

> "Every other layer is best-effort. The database layer is the guarantee. Even if our LLM goes rogue, your data is safe."

That's a hiring-manager-friendly sentence.
