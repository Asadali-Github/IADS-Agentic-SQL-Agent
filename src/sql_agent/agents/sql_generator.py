"""SQL generator stage - NL + retrieved schema -> SQL.

Status: INTERFACE SPEC (see docs/decisions/001-multi-stage-agent.md).

This is the target stage contract. Generation is *realized* in the shipped
runtime by:

- `app/sql/generator.py` - Oracle Select AI backend
  (`DBMS_CLOUD_AI.GENERATE` with action `showsql`), running on OCI Autonomous
  Database and OCI Generative AI (Cohere) under the hood.
- `app/sql/prompt_builder.py` - assembles the prompt from the RAG-retrieved
  schema/KPI context (`app/rag/retriever.py`).

Contract: `generate(question, retrieved_schema, prior_error=None) -> SQL`.
The `prior_error` argument is the self-correction hook the orchestrator uses
on a failed attempt.
"""
