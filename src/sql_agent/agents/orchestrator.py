"""Orchestrator - wires stages, manages the run, routes models.

Status: INTERFACE SPEC (see docs/decisions/001-multi-stage-agent.md).

The composition described here is *realized* in the shipped runtime by
`app/pipeline.py` (class `FullPipeline.run`), with request wiring in
`app/agents/query_orchestrator.py`.

Target stage order:
    Planner -> SchemaRetriever -> (Obfuscator) -> SQLGenerator
      -> SQLValidator -> SafeExecutor -> Critic -> (loop <= N) -> Summariser

What is LIVE on the hot path today (app/pipeline.py):
    1. Multi-turn / follow-up resolution + glossary term enrichment
    2. RAG schema retrieval (app/rag/retriever.py)
    3. SQL generation via Oracle Select AI (app/sql/generator.py)
    4. Static validation + read-only guard (app/sql/validator.py, safety/sql_guard.py)
    5. Safe execution (sql_agent/database/safe_executor.py)
    6. If the result is empty -> VECTOR ROW-FALLBACK to the nearest real rows
       (sql_agent/retrieval/row_fallback.py) - the brief's "similar results"
    7. Deterministic summary + insights + chart spec + confidence (agents/summariser.py)

Documented extension points (NOT on the single-pass hot path - future work):
    - schema obfuscation for privacy (safety/schema_obfuscator.py)
    - cost/latency model-tier routing (llm/model_router.py)
    - a multi-retry critic loop driven by an LLM critic (see critic.py); today
      confidence is computed deterministically and surfaced inline.

Contract: `run(question, session_id=None) -> AgentRunOutput`.
"""
