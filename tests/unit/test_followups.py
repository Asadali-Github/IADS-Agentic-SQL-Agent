"""Unit tests for the shared follow-up resolver (app/agents/followups.py).

These pin down the contract both backends rely on: standalone questions are
never treated as follow-ups, genuine follow-ups are rewritten into standalone
natural-language questions, and SQL is never involved in the rewrite.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT), str(_ROOT / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from app.agents.followups import (  # noqa: E402
    looks_like_follow_up,
    resolve,
    rewrite_follow_up,
)

PREVIOUS = "What were total sales by product category?"


# --- looks_like_follow_up: standalone questions are NOT follow-ups -----------

@pytest.mark.parametrize(
    "question",
    [
        "total sales by region",          # 4 words but self-contained
        "Show total profit by region",
        "top products by revenue",
        "How many orders were placed in 2025?",
        "Show me total orders by city",
        "which product had the highest revenue",
    ],
)
def test_standalone_questions_are_not_follow_ups(question: str) -> None:
    assert looks_like_follow_up(question) is False


# --- looks_like_follow_up: genuine ellipses ARE follow-ups -------------------

@pytest.mark.parametrize(
    "question",
    [
        "What about profit?",
        "what about by category?",
        "and by region?",
        "same for 2024",
        "also by region",
        "compare regions",
        "by region",
    ],
)
def test_elliptical_questions_are_follow_ups(question: str) -> None:
    assert looks_like_follow_up(question) is True


def test_empty_question_is_not_a_follow_up() -> None:
    assert looks_like_follow_up("") is False
    assert looks_like_follow_up("   ") is False


# --- rewrite_follow_up: produces a standalone question, never SQL ------------

def test_rewrite_swaps_measure() -> None:
    out = rewrite_follow_up("What about profit?", PREVIOUS)
    assert out is not None
    assert "profit" in out.lower()
    assert "product category" in out.lower()
    assert "sales" not in out.lower()
    assert "select" not in out.lower()


def test_rewrite_swaps_dimension() -> None:
    out = rewrite_follow_up("what about by region?", PREVIOUS)
    assert out is not None
    assert "by region" in out.lower()
    assert "product category" not in out.lower()


def test_rewrite_appends_dimension_when_previous_had_none() -> None:
    out = rewrite_follow_up("by region", "What was total revenue?")
    assert out is not None
    assert "by region" in out.lower()
    assert "revenue" in out.lower()


def test_rewrite_returns_none_when_nothing_to_swap() -> None:
    assert rewrite_follow_up("what about it?", PREVIOUS) is None
    assert rewrite_follow_up("anything", "") is None


# --- resolve: end-to-end behaviour -------------------------------------------

def test_resolve_passes_through_without_previous_turn() -> None:
    assert resolve("What about profit?", None) == "What about profit?"


def test_resolve_passes_through_standalone_question() -> None:
    q = "Show total profit by region"
    assert resolve(q, PREVIOUS) == q


def test_resolve_rewrites_genuine_follow_up() -> None:
    out = resolve("What about profit?", PREVIOUS)
    assert "profit" in out.lower()
    assert "product category" in out.lower()
    assert "select" not in out.lower()


def test_resolve_falls_back_to_raw_when_unrewritable() -> None:
    assert resolve("what about it?", PREVIOUS) == "what about it?"
