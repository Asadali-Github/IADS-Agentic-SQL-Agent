"""Shared pytest fixtures + import-path setup.

Owner: Team (path setup seeded by Asad for the evaluation/summariser tests).

Makes both `sql_agent` (under src/) and the top-level `evaluation` package
importable when running `pytest` from the repo root.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
for p in (_ROOT, _ROOT / "src"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from sql_agent.core.models import ExecutionResult, GoldenQuery, RetrievedSchema  # noqa: E402


@pytest.fixture
def golden_count() -> GoldenQuery:
    """A simple easy-tier golden question with a scalar answer."""
    return GoldenQuery(
        id="t001",
        question="How many customers are there?",
        difficulty="easy",
        tags=["count"],
        expected_sql="SELECT COUNT(*) FROM customers",
        expected_rows=[[42]],
        expected_tables=["customers"],
    )


@pytest.fixture
def exec_scalar() -> ExecutionResult:
    return ExecutionResult(columns=["n"], rows=[[42]], row_count=1, success=True)


@pytest.fixture
def schema_customers() -> RetrievedSchema:
    return RetrievedSchema(tables=["customers"], columns={"customers": ["customer_id", "full_name"]})


class FakeLLM:
    """Deterministic LLM stand-in: returns canned JSON for each prompt type."""

    def __init__(self, answer: str = "There are 42 customers.",
                 bullets: list[str] | None = None) -> None:
        self.answer = answer
        self.bullets = bullets or ["We counted every customer record."]
        self.calls: list[str] = []

    def complete(self, prompt: str, *, model: str | None = None) -> str:
        self.calls.append(prompt)
        import json
        if "one sentence that answers" in prompt:
            return json.dumps({"answer": self.answer})
        return json.dumps({"explanation": self.bullets})


@pytest.fixture
def fake_llm() -> FakeLLM:
    return FakeLLM()
