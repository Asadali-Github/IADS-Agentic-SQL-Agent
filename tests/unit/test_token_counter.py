"""Tests for src/sql_agent/llm/token_counter.py."""

from __future__ import annotations

from sql_agent.llm.token_counter import (
    PRICING,
    TokenCounter,
    estimate_tokens,
    price_usage,
)


def test_estimate_tokens_monotonic_and_nonzero():
    assert estimate_tokens("") == 0
    assert estimate_tokens("hello") >= 1
    assert estimate_tokens("hello world foo bar") > estimate_tokens("hello")


def test_price_usage_uses_rate_card():
    price = PRICING["cohere.command-r-08-2024"]
    cost = price_usage("cohere.command-r-08-2024", 1000, 1000)
    assert cost == round(price.input_per_1k + price.output_per_1k, 8)


def test_unknown_model_falls_back_to_expensive_tier():
    # Never silently under-report: unknown model priced at the most expensive tier.
    assert price_usage("mystery", 1000, 1000) >= price_usage("small", 1000, 1000)


def test_counter_accumulates_across_calls():
    tc = TokenCounter()
    tc.record("small", "a prompt here", "a completion")
    tc.record("small", "another prompt", "more output")
    assert len(tc.usages) == 2
    assert tc.total_tokens == sum(u.total_tokens for u in tc.usages)
    assert tc.total_cost_usd > 0


def test_record_counts_uses_exact_provider_numbers():
    tc = TokenCounter()
    u = tc.record_counts("large", prompt_tokens=500, completion_tokens=100)
    assert u.prompt_tokens == 500 and u.completion_tokens == 100
    assert u.cost_usd == price_usage("large", 500, 100)


def test_custom_tokenizer_override():
    tc = TokenCounter(tokenizer=lambda text: len(text.split()))
    u = tc.record("small", "one two three", "four five")
    assert u.prompt_tokens == 3 and u.completion_tokens == 2


def test_as_metric_shape():
    tc = TokenCounter()
    tc.record("small", "hi", "yo")
    m = tc.as_metric()
    assert m.name == "token_cost_usd" and m.unit == "usd"


# --- cost-aware guardrails --------------------------------------------------
from sql_agent.llm.token_counter import BudgetExceededError  # noqa: E402


def test_budget_remaining_and_over_budget():
    tc = TokenCounter(budget_usd=0.01)
    tc.record_counts("large", 1000, 1000)  # ~0.018 > 0.01
    assert tc.over_budget is True
    assert tc.remaining_usd < 0


def test_max_calls_guard():
    tc = TokenCounter(max_calls=2)
    tc.record("small", "a", "b")
    tc.record("small", "a", "b")
    assert tc.over_budget is False
    assert tc.would_exceed() is True  # a 3rd call would breach


def test_check_raises_budget_exceeded():
    tc = TokenCounter(budget_usd=0.0001)
    tc.record_counts("large", 1000, 1000)
    import pytest
    with pytest.raises(BudgetExceededError):
        tc.check()


def test_unlimited_counter_never_over_budget():
    tc = TokenCounter()
    tc.record_counts("large", 10_000, 10_000)
    assert tc.over_budget is False
    assert tc.remaining_usd is None
