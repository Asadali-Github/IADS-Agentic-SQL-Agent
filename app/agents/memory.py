"""Small in-process conversation memory for follow-up business questions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

FOLLOW_UP_MARKERS = {
    "also",
    "again",
    "same",
    "previous",
    "last",
    "instead",
    "compare",
}

FOLLOW_UP_PHRASES = (
    "what about",
    "how about",
    "and ",
    "for ",
    "same for",
    "do the same",
)


@dataclass(frozen=True)
class ConversationTurn:
    """One completed user question and pipeline response."""

    original_question: str
    resolved_question: str
    answer: dict[str, Any]
    generated_sql: dict[str, Any]
    pipeline_stage: str

    @property
    def is_successful(self) -> bool:
        """Return true when the turn produced usable SQL-backed information."""
        return self.pipeline_stage in {
            "sql_executed_successfully",
            "sql_executed_with_fallback",
        } and bool(self.generated_sql.get("sql"))


class ConversationMemory:
    """Remember recent successful turns so short follow-ups can be grounded."""

    def __init__(self, max_turns: int = 6) -> None:
        self.max_turns = max_turns
        self.turns: list[ConversationTurn] = []

    def resolve_question(self, user_question: str) -> str:
        """Expand a follow-up question with the latest successful business context."""
        question = user_question.strip()
        previous_turn = self.latest_successful_turn()
        if not previous_turn or not self._looks_like_follow_up(question):
            return question

        return (
            f"Previous successful question: {previous_turn.original_question}\n"
            f"Previous SQL: {previous_turn.generated_sql.get('sql')}\n"
            f"Follow-up question: {question}"
        )

    def record(self, response: dict[str, Any]) -> None:
        """Store a completed pipeline response."""
        self.turns.append(
            ConversationTurn(
                original_question=response["original_question"],
                resolved_question=response.get("resolved_question", response["original_question"]),
                answer=response.get("answer", {}),
                generated_sql=response.get("generated_sql", {}),
                pipeline_stage=response.get("pipeline_stage", ""),
            )
        )
        self.turns = self.turns[-self.max_turns :]

    def latest_successful_turn(self) -> ConversationTurn | None:
        """Return the latest turn that produced usable data."""
        for turn in reversed(self.turns):
            if turn.is_successful:
                return turn
        return None

    def _looks_like_follow_up(self, question: str) -> bool:
        normalized_question = question.lower().strip()
        words = normalized_question.split()
        if len(words) <= 4:
            return True

        if any(normalized_question.startswith(phrase) for phrase in FOLLOW_UP_PHRASES):
            return True

        return any(marker in words for marker in FOLLOW_UP_MARKERS)
