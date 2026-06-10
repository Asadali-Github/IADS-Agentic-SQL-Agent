"""Question planning agent for simple and multi-step analytical requests."""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from typing import Any

from dotenv import load_dotenv

from app.sql.oracle_connection import connect_adb

ConnectionFactory = Callable[[], Any]

COMPLEX_TERMS = ("compare", "vs", "trend", "growth", "why", "reason", "difference")


class QueryPlanner:
    """Build a simple execution plan without making the pipeline depend on planning."""

    def __init__(
        self,
        profile_name: str | None = None,
        connection_factory: ConnectionFactory | None = None,
    ) -> None:
        load_dotenv()
        self.profile_name = (
            profile_name if profile_name is not None else os.getenv("SELECT_AI_PROFILE")
        )
        self.connection_factory = connection_factory or connect_adb

    def plan(self, user_question: str, retrieved_documents: list[dict]) -> dict:
        """Return a single-step or multi-step plan, degrading gracefully on errors."""
        question = user_question.strip()
        if not self._is_complex(question):
            return self._single_step(question)

        if not self.profile_name:
            return self._single_step(
                question,
                error="SELECT_AI_PROFILE is not set.",
            )

        try:
            with self.connection_factory() as connection:
                raw_plan = self._call_select_ai(
                    connection,
                    self._build_prompt(question, retrieved_documents),
                )
            steps = self._parse_steps(raw_plan)
        except Exception as exc:  # pragma: no cover - live Oracle failures vary
            return self._single_step(question, error=str(exc))

        if not steps:
            return self._single_step(
                question,
                error="Oracle Select AI returned no usable planning steps.",
            )

        return {
            "type": "multi_step",
            "steps": steps,
            "original_question": question,
            "provider": "oracle_select_ai",
            "error": None,
        }

    def _is_complex(self, question: str) -> bool:
        return any(
            re.search(rf"\b{re.escape(term)}\b", question, re.IGNORECASE)
            for term in COMPLEX_TERMS
        )

    def _build_prompt(self, question: str, retrieved_documents: list[dict]) -> str:
        schema_context = "\n".join(
            f"- {document.get('title', 'Untitled')}: {document.get('content', '')}"
            for document in retrieved_documents
        )
        return (
            "Break this analytics question into concise SQL-answerable sub-questions. "
            "Return only the sub-questions, one per line.\n\n"
            f"Question: {question}\n\n"
            f"Retrieved schema and business context:\n{schema_context}"
        )

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
            raise RuntimeError("Oracle Select AI returned no plan.")
        return self._read_db_value(row[0]).strip()

    def _parse_steps(self, raw_plan: str) -> list[str]:
        steps: list[str] = []
        for line in raw_plan.splitlines():
            step = re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", line).strip()
            if step:
                steps.append(step)
        return steps

    def _read_db_value(self, value: Any) -> str:
        if hasattr(value, "read"):
            return str(value.read())
        return str(value)

    def _single_step(self, question: str, error: str | None = None) -> dict:
        return {
            "type": "single_step",
            "steps": [question],
            "original_question": question,
            "provider": "local",
            "error": error,
        }
