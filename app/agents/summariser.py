"""Summarise executed query results into a short business answer."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from typing import Any

from dotenv import load_dotenv

from app.sql.oracle_connection import connect_adb

ConnectionFactory = Callable[[], Any]


class SelectAIResultSummariser:
    """Use Oracle Select AI to narrate a concise answer from capped result rows."""

    def __init__(
        self,
        profile_name: str | None = None,
        connection_factory: ConnectionFactory | None = None,
        max_rows_to_send: int = 20,
    ) -> None:
        load_dotenv()
        self.profile_name = (
            profile_name if profile_name is not None else os.getenv("SELECT_AI_PROFILE")
        )
        self.connection_factory = connection_factory or connect_adb
        self.max_rows_to_send = max_rows_to_send

    def summarise(
        self,
        user_question: str,
        generated_sql: dict[str, Any],
        query_results: dict[str, Any],
    ) -> dict[str, Any]:
        """Return a concise answer payload for the user."""
        if query_results.get("status") != "success":
            return self._result(
                answer="I could not summarise the result because the SQL did not execute.",
                provider="local",
                error=query_results.get("error"),
            )

        rows = query_results.get("rows", [])
        if not rows:
            return self._result(
                answer="No matching rows were returned for this question.",
                provider="local",
            )

        if not self.profile_name:
            return self._result(
                answer=self._local_summary(rows),
                provider="local",
                error="SELECT_AI_PROFILE is not set.",
            )

        prompt = self._build_prompt(user_question, generated_sql, query_results)
        try:
            with self.connection_factory() as connection:
                answer = self._call_select_ai(connection, prompt)
        except Exception as exc:  # pragma: no cover - exercised by live DB smoke tests
            return self._result(
                answer=self._local_summary(rows),
                provider="local",
                error=str(exc),
            )

        return self._result(
            answer=answer,
            provider="oracle_select_ai",
            prompt_row_count=min(len(rows), self.max_rows_to_send),
        )

    def _call_select_ai(self, connection: Any, prompt: str) -> str:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT DBMS_CLOUD_AI.GENERATE(
                    prompt       => :prompt,
                    profile_name => :profile_name,
                    action       => 'narrate'
                )
                FROM dual
                """,
                {
                    "prompt": prompt,
                    "profile_name": self.profile_name,
                },
            )
            row = cursor.fetchone()

        if not row or row[0] is None:
            raise RuntimeError("Oracle Select AI returned no summary.")
        return str(row[0]).strip()

    def _build_prompt(
        self,
        user_question: str,
        generated_sql: dict[str, Any],
        query_results: dict[str, Any],
    ) -> str:
        rows = query_results.get("rows", [])[: self.max_rows_to_send]
        payload = {
            "question": user_question,
            "sql": generated_sql.get("sql"),
            "columns": query_results.get("columns", []),
            "rows": rows,
            "total_rows_returned": query_results.get("row_count", len(rows)),
        }
        return (
            "Write a concise business answer in one or two sentences. "
            "Use only the result rows provided. Do not invent numbers. "
            "Mention the leading category or trend when obvious. "
            f"Result payload: {json.dumps(payload, default=str)}"
        )

    def _local_summary(self, rows: list[dict[str, Any]]) -> str:
        first_row = rows[0]
        formatted_values = ", ".join(f"{key}: {value}" for key, value in first_row.items())
        if len(rows) == 1:
            return f"The query returned one row: {formatted_values}."
        return f"The query returned {len(rows)} rows. The top row is {formatted_values}."

    def _result(
        self,
        answer: str,
        provider: str,
        prompt_row_count: int = 0,
        error: str | None = None,
    ) -> dict[str, Any]:
        return {
            "answer": answer,
            "provider": provider,
            "prompt_row_count": prompt_row_count,
            "error": error,
        }
