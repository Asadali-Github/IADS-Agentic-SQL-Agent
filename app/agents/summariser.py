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

        if self.profile_name:
            prompt = self._build_prompt(user_question, generated_sql, query_results)
            try:
                import re
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
            except Exception as exc:  # noqa: BLE001
                pass

        if not answer:
            answer = self._local_summary(rows)

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
            "You are a business summarization assistant. Analyze the query results and write a structured business summary. "
            "Do not invent any numbers. Keep explanations plain and non-technical. "
            "Respond STRICTLY in a JSON object format with the following keys:\n"
            "{\n"
            '  "answer": "A short, direct executive summary of 1-2 sentences answering the user\'s question",\n'
            '  "important_numbers": ["bullet points of key numbers, totals, or aggregates"],\n'
            '  "trends_anomalies": ["bullet points of trends, growths, declines, or outlier anomalies"],\n'
            '  "final_takeaway": "A simple plain-English takeaway/conclusion for a business manager"\n'
            "}\n"
            f"Result payload: {json.dumps(payload, default=str)}\n"
            "JSON:"
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
