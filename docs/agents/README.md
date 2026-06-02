# Agents

> Status: scaffold — content to be added during the hackathon.

The pipeline is composed of stages defined in `src/sql_agent/agents/`. Each stage is a small class implementing a single typed contract: input → output.

## Contracts

All inter-agent messages are Pydantic models in [`../../src/sql_agent/core/models.py`](../../src/sql_agent/core/models.py).

```
Question
  → Plan                    (Planner)
  → RetrievedSchema         (SchemaRetriever)
  → CandidateSQL            (SQLGenerator)
  → ValidationResult        (SQLValidator)
  → ExecutionResult         (SafeExecutor)
  → CritiqueResult          (Critic) — loops back to CandidateSQL up to N times
  → AnswerSummary           (Summariser)
```

## Stage reference

(TODO: per-stage description with input/output models and prompt path.)

## Adding a new stage

(TODO.)
