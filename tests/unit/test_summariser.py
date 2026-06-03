"""Unit tests for result summarisation."""

from __future__ import annotations

from app.agents.summariser import SelectAIResultSummariser


class FakeCursor:
    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.statement: str | None = None
        self.parameters: dict | None = None

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def execute(self, statement: str, parameters: dict) -> None:
        self.statement = statement
        self.parameters = parameters

    def fetchone(self) -> tuple[str]:
        return (self.answer,)


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self.cursor_instance = cursor

    def __enter__(self) -> FakeConnection:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def cursor(self) -> FakeCursor:
        return self.cursor_instance


def test_summarise_uses_select_ai_narrate() -> None:
    cursor = FakeCursor("Electronics generated the highest total sales.")
    connection = FakeConnection(cursor)
    summariser = SelectAIResultSummariser(
        profile_name="SALES_AGENT",
        connection_factory=lambda: connection,
    )

    result = summariser.summarise(
        user_question="What were total sales by product category?",
        generated_sql={"sql": "SELECT ..."},
        query_results={
            "status": "success",
            "columns": ["PRODUCT_CATEGORY", "TOTAL_SALES"],
            "rows": [{"PRODUCT_CATEGORY": "Electronics", "TOTAL_SALES": 57485698.06}],
            "row_count": 1,
        },
    )

    assert result["answer"] == "Electronics generated the highest total sales."
    assert result["provider"] == "oracle_select_ai"
    assert "DBMS_CLOUD_AI.GENERATE" in cursor.statement
    assert "narrate" in cursor.statement
    assert cursor.parameters["profile_name"] == "SALES_AGENT"
    assert "What were total sales by product category?" in cursor.parameters["prompt"]


def test_summarise_falls_back_when_profile_is_missing() -> None:
    summariser = SelectAIResultSummariser(profile_name="", connection_factory=lambda: None)

    result = summariser.summarise(
        user_question="What were total sales by product category?",
        generated_sql={"sql": "SELECT ..."},
        query_results={
            "status": "success",
            "rows": [
                {"PRODUCT_CATEGORY": "Electronics", "TOTAL_SALES": 57485698.06},
                {"PRODUCT_CATEGORY": "Home & Furniture", "TOTAL_SALES": 47674426.96},
            ],
        },
    )

    assert result["provider"] == "local"
    assert "top row is PRODUCT_CATEGORY: Electronics" in result["answer"]
    assert result["error"] == "SELECT_AI_PROFILE is not set."


def test_summarise_accepts_fallback_success_results() -> None:
    summariser = SelectAIResultSummariser(profile_name="", connection_factory=lambda: None)

    result = summariser.summarise(
        user_question="What were total sales by product category?",
        generated_sql={"sql": "SELECT ..."},
        query_results={
            "status": "fallback_success",
            "rows": [
                {"PRODUCT_CATEGORY": "Electronics", "TOTAL_SALES": 57485698.06},
                {"PRODUCT_CATEGORY": "Home & Furniture", "TOTAL_SALES": 47674426.96},
            ],
        },
    )

    assert result["provider"] == "local"
    assert "top row is PRODUCT_CATEGORY: Electronics" in result["answer"]
