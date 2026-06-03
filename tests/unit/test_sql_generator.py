"""Unit tests for the Oracle Select AI SQL generator."""

from __future__ import annotations

from app.sql.generator import OracleSelectAISQLGenerator


class FakeCursor:
    def __init__(self, generated_sql: str) -> None:
        self.generated_sql = generated_sql
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
        return (self.generated_sql,)


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self.cursor_instance = cursor

    def __enter__(self) -> FakeConnection:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def cursor(self) -> FakeCursor:
        return self.cursor_instance


def test_generate_uses_dbms_cloud_ai_showsql() -> None:
    cursor = FakeCursor("SELECT Category, SUM(Revenue) AS total_revenue FROM product_sales")
    connection = FakeConnection(cursor)
    generator = OracleSelectAISQLGenerator(
        profile_name="HACKATHON_PROFILE",
        connection_factory=lambda: connection,
    )

    result = generator.generate("What were total sales by product category?")

    assert result["sql"] == "SELECT Category, SUM(Revenue) AS total_revenue FROM product_sales"
    assert result["error"] is None
    assert "DBMS_CLOUD_AI.GENERATE" in cursor.statement
    assert "showsql" in cursor.statement
    assert cursor.parameters == {
        "prompt": "What were total sales by product category?",
        "profile_name": "HACKATHON_PROFILE",
    }


def test_generate_skips_when_profile_is_missing() -> None:
    generator = OracleSelectAISQLGenerator(profile_name="", connection_factory=lambda: None)

    result = generator.generate("Tell me something unsupported")

    assert result["sql"] is None
    assert result["error"] is None
    assert "SELECT_AI_PROFILE" in result["reasoning"]


def test_generate_uses_known_fallback_when_profile_is_missing() -> None:
    generator = OracleSelectAISQLGenerator(profile_name="", connection_factory=lambda: None)

    result = generator.generate("What were total sales by product category?")

    assert result["provider"] == "local_fallback"
    assert result["sql"] is not None
    assert '"ADMIN"."PRODUCT_SALES_DATASET_FINAL"' in result["sql"]
    assert "SELECT_AI_PROFILE is not set" in result["reasoning"]


def test_generate_uses_known_fallback_when_select_ai_is_unavailable() -> None:
    generator = OracleSelectAISQLGenerator(
        profile_name="SALES_AGENT",
        connection_factory=lambda: (_ for _ in ()).throw(RuntimeError("ADB unavailable")),
    )

    result = generator.generate("What were total sales by product category?")

    assert result["provider"] == "local_fallback"
    assert result["sql"] is not None
    assert '"ADMIN"."PRODUCT_SALES_DATASET_FINAL"' in result["sql"]
    assert 'SUM("REVENUE") AS total_sales' in result["sql"]
    assert "ADB unavailable" in result["error"]
