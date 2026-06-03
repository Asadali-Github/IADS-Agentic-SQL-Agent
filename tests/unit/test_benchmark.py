"""Tests for evaluation/benchmark.py."""

from __future__ import annotations

import json

import pytest

from evaluation.benchmark import (
    AgentRunOutput,
    load_golden,
    make_stub_agent,
    run_benchmark,
    save_result,
    score_case,
)
from sql_agent.core.models import GoldenQuery


def _golden() -> list[GoldenQuery]:
    return [
        GoldenQuery(id="q1", question="count", difficulty="easy",
                    expected_sql="SELECT COUNT(*) FROM customers", expected_rows=[[42]],
                    expected_tables=["customers"]),
        GoldenQuery(id="q2", question="top", difficulty="hard",
                    expected_sql="SELECT ... ORDER BY x", expected_rows=[["a", 1], ["b", 2]],
                    order_matters=True, expected_tables=["orders"]),
    ]


def test_stub_agent_perfect_run_passes_everything():
    result = run_benchmark(make_stub_agent(correct=True), golden=_golden())
    assert result.n_questions == 2
    assert result.n_passed == 2
    assert result.pass_rate == 1.0
    assert result.metric("execution_accuracy").value == 1.0


def test_stub_agent_miss_fails_everything():
    result = run_benchmark(make_stub_agent(correct=False), golden=_golden())
    assert result.n_passed == 0
    assert result.pass_rate == 0.0


def test_order_sensitive_case_fails_on_wrong_order():
    g = _golden()
    def agent(q):  # returns q2's rows reversed
        return AgentRunOutput(sql="x", rows=list(reversed(q.expected_rows)))
    result = run_benchmark(agent, golden=g)
    # q1 (single scalar) passes, q2 (order_matters) fails on reversed rows.
    by_id = {c.question_id: c for c in result.cases}
    assert by_id["q1"].passed is True
    assert by_id["q2"].passed is False


def test_crashing_agent_is_a_failed_case_not_a_crash():
    def boom(q):
        raise RuntimeError("model exploded")
    result = run_benchmark(boom, golden=_golden())
    assert result.n_passed == 0
    assert all("model exploded" in (c.error or "") for c in result.cases)


def test_score_case_partial_match():
    g = _golden()[1]
    out = AgentRunOutput(sql="x", rows=[["a", 1]])  # 1 of 2 expected rows
    case = score_case(g, out, latency_ms=5.0)
    assert case.partial_match == 0.5
    assert case.execution_match is False


def test_load_golden_skips_blanks_and_comments(tmp_path):
    p = tmp_path / "g.jsonl"
    p.write_text(
        "# a comment\n\n"
        + json.dumps({"id": "q1", "question": "hi", "expected_sql": "SELECT 1",
                      "expected_rows": [[1]]}) + "\n",
        encoding="utf-8",
    )
    rows = load_golden(p)
    assert len(rows) == 1
    assert rows[0].id == "q1"


def test_load_golden_raises_on_bad_row(tmp_path):
    p = tmp_path / "bad.jsonl"
    p.write_text('{"id": "q1"}\n', encoding="utf-8")  # missing required fields
    with pytest.raises(ValueError):
        load_golden(p)


def test_save_result_writes_json(tmp_path):
    result = run_benchmark(make_stub_agent(True), golden=_golden())
    out = save_result(result, results_dir=tmp_path)
    assert out.exists()
    data = json.loads(out.read_text())
    assert data["run_id"] == result.run_id
    assert data["n_passed"] == 2


def test_real_golden_file_loads_and_has_tiers():
    rows = load_golden()
    assert len(rows) >= 20
    tiers = {r.difficulty.value for r in rows}
    assert {"easy", "medium", "hard"} <= tiers


# --- realistic mock agent ---------------------------------------------------
from evaluation.benchmark import make_mock_agent  # noqa: E402


def test_mock_agent_is_deterministic():
    g = _golden()
    a = run_benchmark(make_mock_agent(seed=42), golden=g)
    b = run_benchmark(make_mock_agent(seed=42), golden=g)
    assert a.n_passed == b.n_passed
    assert [c.passed for c in a.cases] == [c.passed for c in b.cases]


def test_mock_agent_exercises_full_metric_surface():
    # Over a reasonable number of cases the mock should produce real latency,
    # cost and (likely) some retries so every metric is populated.
    g = [GoldenQuery(id=f"q{i}", question="x", difficulty="medium",
                     expected_sql="SELECT 1 FROM dual", expected_rows=[[i]],
                     expected_tables=["dual"]) for i in range(30)]
    res = run_benchmark(make_mock_agent(seed=1, accuracy=0.8), golden=g)
    assert res.metric("latency_p50_ms").value > 0
    assert res.metric("latency_p95_ms").value >= res.metric("latency_p50_ms").value
    assert res.metric("token_cost_per_request_usd").value > 0
    assert 0.0 <= res.metric("retry_rate").value <= 1.0
    assert 0.0 < res.pass_rate < 1.0  # imperfect by construction
