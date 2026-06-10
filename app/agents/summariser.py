"""Summarise executed query results into a short business answer."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from typing import Any

import structlog
from dotenv import load_dotenv

from app.sql.oracle_connection import connect_adb

_logger = structlog.get_logger()

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
        if query_results.get("status") not in {"success", "fallback_success"}:
            return self._result(
                answer="I could not summarise the result because the SQL did not execute.",
                provider="local",
                error=query_results.get("error"),
            )

        rows = query_results.get("rows", [])
        columns = query_results.get("columns", [])
        if not rows:
            return self._result(
                answer="No matching rows were returned for this question.",
                provider="local",
            )

        answer = None
        important_numbers = []
        trends_anomalies = []
        final_takeaway = None
        error = None

        if self.profile_name:
            prompt = self._build_prompt(user_question, generated_sql, query_results)
            try:
                with self.connection_factory() as connection:
                    response_text = self._call_select_ai(connection, prompt)

                match = re.search(r"\{.*\}", response_text, re.S)
                if match:
                    data = json.loads(match.group())
                    if data.get("answer"):
                        answer = str(data["answer"]).strip()
                        important_numbers = [str(x).strip() for x in data.get("important_numbers", []) if x]
                        trends_anomalies = [str(x).strip() for x in data.get("trends_anomalies", []) if x]
                        if data.get("final_takeaway"):
                            final_takeaway = str(data["final_takeaway"]).strip()
                else:
                    _logger.warning("summariser_no_json_in_response", response_preview=response_text[:200])
                    answer = response_text
            except Exception as exc:  # noqa: BLE001
                _logger.error("summariser_select_ai_failed", error=str(exc))
        else:
            error = "SELECT_AI_PROFILE is not set."

        if not answer:
            answer = self._local_summary(user_question, rows)

        # Fallbacks for empty structured fields
        if not important_numbers and rows:
            from src.sql_agent.agents.summariser import profile_result, _fmt
            profile = profile_result(columns, [[r.get(c) for c in columns] for r in rows])
            for col in profile.get("columns", []):
                if col.get("dtype") == "numeric":
                    fmt_sum = _fmt(col["name"], col["sum"])
                    fmt_mean = _fmt(col["name"], col["mean"])
                    important_numbers.append(f"Total {col['name'].replace('_', ' ').title()}: {fmt_sum} (Average: {fmt_mean})")
            if not important_numbers:
                important_numbers.append(f"Total rows: {len(rows)}")

        if not trends_anomalies and rows:
            from src.sql_agent.agents.summariser import generate_insights
            trends_anomalies = generate_insights(user_question, columns, [[r.get(c) for c in columns] for r in rows])

        if not final_takeaway and rows:
            from src.sql_agent.agents.summariser import _column_roles, _fmt, profile_result
            profile = profile_result(columns, [[r.get(c) for c in columns] for r in rows])
            dim_idx, measure_idx, _ = _column_roles(columns, [[r.get(c) for c in columns] for r in rows], profile)
            if dim_idx is not None and measure_idx is not None:
                try:
                    top = max(rows, key=lambda r: r.get(columns[measure_idx], 0))
                    dname, mname = columns[dim_idx], columns[measure_idx]
                    final_takeaway = f"Top performer: {top.get(dname)} with {_fmt(mname, top.get(mname))} on {mname.replace('_', ' ')}."
                except Exception:  # noqa: BLE001
                    final_takeaway = f"The query successfully returned {len(rows)} records."
            else:
                final_takeaway = f"The query successfully returned {len(rows)} records."

        return self._result(
            answer=answer,
            important_numbers=important_numbers,
            trends_anomalies=trends_anomalies,
            final_takeaway=final_takeaway,
            provider="oracle_select_ai" if self.profile_name else "local",
            prompt_row_count=min(len(rows), self.max_rows_to_send),
            error=error,
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
        rows = query_results.get("rows", [])[:self.max_rows_to_send]
        columns = query_results.get("columns", [])
        total_rows = query_results.get("row_count", len(rows))
        sql = generated_sql.get("sql") or "N/A"

        return (
            "You are a senior business data analyst. A user asked a question, "
            "we ran a database query, and it returned the data below.\n\n"
            "YOUR TASK:\n"
            "1. Write a 1-2 sentence executive summary that directly answers the user's question.\n"
            "2. List 2-4 important numbers, totals, or aggregates from the data.\n"
            "3. Note any trends, growth patterns, declines, or anomalies you see.\n"
            "4. Write one plain-English takeaway a business manager can act on.\n\n"
            "STRICT RULES:\n"
            "- Do NOT invent or estimate numbers — only use what is in the data.\n"
            "- Keep language simple and non-technical.\n"
            "- Respond with ONLY a JSON object — no prose, no markdown, no explanation.\n\n"
            "REQUIRED JSON FORMAT:\n"
            '{"answer": "<1-2 sentence executive summary>", '
            '"important_numbers": ["<key number 1>", "<key number 2>"], '
            '"trends_anomalies": ["<trend or anomaly 1>"], '
            '"final_takeaway": "<actionable business takeaway>"}\n\n'
            f"USER QUESTION: {user_question}\n"
            f"SQL QUERY: {sql}\n"
            f"COLUMNS: {', '.join(columns)}\n"
            f"TOTAL ROWS RETURNED: {total_rows}\n"
            f"DATA: {json.dumps(rows, default=str)}\n"
            "JSON:"
        )

    def _local_summary(self, user_question: str, rows: list[dict[str, Any]]) -> str:
        first_row = rows[0]
        formatted_values = ", ".join(
            f"{self._humanize_label(key)}: {self._format_value(value)}"
            for key, value in first_row.items()
        )
        if len(rows) == 1:
            return f"The query returned one row: {formatted_values}."

        question_intro = "For this question"
        if user_question:
            question_intro = f"For '{user_question}'"
        return (
            f"{question_intro}, the result returned {len(rows)} rows. "
            f"The leading row is {formatted_values}."
        )

    def _humanize_label(self, label: str) -> str:
        return label.replace("_", " ").strip().lower()

    def _format_value(self, value: Any) -> str:
        if isinstance(value, float):
            return f"{value:,.2f}"
        if isinstance(value, int) and not isinstance(value, bool):
            return f"{value:,}"
        return str(value)

    def _result(
        self,
        answer: str,
        important_numbers: list[str] = None,
        trends_anomalies: list[str] = None,
        final_takeaway: str | None = None,
        provider: str = "local",
        prompt_row_count: int = 0,
        error: str | None = None,
    ) -> dict[str, Any]:
        return {
            "answer": answer,
            "important_numbers": important_numbers or [],
            "trends_anomalies": trends_anomalies or [],
            "final_takeaway": final_takeaway,
            "provider": provider,
            "prompt_row_count": prompt_row_count,
            "error": error,
        }
