"""Run agent against test set, compute accuracy metrics.

Owner: Aneesh + Asad
Status: placeholder — implement during the hackathon.

TODO:
- Define the public interface here
- Implement the logic
- Write tests in tests/unit/test_benchmark.py
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from app.agents.query_orchestrator import QueryOrchestrator
from evaluation import metrics


def run_benchmark(
    questions: Iterable[str],
    orchestrator: QueryOrchestrator | None = None,
    max_retries: int = 1,
) -> list[dict[str, Any]]:
    """Run questions through the pipeline and retry when shared reflection flags an issue."""
    agent = orchestrator or QueryOrchestrator()
    results: list[dict[str, Any]] = []
    total_retries = 0

    for question in questions:
        retry_count = 0
        result = agent.process_question(question)
        reflection = metrics.reflect(result)

        while not reflection["ok"] and retry_count < max_retries:
            retry_count += 1
            total_retries += 1
            print(f"Retrying question due to {reflection['issue']}: {question}")
            result = agent.process_question(question)
            reflection = metrics.reflect(result)

        results.append(
            {
                "question": question,
                "result": result,
                "reflection": reflection,
                "retry_count": retry_count,
            }
        )

    print(f"Benchmark complete. Questions: {len(results)}. Retries: {total_retries}.")
    return results
