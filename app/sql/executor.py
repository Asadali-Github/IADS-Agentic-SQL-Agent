"""Oracle SQL executor for validated SELECT queries."""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from dotenv import load_dotenv

from app.sql.oracle_connection import connect_adb
from app.sql.validator import validate_sql


ConnectionFactory = Callable[[], Any]


class OracleSQLExecutor:
    """Execute safe SQL against Oracle Autonomous Database."""

    def __init__(
        self,
        connection_factory: ConnectionFactory | None = None,
        max_rows: int | None = None,
        timeout_seconds: int | None = None,
    ) -> None:
        load_dotenv()
        self.connection_factory = connection_factory or connect_adb
        self.max_rows = max_rows if max_rows is not None else self._env_int(
            "AGENT_MAX_ROWS_RETURNED",
            500,
        )
        self.timeout_seconds = timeout_seconds if timeout_seconds is not None else self._env_int(
            "AGENT_QUERY_TIMEOUT_SECONDS",
            15,
        )

    def execute(self, sql: str) -> dict:
        """Validate and execute SQL, returning rows as JSON-friendly dictionaries."""
        validation = validate_sql(sql)
        if not validation["is_valid"]:
            return self._result(
                success=False,
                error=validation["reason"],
            )

        safe_sql = validation.get("safe_sql") or sql.strip()
        if not safe_sql:
            return self._result(
                success=False,
                error="Empty SQL query.",
            )

        try:
            with self.connection_factory() as connection:
                self._apply_timeout(connection)
                with connection.cursor() as cursor:
                    cursor.arraysize = min(max(self.max_rows, 1), 1000)
                    cursor.execute(safe_sql)

                    columns = [description[0] for description in cursor.description or []]
                    fetched_rows = cursor.fetchmany(self.max_rows + 1)
                    capped = len(fetched_rows) > self.max_rows
                    rows = fetched_rows[: self.max_rows]

            return self._result(
                success=True,
                columns=columns,
                rows=[
                    {
                        column: self._to_json_value(value)
                        for column, value in zip(columns, row, strict=True)
                    }
                    for row in rows
                ],
                capped=capped,
            )
        except Exception as exc:  # pragma: no cover - live DB failures vary
            return self._result(
                success=False,
                error=f"Oracle execution failed: {exc}",
            )

    def _apply_timeout(self, connection: Any) -> None:
        if hasattr(connection, "call_timeout"):
            connection.call_timeout = self.timeout_seconds * 1000

    def _env_int(self, name: str, default: int) -> int:
        value = os.getenv(name)
        if not value:
            return default

        try:
            return int(value)
        except ValueError:
            return default

    def _to_json_value(self, value: Any) -> Any:
        if value is None:
            return None

        if hasattr(value, "read"):
            return self._to_json_value(value.read())

        if isinstance(value, Decimal):
            return int(value) if value == value.to_integral_value() else float(value)

        if isinstance(value, datetime | date):
            return value.isoformat()

        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")

        return value

    def _result(
        self,
        success: bool,
        columns: list[str] | None = None,
        rows: list[dict] | None = None,
        capped: bool = False,
        error: str | None = None,
    ) -> dict:
        result_rows = rows or []
        return {
            "success": success,
            "columns": columns or [],
            "rows": result_rows,
            "row_count": len(result_rows),
            "capped": capped,
            "error": error,
        }


def execute_sql(sql: str) -> dict:
    """Convenience wrapper for one-off SQL execution."""
    return OracleSQLExecutor().execute(sql)
