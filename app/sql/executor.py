"""Safe read-only SQL executor for validated Oracle queries."""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from dotenv import load_dotenv

from app.sql.fallbacks import fallback_results_for_sql
from app.sql.oracle_connection import connect_adb

ConnectionFactory = Callable[[], Any]


class SafeSQLExecutor:
    """Execute validated SELECT SQL and return a small result payload."""

    def __init__(
        self,
        connection_factory: ConnectionFactory | None = None,
        max_rows: int | None = None,
        timeout_seconds: int | None = None,
    ) -> None:
        load_dotenv()
        self.connection_factory = connection_factory or connect_adb
        self.max_rows = max_rows or int(os.getenv("AGENT_MAX_ROWS_RETURNED", "500"))
        self.timeout_seconds = timeout_seconds or int(
            os.getenv("AGENT_QUERY_TIMEOUT_SECONDS", "15")
        )

    def execute(self, sql_validation: dict[str, Any]) -> dict[str, Any]:
        """Execute only validated SQL and cap returned rows."""
        if not sql_validation.get("is_valid"):
            return self._result(
                status="skipped",
                reason=f"SQL was not executed: {sql_validation.get('reason')}",
            )

        sql = sql_validation.get("safe_sql")
        if not sql:
            return self._result(
                status="skipped",
                reason="SQL was not executed: no safe SQL was provided.",
            )

        row_limit = min(int(sql_validation.get("max_rows", self.max_rows)), self.max_rows)

        try:
            with self.connection_factory() as connection:
                self._apply_timeout(connection)
                columns, rows = self._execute_select(connection, sql, row_limit)
        except Exception as exc:  # pragma: no cover - exercised by live DB smoke tests
            fallback_results = fallback_results_for_sql(sql)
            if fallback_results:
                return self._result(
                    status="fallback_success",
                    reason="Live SQL execution failed; returned cached fallback rows.",
                    sql=sql,
                    columns=fallback_results["columns"],
                    rows=fallback_results["rows"],
                    row_count=len(fallback_results["rows"]),
                    row_limit=row_limit,
                    error=str(exc),
                )
            return self._result(
                status="error",
                reason="SQL execution failed.",
                sql=sql,
                error=str(exc),
            )

        return self._result(
            status="success",
            reason="SQL executed successfully.",
            sql=sql,
            columns=columns,
            rows=rows,
            row_count=len(rows),
            row_limit=row_limit,
        )

    def _execute_select(
        self,
        connection: Any,
        sql: str,
        row_limit: int,
    ) -> tuple[list[str], list[dict]]:
        with connection.cursor() as cursor:
            cursor.arraysize = min(row_limit, 100)
            cursor.execute(sql)
            columns = [description[0] for description in cursor.description or []]
            raw_rows = cursor.fetchmany(row_limit)

        rows = [dict(zip(columns, row, strict=False)) for row in raw_rows]
        return columns, rows

    def _apply_timeout(self, connection: Any) -> None:
        if hasattr(connection, "call_timeout"):
            connection.call_timeout = self.timeout_seconds * 1000

    def _result(
        self,
        status: str,
        reason: str,
        sql: str | None = None,
        columns: list[str] | None = None,
        rows: list[dict] | None = None,
        row_count: int = 0,
        row_limit: int | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        return {
            "status": status,
            "reason": reason,
            "sql": sql,
            "columns": columns or [],
            "rows": rows or [],
            "row_count": row_count,
            "row_limit": row_limit or self.max_rows,
            "error": error,
        }
