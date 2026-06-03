"""Unit tests for safe SQL execution."""

from __future__ import annotations

from app.sql.executor import SafeSQLExecutor


class FakeCursor:
    def __init__(self) -> None:
        self.description = [("CATEGORY",), ("TOTAL_SALES",)]
        self.executed_sql: str | None = None
        self.arraysize: int | None = None

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def execute(self, sql: str) -> None:
        self.executed_sql = sql

    def fetchmany(self, row_limit: int) -> list[tuple[str, int]]:
        rows = [
            ("Technology", 1200),
            ("Furniture", 800),
            ("Office Supplies", 500),
        ]
        return rows[:row_limit]


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self.cursor_instance = cursor
        self.call_timeout: int | None = None

    def __enter__(self) -> FakeConnection:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def cursor(self) -> FakeCursor:
        return self.cursor_instance


def test_execute_runs_validated_sql_and_returns_rows() -> None:
    cursor = FakeCursor()
    connection = FakeConnection(cursor)
    executor = SafeSQLExecutor(
        connection_factory=lambda: connection,
        max_rows=2,
        timeout_seconds=7,
    )

    result = executor.execute(
        {
            "is_valid": True,
            "safe_sql": "SELECT category, total_sales FROM product_sales FETCH FIRST 2 ROWS ONLY",
            "reason": "SQL validation passed.",
            "max_rows": 2,
        }
    )

    assert result["status"] == "success"
    assert result["columns"] == ["CATEGORY", "TOTAL_SALES"]
    assert result["rows"] == [
        {"CATEGORY": "Technology", "TOTAL_SALES": 1200},
        {"CATEGORY": "Furniture", "TOTAL_SALES": 800},
    ]
    assert result["row_count"] == 2
    assert (
        cursor.executed_sql
        == "SELECT category, total_sales FROM product_sales FETCH FIRST 2 ROWS ONLY"
    )
    assert connection.call_timeout == 7000


def test_execute_skips_invalid_sql() -> None:
    executor = SafeSQLExecutor(connection_factory=lambda: None)

    result = executor.execute(
        {
            "is_valid": False,
            "reason": "Only SELECT statements are allowed.",
        }
    )

    assert result["status"] == "skipped"
    assert result["error"] is None
    assert "Only SELECT statements are allowed" in result["reason"]
