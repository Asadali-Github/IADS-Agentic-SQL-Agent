"""Reflection agent that can request corrected SQL after failed execution."""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from dotenv import load_dotenv

from app.sql.oracle_connection import connect_adb
from evaluation.metrics import detect_issue

ConnectionFactory = Callable[[], Any]


class QueryReflector:
    """Detect failed query attempts and optionally ask Oracle Select AI for a fix."""

    def __init__(
        self,
        profile_name: str | None = None,
        connection_factory: ConnectionFactory | None = None,
        max_retries: int = 1,
    ) -> None:
        load_dotenv()
        self.profile_name = (
            profile_name if profile_name is not None else os.getenv("SELECT_AI_PROFILE")
        )
        self.connection_factory = connection_factory or connect_adb
        self.max_retries = max_retries

    def reflect(
        self,
        question: str,
        generated_sql: dict,
        query_results: dict,
        retrieved_documents: list[dict],
    ) -> dict:
        """Return reflection status and possible corrected SQL without raising."""
        issue = detect_issue(
            {
                "generated_sql": generated_sql,
                "query_results": query_results,
            }
        )
        if issue is None:
            return self._result(ok=True, issue=None)

        if not self.profile_name or self.max_retries <= 0:
            return self._result(ok=False, issue=issue)

        try:
            with self.connection_factory() as connection:
                corrected_sql = self._call_select_ai(
                    connection,
                    self._build_prompt(
                        question,
                        generated_sql,
                        issue,
                        retrieved_documents,
                    ),
                )
        except Exception as exc:  # pragma: no cover - live Oracle failures vary
            return self._result(ok=False, issue=issue, error=str(exc))

        return self._result(
            ok=False,
            issue=issue,
            corrected_sql=corrected_sql or None,
            provider="oracle_select_ai",
        )

    def _build_prompt(
        self,
        question: str,
        generated_sql: dict,
        issue: str,
        retrieved_documents: list[dict],
    ) -> str:
        schema_context = "\n".join(
            f"- {document.get('title', 'Untitled')}: {document.get('content', '')}"
            for document in retrieved_documents
        )
        bad_sql = generated_sql.get("sql") or ""
        return (
            "Correct the SQL for this Oracle analytics question. Return only SQL.\n\n"
            f"Question: {question}\n"
            f"Issue detected: {issue}\n"
            f"Bad SQL:\n{bad_sql}\n\n"
            f"Retrieved schema and business context:\n{schema_context}"
        )

    def _call_select_ai(self, connection: Any, prompt: str) -> str:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT DBMS_CLOUD_AI.GENERATE(
                    prompt       => :prompt,
                    profile_name => :profile_name,
                    action       => 'showsql'
                )
                FROM dual
                """,
                {"prompt": prompt, "profile_name": self.profile_name},
            )
            row = cursor.fetchone()

        if not row or row[0] is None:
            raise RuntimeError("Oracle Select AI returned no corrected SQL.")
        return self._read_db_value(row[0]).strip()

    def _read_db_value(self, value: Any) -> str:
        if hasattr(value, "read"):
            return str(value.read())
        return str(value)

    def _result(
        self,
        ok: bool,
        issue: str | None,
        corrected_sql: str | None = None,
        provider: str = "local",
        error: str | None = None,
    ) -> dict:
        return {
            "ok": ok,
            "issue": issue,
            "corrected_sql": corrected_sql,
            "provider": provider,
            "error": error,
        }
