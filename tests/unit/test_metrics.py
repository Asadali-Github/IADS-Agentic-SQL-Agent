"""Tests for evaluation/metrics.py."""

from __future__ import annotations

from evaluation.metrics import (
    compute_metrics,
    exact_set_match,
    execution_accuracy,
    partial_match,
    percentile,
    retry_rate,
)
from sql_agent.core.models import CaseResult, Difficulty


def test_execution_accuracy_order_insensitive_by_default():
    assert execution_accuracy([[1], [2]], [[2], [1]]) is True


def test_execution_accuracy_respects_order_when_required():
    assert execution_accuracy([[1], [2]], [[2], [1]], order_matters=True) is False
    assert execution_accuracy([[1], [2]], [[1], [2]], order_matters=True) is True


def test_execution_accuracy_numeric_and_whitespace_normalisation():
    # 5 vs 5.0, trailing space, float rounding noise all treated as equal.
    assert execution_accuracy([["x", 5]], [["x ", 5.000000001]]) is True


def test_execution_accuracy_counts_multiplicity():
    assert execution_accuracy([[1], [1]], [[1]]) is False


def test_exact_set_match_ignores_order_and_duplicates():
    assert exact_set_match([[1], [1], [2]], [[2], [1]]) is True
    assert exact_set_match([[1], [2]], [[1], [3]]) is False


def test_partial_match_is_recall_over_expected():
    assert partial_match([["a"], ["b"], ["c"], ["d"]], [["a"], ["b"]]) == 0.5
    assert partial_match([], []) == 1.0
    assert partial_match([], [[1]]) == 0.0


def test_percentile_interpolates():
    assert percentile([10, 20, 30, 40], 50) == 25.0
    assert percentile([], 50) is None
    assert percentile([7], 95) == 7.0


def _case(**kw):
    base = dict(question_id="q", execution_match=False, exact_set_match=False,
                partial_match=0.0, retries=0)
    base.update(kw)
    return CaseResult(**base)


def test_retry_rate():
    cases = [_case(retries=0), _case(retries=2), _case(retries=0), _case(retries=1)]
    assert retry_rate(cases) == 0.5


def test_compute_metrics_headline_and_tiers():
    cases = [
        _case(question_id="q1", difficulty=Difficulty.EASY, execution_match=True,
              exact_set_match=True, partial_match=1.0, latency_ms=10, token_cost_usd=0.001),
        _case(question_id="q2", difficulty=Difficulty.HARD, execution_match=False,
              partial_match=0.5, retries=1, latency_ms=30, token_cost_usd=0.003),
    ]
    metrics = {m.name: m.value for m in compute_metrics(cases)}
    assert metrics["execution_accuracy"] == 0.5
    assert metrics["partial_match"] == 0.75
    assert metrics["retry_rate"] == 0.5
    assert metrics["execution_accuracy_easy"] == 1.0
    assert metrics["execution_accuracy_hard"] == 0.0
    assert "latency_p50_ms" in metrics
    assert "token_cost_per_request_usd" in metrics


def test_compute_metrics_empty():
    metrics = compute_metrics([])
    assert metrics[0].name == "execution_accuracy"
    assert metrics[0].value == 0.0


# --- semantic / AST SQL comparison -----------------------------------------
from evaluation.metrics import (  # noqa: E402
    canonicalize_sql,
    sql_ast_match,
    sql_structural_similarity,
)

_A = ("SELECT c.country_code, SUM(o.total_gbp) AS revenue FROM orders o "
      "JOIN customers c ON c.customer_id=o.customer_id GROUP BY c.country_code")
_B = ("select c.country_code, sum(o.total_gbp) as total from orders o "
      "join customers c on o.customer_id = c.customer_id group by c.country_code")
_C = "SELECT country_code, COUNT(*) FROM customers GROUP BY country_code"


def test_ast_match_ignores_alias_format_case_and_commutativity():
    assert sql_ast_match(_A, _B) is True


def test_ast_match_rejects_different_logic():
    assert sql_ast_match(_A, _C) is False


def test_ast_match_handles_unparseable_sql_gracefully():
    assert sql_ast_match("this is not sql", "neither is this") is False
    assert canonicalize_sql("@@@") is None


def test_structural_similarity_bounds():
    assert sql_structural_similarity(_A, _B) == 1.0
    assert 0.0 < sql_structural_similarity(_A, _C) < 1.0


def test_ast_match_metric_in_compute():
    cases = [
        _case(execution_match=True, ast_match=True),
        _case(execution_match=False, ast_match=True),
    ]
    metrics = {m.name: m.value for m in compute_metrics(cases)}
    assert metrics["ast_match"] == 1.0
