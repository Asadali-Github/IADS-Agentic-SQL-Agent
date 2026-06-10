"""Tests for src/sql_agent/suggestions.py (UI question suggestions)."""

from __future__ import annotations

from sql_agent.suggestions import suggest_questions


def test_default_returns_n_suggestions():
    out = suggest_questions(4)
    assert len(out) == 4
    assert all({"label", "question"} <= set(s) for s in out)


def test_partial_ranks_profit_first():
    out = suggest_questions(3, partial="profit margin")
    assert out
    assert "margin" in out[0]["question"].lower() or "profit" in out[0]["question"].lower()


def test_partial_products():
    labels = [s["label"] for s in suggest_questions(2, partial="best selling products")]
    assert any("product" in l.lower() for l in labels)


def test_empty_partial_returns_catalogue_order():
    assert suggest_questions(2, partial="   ") == suggest_questions(2)
