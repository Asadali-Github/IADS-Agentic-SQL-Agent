"""Base agent-stage protocol - the contract every pipeline stage honours.

Status: INTERFACE SPEC (see docs/decisions/001-multi-stage-agent.md).

This package documents the *target* multi-stage agent design. The shipped
runtime composes these stages end-to-end in `app/pipeline.py` (class
`FullPipeline`); the production summariser stage lives in
`agents/summariser.py` and is imported directly by that pipeline.

A stage is any callable that takes the shared run context and returns a typed
result (see `sql_agent/core/models.py`). Keeping the contract here lets the
orchestrator treat Planner / SchemaRetriever / SQLGenerator / SQLValidator /
SafeExecutor / Critic / Summariser uniformly, and lets us swap the offline
composition for the live OCI composition without touching any call site.
"""
