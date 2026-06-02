"""Run a simple RAG-to-SQL-prompt pipeline with placeholder documents."""

from __future__ import annotations

import json
import sys

from app.agents.query_orchestrator import QueryOrchestrator


def main() -> None:
    sample_question = "What were total sales by product category?"
    user_question = " ".join(sys.argv[1:]).strip() or sample_question

    orchestrator = QueryOrchestrator()
    response = orchestrator.process_question(user_question)

    print("\n=== Original Question ===")
    print(response["original_question"])

    print("\n=== Retrieved Documents ===")
    print(json.dumps(response["retrieved_documents"], indent=2))

    print("\n=== SQL Generation Prompt ===")
    print(response["sql_generation_prompt"])

    print("\n=== Generated SQL ===")
    print(json.dumps(response["generated_sql"], indent=2))

    print("\n=== Pipeline Stage ===")
    print(response["pipeline_stage"])


if __name__ == "__main__":
    main()
