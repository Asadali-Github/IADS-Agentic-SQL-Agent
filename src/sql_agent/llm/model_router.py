"""Multi-model router — pick a cheaper/faster model for simple queries.

Owner: Omar
Status: scaffold — implement during the hackathon.

Why this exists:
  Not every question needs the heaviest model. "How many items are in stock?"
  is a one-table COUNT. "What's the year-over-year growth of category X in
  region Y broken down by quarter?" is a multi-join with window functions.
  Sending both to the same expensive model wastes tokens and adds latency.

Routing rules (initial heuristic):
  - SMALL model: single-table queries, no joins, no aggregates beyond COUNT/SUM
  - LARGE model: joins, subqueries, window functions, math, multi-step reasoning
  - Fallback: LARGE if the planner flags the question as complex

Wiring:
  Called by `orchestrator.py` before invoking `sql_generator.py`. The chosen
  model id is threaded through the LLM client.

TODO:
- Public interface:
    classify_complexity(question: str, plan: Plan) -> ModelTier
    pick_model(tier: ModelTier) -> str   # returns OCI model id
- ModelTier = Literal["small", "large"]
- Initial classifier: rule-based (keyword + sqlglot AST of the plan if available)
- Stretch goal: a tiny LLM call (small model) that returns "small | large"
- Config: ROUTER_ENABLED, ROUTER_SMALL_MODEL_ID, ROUTER_LARGE_MODEL_ID
- Emit a metric: count requests per tier (for the demo slide)
- Write tests in tests/unit/test_model_router.py

Pitch line:
  "We route ~60% of queries to a cheaper model, cutting average token cost
  by Z% with no accuracy loss on the small-tier queries." (Numbers come from
  the benchmark — see EVALUATION.md.)
"""
