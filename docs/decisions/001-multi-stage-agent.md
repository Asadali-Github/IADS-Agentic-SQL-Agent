# ADR-001: Multi-stage agent over single-shot prompt

**Status:** Accepted
**Date:** 2026-06-02
**Deciders:** Team 4

## Context

We need to translate natural-language questions into executable SQL against a structured database. The simplest approach is a single LLM call: stuff the schema and the question into one prompt, take the output, run it.

This works for trivial cases but breaks down quickly:
- The LLM hallucinates column names that don't exist
- For wide schemas, the prompt becomes too long, hurting accuracy and cost
- There's no way to recover from a syntactically wrong query
- The result can't be validated against the question
- The user gets a black box: either it works or it doesn't, with no introspection

## Decision

Build a **multi-stage agent pipeline** with five specialised stages: Planner → Schema Retriever → SQL Generator → SQL Validator → Safe Executor → Critic → Summariser.

Each stage has:
- A single responsibility
- A typed input and output (Pydantic models)
- The ability to fail explicitly with a typed error

The Critic stage can loop back to the Generator with feedback, capped at 3 retries.

## Consequences

**Positive:**
- Failures localise — we know which stage broke
- Each stage can be tested in isolation
- Retries are driven by real errors, not heuristic
- The user sees a transparent trace (question → retrieved schema → SQL → result → summary)
- The architecture directly matches the "agentic" framing of the hackathon brief

**Negative:**
- More moving parts than a single prompt
- Latency: 4–6 LLM calls per query worst case (vs 1)
- More code to maintain

**Mitigations:**
- Cache schema retrieval across questions
- Parallelise where possible (Validator is fast, runs while Executor prepares connection)
- Cap retries strictly
