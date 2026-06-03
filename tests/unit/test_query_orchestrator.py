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


def test_orchestrator_resolves_follow_up_with_previous_successful_question() -> None:
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
    assert "Previous successful question: What were total sales by product category?" in (
        second_response["resolved_question"]
    )
    assert "Follow-up question: What about profit?" in second_response["resolved_question"]
    assert retriever.questions[-1] == second_response["resolved_question"]
    assert generator.prompts[-1].count("Previous successful question") == 1


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
