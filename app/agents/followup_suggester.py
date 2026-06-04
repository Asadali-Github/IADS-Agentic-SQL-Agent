"""Oracle Select AI-backed follow-up question suggestions."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from typing import Any

from dotenv import load_dotenv

from app.sql.oracle_connection import connect_adb

ConnectionFactory = Callable[[], Any]

VALID_SUGGESTION_TYPES = {
    "RUN_NEW_SQL",
    "TRANSFORM_PREVIOUS_RESULT",
    "MODIFY_PREVIOUS_SQL",
}


class FollowUpSuggester:
    """Suggest safe next questions after a completed chatbot response."""

    def __init__(
        self,
        profile_name: str | None = None,
        connection_factory: ConnectionFactory | None = None,
        max_suggestions: int = 4,
    ) -> None:
        load_dotenv()
        self.profile_name = (
            profile_name if profile_name is not None else os.getenv("SELECT_AI_PROFILE")
        )
        self.connection_factory = connection_factory or connect_adb
        self.max_suggestions = max_suggestions

    def suggest(self, response: dict) -> list[dict[str, str]]:
        """Return validated follow-up suggestions, falling back locally on failure."""
        if not self._can_suggest(response):
            return []

        fallback = self._fallback_suggestions(response)
        if not self.profile_name:
            return fallback

        try:
            with self.connection_factory() as connection:
                raw_response = self._call_select_ai(connection, self._build_prompt(response))
            suggestions = self._parse_suggestions(raw_response)
        except Exception:
            return fallback

        return suggestions or fallback

    def _can_suggest(self, response: dict) -> bool:
        return bool(response.get("query_results", {}).get("rows")) and response.get(
            "pipeline_stage"
        ) in {
            "sql_executed_successfully",
            "sql_executed_with_fallback",
            "answered_from_conversation_memory",
        }

    def _build_prompt(self, response: dict) -> str:
        query_results = response.get("query_results") or {}
        rows = list(query_results.get("rows") or [])[:5]
        columns = query_results.get("columns") or (list(rows[0].keys()) if rows else [])
        documents = [
            {
                "title": document.get("title"),
                "type": document.get("type"),
                "content": document.get("content"),
            }
            for document in (response.get("retrieved_documents") or [])[:5]
        ]
        payload = {
            "original_question": response.get("original_question"),
            "resolved_question": response.get("resolved_question"),
            "sql": (response.get("generated_sql") or {}).get("sql"),
            "columns": columns,
            "row_count": query_results.get("row_count", len(rows)),
            "sample_rows": rows,
            "retrieved_context": documents,
        }
        return f"""Suggest helpful follow-up questions for an enterprise SQL chatbot.

Return only JSON in this exact shape:
{{
  "suggestions": [
    {{"label": "short button label", "question": "full user question", "type": "RUN_NEW_SQL"}}
  ]
}}

Allowed type values:
- RUN_NEW_SQL
- TRANSFORM_PREVIOUS_RESULT
- MODIFY_PREVIOUS_SQL

Rules:
- Suggest at most {self.max_suggestions} questions.
- Use only the provided columns, SQL, rows, and business context.
- Do not invent unavailable tables or metrics.
- Cached-result transforms must be limited to sorting, explaining, lowest/highest,
  top/bottom row selection, or chart-style requests.
- Include at least one previous-SQL modification when SQL exists.
- Keep labels under 28 characters.
- Questions must be directly usable as the next user message.

Current response state:
{json.dumps(payload, default=str)}
"""

    def _call_select_ai(self, connection: Any, prompt: str) -> str:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT DBMS_CLOUD_AI.GENERATE(
                    prompt       => :prompt,
                    profile_name => :profile_name,
                    action       => 'chat'
                )
                FROM dual
                """,
                {"prompt": prompt, "profile_name": self.profile_name},
            )
            row = cursor.fetchone()

        if not row or row[0] is None:
            raise RuntimeError("Oracle Select AI returned no follow-up suggestions.")
        return self._read_db_value(row[0])

    def _parse_suggestions(self, raw_response: str) -> list[dict[str, str]]:
        match = re.search(r"\{.*\}", raw_response, re.DOTALL)
        if not match:
            return []
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError:
            return []

        parsed: list[dict[str, str]] = []
        for suggestion in payload.get("suggestions") or []:
            label = str(suggestion.get("label") or "").strip()
            question = str(suggestion.get("question") or "").strip()
            suggestion_type = str(suggestion.get("type") or "").strip()
            if not label or not question or suggestion_type not in VALID_SUGGESTION_TYPES:
                continue
            if suggestion_type == "TRANSFORM_PREVIOUS_RESULT" and not self._supported_transform(
                question
            ):
                continue
            parsed.append(
                {
                    "label": label[:40],
                    "question": question[:240],
                    "type": suggestion_type,
                }
            )
            if len(parsed) >= self.max_suggestions:
                break
        return parsed

    def _supported_transform(self, question: str) -> bool:
        normalized = question.lower()
        return any(
            term in normalized
            for term in (
                "ascending",
                "bottom",
                "chart",
                "descending",
                "explain",
                "highest",
                "lowest",
                "sort",
                "top",
            )
        )

    def _fallback_suggestions(self, response: dict) -> list[dict[str, str]]:
        query_results = response.get("query_results") or {}
        rows = list(query_results.get("rows") or [])
        if not rows:
            return []

        columns = query_results.get("columns") or list(rows[0].keys())
        numeric_columns = self._numeric_columns(rows)
        suggestions = [
            {
                "label": "Sort ascending",
                "question": "Sort these ascendingly",
                "type": "TRANSFORM_PREVIOUS_RESULT",
            },
            {
                "label": "Explain result",
                "question": "Explain this result",
                "type": "TRANSFORM_PREVIOUS_RESULT",
            },
        ]
        if (response.get("generated_sql") or {}).get("sql"):
            suggestions.append(
                {
                    "label": "Filter 2024",
                    "question": "Show the same result for 2024 only",
                    "type": "MODIFY_PREVIOUS_SQL",
                }
            )
        if numeric_columns and columns:
            suggestions.append(
                {
                    "label": "Show lowest",
                    "question": f"What is the lowest {numeric_columns[-1]} among these?",
                    "type": "TRANSFORM_PREVIOUS_RESULT",
                }
            )
        return suggestions[: self.max_suggestions]

    def _numeric_columns(self, rows: list[dict[str, Any]]) -> list[str]:
        columns = list(rows[0].keys())
        numeric_columns = []
        for column in columns:
            values = [row.get(column) for row in rows if row.get(column) is not None]
            if values and all(self._is_numeric(value) for value in values):
                numeric_columns.append(column)
        return numeric_columns

    def _is_numeric(self, value: Any) -> bool:
        if isinstance(value, bool) or value is None:
            return False
        if isinstance(value, int | float):
            return True
        try:
            float(str(value).replace(",", ""))
        except (TypeError, ValueError):
            return False
        return True

    def _read_db_value(self, value: Any) -> str:
        if hasattr(value, "read"):
            return str(value.read())
        return str(value)
