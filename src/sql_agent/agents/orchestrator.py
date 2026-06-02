"""Orchestrator — wires stages, manages retry loop, routes models.

Owner: Omar
Status: placeholder — implement during the hackathon.

Responsibilities:
- Run the pipeline: Planner → SchemaRetriever → (Obfuscator) → SQLGenerator
  → SQLValidator → SafeExecutor → Critic → (loop ≤ N) → Summariser
- Route each request to the right model tier (see llm/model_router.py)
- Surface confidence scores from the critic to the API response

TODO:
- Define the public interface here
- Implement the logic:
    1. Run Planner
    2. Call model_router.classify_complexity() → pick model id
    3. Retrieve schema (and optionally obfuscate)
    4. Pull few-shot examples (few_shot_bank.get_few_shot_examples)
    5. Generate → validate → execute → critique
    6. If empty result AND VECTOR_FALLBACK_ENABLED: call row_fallback
    7. Retry up to AGENT_MAX_RETRIES with critic feedback
    8. Summarise and return
- Write tests in tests/unit/test_orchestrator.py

See also:
- src/sql_agent/llm/model_router.py — cost/speed routing
- src/sql_agent/safety/schema_obfuscator.py — privacy masking
- src/sql_agent/retrieval/few_shot_bank.py — dynamic prompt examples
"""
