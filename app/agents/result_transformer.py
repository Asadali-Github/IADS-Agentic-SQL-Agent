"""Cached-result transformations that never call SQL or the database."""

from __future__ import annotations

import re
from typing import Any

from app.agents.memory import ConversationMemory, MemoryAnswer


class CachedResultTransformer:
    """Apply safe transformations to the latest cached result rows."""

    def __init__(self, memory: ConversationMemory) -> None:
        self.memory = memory

    def transform(self, user_message: str) -> MemoryAnswer | None:
        """Return an answer from cached rows, or None when clarification is safer."""
        memory_answer = self.memory.answer_from_previous_results(user_message)
        if memory_answer:
            return memory_answer

        previous_turn = self.memory.latest_result_turn()
        if not previous_turn:
            return None

        rows = list(previous_turn.query_results.get("rows") or [])
        if not rows:
            return None

        normalized = user_message.lower().strip()
        filtered_answer = self._filter_rows_by_text(user_message, rows, previous_turn)
        if filtered_answer:
            return filtered_answer

        if any(term in normalized for term in ("explain", "summary", "summarize")):
            return MemoryAnswer(
                answer=self._explain_rows(rows),
                rows=rows,
                columns=list(rows[0].keys()),
                source_turn=previous_turn,
            )

        limited_rows = self._limit_rows(user_message, rows)
        if limited_rows is not None:
            return MemoryAnswer(
                answer=f"Here are {len(limited_rows)} rows from the previous result.",
                rows=limited_rows,
                columns=list(limited_rows[0].keys()) if limited_rows else list(rows[0].keys()),
                source_turn=previous_turn,
            )

        return None

    def _filter_rows_by_text(
        self,
        user_message: str,
        rows: list[dict[str, Any]],
        previous_turn: Any,
    ) -> MemoryAnswer | None:
        term = self._text_filter_term(user_message)
        if not term:
            return None

        text_columns = [
            column
            for column in rows[0]
            if any(isinstance(row.get(column), str) for row in rows)
        ]
        if not text_columns:
            return None

        normalized_term = term.lower()
        filtered_rows = [
            row
            for row in rows
            if any(normalized_term in str(row.get(column, "")).lower() for column in text_columns)
        ]
        if filtered_rows:
            answer = (
                f"From the previous result, {len(filtered_rows)} row(s) contain "
                f"{term!r}."
            )
        else:
            answer = f"No rows in the previous result contain {term!r}."

        return MemoryAnswer(
            answer=answer,
            rows=filtered_rows,
            columns=list(rows[0].keys()),
            source_turn=previous_turn,
        )

    def _text_filter_term(self, user_message: str) -> str | None:
        normalized = user_message.lower().strip()
        if not re.search(r"\b(?:it|them|these|those|result|results|answer|this)\b", normalized):
            return None

        match = re.search(
            r"\b(?:have|has|contain|contains|containing|include|includes|including|with)\s+"
            r"[\"']?([a-zA-Z0-9_-]+)[\"']?",
            normalized,
        )
        if not match:
            return None

        term = match.group(1).strip()
        if term in {"a", "an", "any", "the"}:
            return None
        return term

    def _explain_rows(self, rows: list[dict[str, Any]]) -> str:
        columns = list(rows[0].keys())
        numeric_columns = [
            column
            for column in columns
            if all(self._is_numeric(row.get(column)) for row in rows if row.get(column) is not None)
        ]
        if numeric_columns:
            metric_column = numeric_columns[-1]
            sorted_rows = sorted(
                rows,
                key=lambda row: self._numeric_value(row.get(metric_column)),
                reverse=True,
            )
            highest = sorted_rows[0]
            lowest = sorted_rows[-1]
            return (
                f"The previous result contains {len(rows)} rows. "
                f"It is mainly comparing {metric_column.replace('_', ' ').lower()} across "
                f"{', '.join(column for column in columns if column != metric_column)}. "
                f"The highest row is {self._format_row(highest)}; "
                f"the lowest row is {self._format_row(lowest)}."
            )

        return (
            f"The previous result contains {len(rows)} rows with columns: "
            f"{', '.join(columns)}."
        )

    def _limit_rows(self, user_message: str, rows: list[dict[str, Any]]) -> list[dict] | None:
        match = re.search(r"\b(?:top|first|bottom|last)\s+(\d+)\b", user_message.lower())
        if not match:
            return None
        limit = max(1, int(match.group(1)))
        if any(term in user_message.lower() for term in ("bottom", "last")):
            return rows[-limit:]
        return rows[:limit]

    def _format_row(self, row: dict[str, Any]) -> str:
        return ", ".join(f"{key}: {value}" for key, value in row.items())

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

    def _numeric_value(self, value: Any) -> float:
        if isinstance(value, int | float) and not isinstance(value, bool):
            return float(value)
        return float(str(value).replace(",", ""))
