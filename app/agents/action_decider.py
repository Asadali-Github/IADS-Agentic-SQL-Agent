"""Structured next-action decision before SQL generation."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from typing import Any

from dotenv import load_dotenv

from app.sql.oracle_connection import connect_adb

ConnectionFactory = Callable[[], Any]

VALID_ACTIONS = {
    "RUN_NEW_SQL",
    "TRANSFORM_PREVIOUS_RESULT",
    "MODIFY_PREVIOUS_SQL",
    "ASK_CLARIFICATION",
}

TRANSFORM_TERMS = {
    "bottom",
    "chart",
    "explain",
    "filter",
    "format",
    "highest",
    "list",
    "lowest",
    "maximum",
    "minimum",
    "rename",
    "sort",
    "summarize",
    "summary",
    "table",
    "top",
}
TRANSFORM_REFERENCES = {"above", "answer", "it", "result", "results", "them", "this", "those"}
MODIFY_STARTS = ("for ", "same but", "same for", "only ", "but for")
MODIFY_PHRASES = ("what about", "how about")
MODIFY_TERMS = {
    "category",
    "city",
    "country",
    "customer",
    "month",
    "product",
    "region",
    "segment",
    "state",
    "year",
}
RUN_NEW_TERMS = {"fresh", "latest", "new", "refresh", "rerun", "re-run", "update"}
BARE_MODIFY_REQUESTS = (
    "modify sql",
    "modify the sql",
    "modify previous sql",
    "modify the previous sql",
    "modify query",
    "modify the query",
    "modify previous query",
    "modify the previous query",
)
BARE_RUN_REQUESTS = (
    "run query",
    "run a query",
    "run new query",
    "run a new query",
    "new query",
)
BARE_USE_PREVIOUS_RESULT_REQUESTS = (
    "use previous result",
    "use the previous result",
    "use previous results",
    "use the previous results",
    "previous result",
    "the previous result",
    "previous results",
    "the previous results",
)


class QueryActionDecider:
    """Choose whether the next turn should query, modify SQL, or transform cached rows."""

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

    def decide_next_action(self, user_message: str, conversation_state: dict) -> dict:
        """Return one validated structured action; never raise."""
        local_decision = self._local_decision(user_message, conversation_state)
        if local_decision:
            return self._apply_safeguards(local_decision, user_message, conversation_state)

        if not self.profile_name:
            return self._apply_safeguards(
                self._result(
                    "ASK_CLARIFICATION",
                    False,
                    False,
                    False,
                    "No confident local action and SELECT_AI_PROFILE is not set.",
                ),
                user_message,
                conversation_state,
            )

        try:
            with self.connection_factory() as connection:
                raw_response = self._call_select_ai(
                    connection,
                    self._build_prompt(user_message, conversation_state),
                )
            decision = self._parse_decision(raw_response)
        except Exception as exc:  # pragma: no cover - live Oracle failures vary
            return self._result(
                "ASK_CLARIFICATION",
                False,
                False,
                False,
                "Could not decide safely.",
                error=str(exc),
            )

        return self._apply_safeguards(decision, user_message, conversation_state)

    def _local_decision(self, user_message: str, conversation_state: dict) -> dict | None:
        normalized = user_message.lower().strip()
        words = set(re.findall(r"[a-zA-Z0-9_-]+", normalized))

        if normalized in BARE_MODIFY_REQUESTS:
            return self._result(
                "MODIFY_PREVIOUS_SQL",
                True,
                False,
                True,
                "User asked to modify previous SQL but did not provide a constraint.",
            )

        if normalized in BARE_USE_PREVIOUS_RESULT_REQUESTS:
            return self._result(
                "TRANSFORM_PREVIOUS_RESULT",
                False,
                True,
                False,
                "User asked to use the previous result but did not provide a transformation.",
            )

        if normalized in BARE_RUN_REQUESTS:
            return self._result(
                "ASK_CLARIFICATION",
                False,
                False,
                False,
                "User asked to run a query but did not specify the data question.",
            )

        if words.intersection(RUN_NEW_TERMS) and conversation_state.get("has_previous_sql"):
            return self._result(
                "MODIFY_PREVIOUS_SQL",
                True,
                False,
                True,
                "User asked to refresh by rerunning the previous SQL context.",
            )

        if words.intersection(RUN_NEW_TERMS):
            return self._result(
                "RUN_NEW_SQL",
                True,
                False,
                False,
                "User asked for fresh data or a refresh.",
            )

        if words.intersection(TRANSFORM_TERMS) and (
            words.intersection(TRANSFORM_REFERENCES) or len(words) <= 4
        ):
            return self._result(
                "TRANSFORM_PREVIOUS_RESULT",
                False,
                True,
                False,
                "User asked to transform or explain the previous output.",
            )

        if normalized.startswith(MODIFY_STARTS + MODIFY_PHRASES) or (
            self._has_year_or_constraint(words) and conversation_state.get("has_previous_sql")
        ):
            return self._result(
                "MODIFY_PREVIOUS_SQL",
                True,
                False,
                True,
                "User added a constraint to the previous SQL request.",
            )

        if self._looks_standalone(words):
            return self._result(
                "RUN_NEW_SQL",
                True,
                False,
                False,
                "User asked a standalone analytical question.",
            )

        if words:
            return self._result(
                "RUN_NEW_SQL",
                True,
                False,
                False,
                "Defaulting to a new query for a non-empty user message.",
            )

        return self._result(
            "ASK_CLARIFICATION",
            False,
            False,
            False,
            "Empty user message.",
        )

    def _has_year_or_constraint(self, words: set[str]) -> bool:
        return bool(words.intersection(MODIFY_TERMS)) or any(
            re.fullmatch(r"20\d{2}", word) for word in words
        )

    def _looks_standalone(self, words: set[str]) -> bool:
        business_terms = {
            "by",
            "customer",
            "customers",
            "five",
            "list",
            "margin",
            "monthly",
            "product",
            "products",
            "profit",
            "revenue",
            "sales",
            "show",
            "top",
            "total",
            "what",
        }
        return len(words.intersection(business_terms)) >= 2

    def _apply_safeguards(
        self,
        decision: dict,
        user_message: str,
        conversation_state: dict,
    ) -> dict:
        action = decision.get("action")
        if action not in VALID_ACTIONS:
            return self._ask_clarification("Decision action was invalid.")

        if action == "TRANSFORM_PREVIOUS_RESULT" and not conversation_state.get(
            "has_previous_result"
        ):
            return self._ask_clarification("No previous result is available to transform.")

        if action == "MODIFY_PREVIOUS_SQL" and not conversation_state.get("has_previous_sql"):
            fallback = "RUN_NEW_SQL" if self._looks_standalone(set(user_message.split())) else None
            if fallback:
                return self._result(
                    fallback,
                    True,
                    False,
                    False,
                    "No previous SQL exists; treating the message as a new query.",
                )
            return self._ask_clarification("No previous SQL is available to modify.")

        return decision

    def _build_prompt(self, user_message: str, conversation_state: dict) -> str:
        return f"""Decide the next action for a SQL chatbot.

