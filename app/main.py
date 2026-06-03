"""Run a simple RAG-to-SQL-prompt pipeline with placeholder documents."""

from __future__ import annotations

import json
import sys

from app.agents.query_orchestrator import QueryOrchestrator


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "--chat":
        run_chat()
        return

    sample_question = "What were total sales by product category?"
    user_question = " ".join(sys.argv[1:]).strip() or sample_question

    orchestrator = QueryOrchestrator()
    response = orchestrator.process_question(user_question)
    print_response(response)


def run_chat() -> None:
    """Run a tiny CLI chat loop that keeps in-process conversation memory."""
    orchestrator = QueryOrchestrator()
    print("Oracle SQL Agent chat. Type exit to stop.")
    while True:
        user_question = input("\nQuestion: ").strip()
        if user_question.lower() in {"exit", "quit"}:
            return
        if not user_question:
            continue

        response = orchestrator.process_question(user_question)
        print_response(response)


def print_response(response: dict) -> None:
    """Print the pipeline response in a readable debug format."""
    print("\n=== Original Question ===")
    print(response["original_question"])

    print("\n=== Resolved Question ===")
    print(response["resolved_question"])

    print("\n=== Answer ===")
    print(response["answer"]["answer"])

    print("\n=== Support Assessment ===")
    print(json.dumps(response["support_assessment"], indent=2))

    print("\n=== Retrieved Documents ===")
    print(json.dumps(response["retrieved_documents"], indent=2))

    print("\n=== SQL Generation Prompt ===")
    print(response["sql_generation_prompt"])

    print("\n=== Generated SQL ===")
    print(json.dumps(response["generated_sql"], indent=2))

    print("\n=== SQL Validation ===")
    print(json.dumps(response["sql_validation"], indent=2))

    print("\n=== Query Results ===")
    print(json.dumps(response["query_results"], indent=2, default=str))

    print("\n=== Answer Details ===")
    print(json.dumps(response["answer"], indent=2, default=str))

    print("\n=== Pipeline Stage ===")
    print(response["pipeline_stage"])


if __name__ == "__main__":
    main()
