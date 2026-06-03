"""Unit tests for conversation memory and unsupported-question guardrails."""

from __future__ import annotations

from typing import Any

from app.agents.query_orchestrator import QueryOrchestrator
from app.sql.executor import SafeSQLExecutor

REVENUE_DOC = {
    "id": "kpi_revenue",
    "title": "Revenue KPI Definition",
    "type": "kpi_definition",
    "content": "Revenue means total sales. Use SUM(Revenue) by Category.",
}

PROFIT_DOC = {
    "id": "kpi_profit",
    "title": "Profit KPI Definition",
    "type": "kpi_definition",
    "content": "Profit means total profit. Use SUM(Profit) by Category.",
}


class FakeRetriever:
    def __init__(self, documents: list[dict]) -> None:
        self.documents = documents
        self.questions: list[str] = []

    def retrieve(self, user_question: str) -> list[dict]:
        self.questions.append(user_question)
        return self.documents


class FakeGenerator:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> dict[str, Any]:
        self.prompts.append(prompt)
        return {
            "sql": 'SELECT "CATEGORY", SUM("REVENUE") AS total_sales FROM product_sales',
            "clarification_question": None,
            "reasoning": "fake",
            "provider": "fake",
            "error": None,
        }


class FailingGenerator:
    def generate(self, prompt: str) -> dict[str, Any]:
        raise AssertionError("Generator should not be called for unsupported questions.")


class FakeExecutor:
    def execute(self, sql_validation: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": "success",
            "reason": "fake execution",
            "sql": sql_validation.get("safe_sql"),
            "columns": ["CATEGORY", "TOTAL_SALES"],
            "rows": [{"CATEGORY": "Electronics", "TOTAL_SALES": 10}],
            "row_count": 1,
            "row_limit": 100,
            "error": None,
        }


class FakeSummariser:
    def summarise(
        self,
        user_question: str,
        generated_sql: dict[str, Any],
        query_results: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "answer": f"Answered: {user_question}",
            "provider": "fake",
            "prompt_row_count": 1,
            "error": None,
        }


def test_orchestrator_rewrites_follow_up_into_standalone_question() -> None:
    """A genuine follow-up is rewritten into a standalone question and the
    previous SQL is NEVER injected into the next turn (no answering-from-memory)."""
    retriever = FakeRetriever([REVENUE_DOC, PROFIT_DOC])
    generator = FakeGenerator()
    orchestrator = QueryOrchestrator(
        retriever=retriever,
        sql_generator=generator,
        sql_executor=FakeExecutor(),
        summariser=FakeSummariser(),
    )

    first_response = orchestrator.process_question("What were total sales by product category?")
    second_response = orchestrator.process_question("What about profit?")

    assert first_response["pipeline_stage"] == "sql_executed_successfully"
    assert second_response["pipeline_stage"] == "sql_executed_successfully"

    resolved = second_response["resolved_question"]
    # Rewritten into a real, standalone question about profit by product category.
    assert "profit" in resolved.lower()
    assert "product category" in resolved.lower()
    # The previous question's SQL must not leak into the resolved question...
    assert "Previous SQL" not in resolved
    assert "Previous successful question" not in resolved
    assert "SELECT" not in resolved.upper()
    # ...nor into the prompt handed to the SQL generator.
    assert "Previous SQL" not in generator.prompts[-1]
    assert "Previous successful question" not in generator.prompts[-1]
    # Retrieval ran on the rewritten standalone question.
    assert retriever.questions[-1] == resolved


def test_orchestrator_does_not_hijack_standalone_question() -> None:
    """A self-contained question after a prior turn must be answered fresh, not
    rewritten from the previous turn — this is the core bug being fixed."""
    retriever = FakeRetriever([REVENUE_DOC, PROFIT_DOC])
    generator = FakeGenerator()
    orchestrator = QueryOrchestrator(
        retriever=retriever,
        sql_generator=generator,
        sql_executor=FakeExecutor(),
        summariser=FakeSummariser(),
    )

    orchestrator.process_question("What were total sales by product category?")
    standalone = orchestrator.process_question("Show total profit by region")

    # Returned untouched — not merged with the previous "by product category" turn.
    assert standalone["resolved_question"] == "Show total profit by region"
    assert "product category" not in standalone["resolved_question"].lower()
    assert "Previous SQL" not in generator.prompts[-1]
    assert retriever.questions[-1] == "Show total profit by region"


def test_orchestrator_skips_sql_generation_for_unsupported_question() -> None:
    orchestrator = QueryOrchestrator(
        retriever=FakeRetriever([]),
        sql_generator=FailingGenerator(),
        sql_executor=SafeSQLExecutor(connection_factory=lambda: None),
        summariser=FakeSummariser(),
    )

    response = orchestrator.process_question("Who won the football match yesterday?")

    assert response["pipeline_stage"] == "unsupported_question_no_sql_generated"
    assert response["generated_sql"]["sql"] is None
    assert response["sql_generation_prompt"] is None
    assert response["query_results"]["status"] == "skipped"
    assert response["answer"]["provider"] == "local_no_answer"
    assert "do not have enough retrieved schema" in response["answer"]["answer"]