Return exactly one JSON object with these keys:
action, needs_sql, uses_previous_result, uses_previous_sql, reason.

Allowed action values:
- RUN_NEW_SQL
- TRANSFORM_PREVIOUS_RESULT
- MODIFY_PREVIOUS_SQL
- ASK_CLARIFICATION

Rules:
- RUN_NEW_SQL: new metric/entity/table/analysis, fresh/latest data, or independent question.
- TRANSFORM_PREVIOUS_RESULT: sort, filter, summarize, explain, rename,
  format, chart, or manipulate previous result only.
- MODIFY_PREVIOUS_SQL: user adds a constraint to previous query, such as
  date/year/region/category/customer/product type, or says same but for.
- ASK_CLARIFICATION: only when ambiguous.

Conversation state:
{json.dumps(conversation_state, default=str)}

User message:
{user_message}
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
            raise RuntimeError("Oracle Select AI returned no action decision.")
        return self._read_db_value(row[0])

    def _parse_decision(self, raw_response: str) -> dict:
        match = re.search(r"\{.*\}", raw_response, re.DOTALL)
        if not match:
            return self._ask_clarification("LLM did not return JSON.")
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return self._ask_clarification("LLM JSON could not be parsed.")

        action = parsed.get("action")
        if action not in VALID_ACTIONS:
            return self._ask_clarification("LLM returned an invalid action.")
        return self._result(
            action,
            bool(parsed.get("needs_sql")),
            bool(parsed.get("uses_previous_result")),
            bool(parsed.get("uses_previous_sql")),
            str(parsed.get("reason") or ""),
            provider="oracle_select_ai",
        )

    def _read_db_value(self, value: Any) -> str:
        if hasattr(value, "read"):
            return str(value.read())
        return str(value)

    def _ask_clarification(self, reason: str) -> dict:
        return self._result("ASK_CLARIFICATION", False, False, False, reason)

    def _result(
        self,
        action: str,
        needs_sql: bool,
        uses_previous_result: bool,
        uses_previous_sql: bool,
        reason: str,
        provider: str = "local",
        error: str | None = None,
    ) -> dict:
        return {
            "action": action,
            "needs_sql": needs_sql,
            "uses_previous_result": uses_previous_result,
            "uses_previous_sql": uses_previous_sql,
            "reason": reason,
            "provider": provider,
            "error": error,
        }


def decide_next_action(user_message: str, conversation_state: dict) -> dict:
    """Convenience wrapper for callers that do not manage a decider instance."""
    return QueryActionDecider().decide_next_action(user_message, conversation_state)
