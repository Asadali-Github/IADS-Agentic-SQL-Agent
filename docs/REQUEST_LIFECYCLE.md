# Request lifecycle

End-to-end trace of a single user question: from Streamlit click, through
the backend pipeline, and back to the rendered answer. Owners in brackets.

## Step-by-step

```
┌─────────────────────────────────────────────────────────────────────────┐
│ FRONTEND  (Streamlit — Mehdi)                                           │
├─────────────────────────────────────────────────────────────────────────┤
│  1. User types: "Top 5 products by revenue in the UK last quarter"      │
│  2. Streamlit POSTs to http://api:8000/query  with {"question": "..."}  │
└──────────────────────────────────┬──────────────────────────────────────┘
                                   │ HTTP POST
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ BACKEND API  (FastAPI — Mehdi)                                          │
├─────────────────────────────────────────────────────────────────────────┤
│  3. routes.py /query endpoint receives the request                      │
│  4. Validates payload with api/schemas.QueryRequest (Pydantic)          │
│  5. Calls orchestrator.run(question)                                    │
└──────────────────────────────────┬──────────────────────────────────────┘
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ ORCHESTRATOR  (Omar)                                                    │
├─────────────────────────────────────────────────────────────────────────┤
│  6. Planner.plan(question)        → Plan                                │
│       (Hasan)                       — "data question, scope = sales"    │
│                                                                         │
│  7. SchemaRetriever.retrieve(question) → RetrievedSchema                │
│       (Zayad)                       — top-k tables from vector store    │
│                                                                         │
│  8. FewShotBank.get_examples(question) → [FewShotExample, ...]          │
│       (Zayad)                       — 2 similar past queries            │
│                                                                         │
│  9. SchemaObfuscator.obfuscate(schema) → (ObfuscatedSchema, AliasMap)   │
│       (Asad / Abdul Qayyum)         — real names → Table_A, Column_B    │
│                                                                         │
│ 10. ModelRouter.pick_model(question, plan) → model_id                   │
│       (Omar)                        — small or large tier               │
│                                                                         │
│ 11. SQLGenerator.generate(...)    → CandidateSQL                        │
│       (Hasan)                       — LLM call to OCI GenAI             │
│                                                                         │
│ 12. SchemaObfuscator.deobfuscate(sql, alias_map) → real_sql             │
│                                                                         │
│ 13. SQLValidator.validate(real_sql, schema) → ValidationResult          │
│       (Omar)                        — sqlglot static checks             │
│                                                                         │
│ 14. SafeExecutor.execute(real_sql) → ExecutionResult                    │
│       (Abdul Qayyum)                — read-only user, timeout, row cap  │
│       ↓                                                                 │
│       Autonomous DB                                                     │
│                                                                         │
│ 15. If rows == 0 AND VECTOR_FALLBACK_ENABLED:                           │
│       RowFallback.find_similar_rows(...) → approximate rows             │
│       (Zayad)                                                           │
│                                                                         │
│ 16. Critic.review(...)            → CritiqueResult (accept, confidence) │
│       (Omar)                                                            │
│       │                                                                 │
│       ├─ retry (≤ AGENT_MAX_RETRIES) → back to step 11 with feedback    │
│       │                                                                 │
│       └─ accept                                                         │
│                                                                         │
│ 17. Summariser.summarise(...)     → AnswerSummary                       │
│       (Asad)                        — answer + explanation              │
└──────────────────────────────────┬──────────────────────────────────────┘
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ BACKEND API  (Mehdi)                                                    │
├─────────────────────────────────────────────────────────────────────────┤
│ 18. routes.py wraps AnswerSummary in QueryResponse and returns JSON     │
└──────────────────────────────────┬──────────────────────────────────────┘
                                   │ HTTP 200
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ FRONTEND  (Mehdi)                                                       │
├─────────────────────────────────────────────────────────────────────────┤
│ 19. Streamlit renders:                                                  │
│       - Direct answer (one sentence)                                    │
│       - Confidence badge (green / yellow if < threshold)                │
│       - Result table                                                    │
│       - "How did the AI calculate this?" expander:                      │
│           - SQL (syntax-highlighted)                                    │
│           - Plain-English explanation                                   │
│           - Tables used + why                                           │
│       - Approximate-match notice (if RowFallback was used)              │
└─────────────────────────────────────────────────────────────────────────┘
```

## Error paths

At every numbered step, an exception can short-circuit the flow.
`core/exceptions.py` defines the exception hierarchy; `api/routes.py`
catches and maps each to a friendly Streamlit response.

| Where it fails | Exception | UI shows |
|---|---|---|
| Step 6 (planner refuses)        | `OutOfScopeQuestion`     | "I understood your question, but our current system doesn't track X..." |
| Step 7 (no relevant schema)     | `NoRelevantSchema`       | "I don't see data about Y in this database. Try asking about Z instead." |
| Step 13 (validation failed)     | `InvalidSQL`             | Internal retry. If exceeds max retries: "I couldn't generate confident SQL." |
| Step 14 (DB error)              | `DatabaseExecutionError` | If `DEMO_FALLBACK_ENABLED` → cached result. Else: friendly fallback. |
| Step 14 (timeout)               | `QueryTimeout`           | "Your question needed more time than I have available." |
| Step 16 (low confidence)        | n/a (still returns)      | Yellow warning banner above the answer. |

## Observability

Each numbered step emits a structured log line with a shared trace ID.
The orchestrator stamps the trace ID at step 6; every downstream call
propagates it. Logs are queryable by trace ID to debug a single request
end-to-end.

(See `observability/README.md` for the planned OpenTelemetry rollout.)
