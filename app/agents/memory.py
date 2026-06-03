"""Small in-process conversation memory for follow-up business questions.

Follow-up detection and rewriting live in :mod:`app.agents.followups`, which is
shared with the offline pipeline so both backends behave identically. Memory's
only job here is to remember recent successful turns and, for a genuine
elliptical follow-up, hand back a *standalone* rewritten question. It never
injects the previous SQL into the next turn, so every question is generated and
executed against the database afresh instead of being answered from the prior
result.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.agents.followups import looks_like_follow_up, resolve as resolve_follow_up


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
        """Rewrite a genuine follow-up into a standalone, database-ready question.

        Standalone questions (and anything with no prior successful turn) are
        returned unchanged. Genuine follow-ups like "what about profit?" are
        rewritten against the previous *question* (e.g. "What were total profit
        by product category?") -- never against the previous SQL -- so the agent
        always queries the database instead of replaying the last answer.
        """
        question = user_question.strip()
        previous_turn = self.latest_successful_turn()
        if not previous_turn:
            return question
        return resolve_follow_up(question, previous_turn.original_question)

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

    def is_follow_up(self, question: str) -> bool:
        """True only when ``question`` is a genuine follow-up to a prior turn."""
        if not self.latest_successful_turn():
            return False
        return looks_like_follow_up(question)
