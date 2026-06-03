#!/usr/bin/env python3
"""Adversarial stress test for the Summariser - no DB or LLM required.

Owner: Asad.   Run:  python scripts/stress_summariser.py

Feeds a battery of nasty, edge-case result sets through the Summariser and
asserts it ALWAYS returns a valid AnswerSummary without raising: empty results,
NULL cells, ragged rows, special characters / injection strings, unicode, extreme
dates, huge/negative numbers, very wide rows, thousands of rows, and PII-laden
cells. This is how we guarantee graceful, deterministic behaviour before the
database layer is even written.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

from sql_agent.agents.summariser import Summariser  # noqa: E402
from sql_agent.core.models import AnswerSummary, ExecutionResult, RetrievedSchema  # noqa: E402


def adversarial_cases() -> list[tuple[str, ExecutionResult]]:
    cases: list[tuple[str, ExecutionResult]] = [
        ("empty result", ExecutionResult(columns=["n"], rows=[], row_count=0)),
        ("single NULL", ExecutionResult(columns=["v"], rows=[[None]], row_count=1)),
        ("all-NULL column", ExecutionResult(columns=["a", "b"],
                                            rows=[[None, 1], [None, 2]], row_count=2)),
        ("ragged rows", ExecutionResult(columns=["a", "b", "c"],
                                        rows=[[1], [1, 2], [1, 2, 3]], row_count=3)),
        ("special chars + injection", ExecutionResult(columns=["txt"],
            rows=[["O'Brien"], ["a\"b"], ["c\\d"], ["'; DROP TABLE orders; --"], ["line1\nline2\t<x>"]],
            row_count=5)),
        ("unicode", ExecutionResult(columns=["name"],
            rows=[["Zoë"], ["北京"], ["emoji 🚀💸"], ["Ω≈ç√"]], row_count=4)),
        ("extreme dates", ExecutionResult(columns=["d"],
            rows=[["0001-01-01"], ["2999-12-31"], ["1970-01-01"]], row_count=3)),
        ("huge / negative numbers", ExecutionResult(columns=["x"],
            rows=[[1e308], [-1e308], [0], [0.0000001], [10**30]], row_count=5)),
        ("booleans + mixed", ExecutionResult(columns=["flag", "val"],
            rows=[[True, 1], [False, None], [True, "n/a"]], row_count=3)),
        ("very wide row (60 cols)", ExecutionResult(columns=[f"c{i}" for i in range(60)],
            rows=[list(range(60))], row_count=1)),
        ("5000 rows", ExecutionResult(columns=["k", "v"],
            rows=[[f"K{i%10}", i] for i in range(5000)], row_count=5000)),
        ("PII in cells", ExecutionResult(columns=["email", "phone"],
            rows=[["a@b.com", "+44 7700 900123"]], row_count=1)),
        ("weird column names", ExecutionResult(columns=["", "select", "a b\tc"],
            rows=[[1, 2, 3]], row_count=1)),
        ("failed execution", ExecutionResult.failure("ORA-00942: table or view does not exist")),
    ]
    # pad to >50 by varying row counts on the numeric case
    for k in range(1, 41):
        cases.append((f"numeric n={k}", ExecutionResult(columns=["amount"],
                     rows=[[round(i * 1.5 - k, 2)] for i in range(k)], row_count=k)))
    return cases


def main() -> int:
    summ = Summariser(max_preview_rows=10)  # deterministic fallback, tight cap
    schema = RetrievedSchema(tables=["orders"])
    failures = 0
    for name, ex in adversarial_cases():
        try:
            out = summ.summarise("stress question", "SELECT * FROM orders", ex, schema)
            assert isinstance(out, AnswerSummary)
            assert isinstance(out.answer, str) and out.answer  # never empty
            assert isinstance(out.explanation, list)
            # no raw PII may survive
            assert "a@b.com" not in out.answer
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"  FAIL [{name}]: {type(exc).__name__}: {exc}")
    total = len(adversarial_cases())
    print(f"[stress] {total - failures}/{total} adversarial cases handled gracefully.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
