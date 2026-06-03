#!/usr/bin/env python3
"""End-to-end demo: natural-language question -> business answer.

Runs the full pipeline (RAG retrieve -> SQL -> execute -> summarise) on the real
product_sales data, fully offline. With OCI/Oracle configured it uses the live
generator and database automatically.

    python scripts/demo_pipeline.py
    python scripts/demo_pipeline.py "which regions made the most profit?"
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "src"))

from app.pipeline import answer_question  # noqa: E402

DEFAULT_QUESTIONS = [
    "How many orders are in the dataset?",
    "What is the total revenue by region?",
    "What are the top 5 products by total revenue?",
    "What is the profit margin percentage by region?",
    "What was the monthly revenue in 2024?",
]


def show(question: str) -> None:
    r = answer_question(question)
    print("=" * 74)
    print(f"Q: {question}")
    print(f"   provider={r['provider']}  confidence={r['confidence']}  "
          f"approx={r['approximate_match']}  latency={r['latency_ms']}ms")
    if r.get("retrieved_doc_ids"):
        print(f"   RAG context: {r['retrieved_doc_ids']}")
    if r.get("clarification"):
        print(f"    NEEDS CLARIFICATION: {r['clarification']}")
    if not r["sql"]:
        return
    print(f"\nANSWER: {r['answer']}")
    if r["insights"]:
        print("INSIGHTS:")
        for i in r["insights"]:
            print(f"  * {i}")
    print("EXPLANATION:")
    for b in r["explanation_bullets"]:
        print(f"  - {b}")
    if r["chart"]:
        c = r["chart"]
        print(f"CHART: {c['type']} (x={c.get('x')}, y={c.get('y')})")
    print(f"SQL: {r['sql']}")
    print(f"ROWS ({len(r['rows'])}): {r['rows'][:3]}{' ...' if len(r['rows']) > 3 else ''}")


def main() -> int:
    questions = [" ".join(sys.argv[1:])] if len(sys.argv) > 1 else DEFAULT_QUESTIONS
    for q in questions:
        show(q)
    print("=" * 74)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
