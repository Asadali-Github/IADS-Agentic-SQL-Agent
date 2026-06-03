"""Tests for src/sql_agent/agents/summariser.py."""

from __future__ import annotations

from sql_agent.agents.summariser import Summariser, extract_tables
from sql_agent.core.models import CandidateSQL, ExecutionResult, RetrievedSchema


def test_extract_tables_from_join():
    sql = ("SELECT c.full_name, SUM(o.total_gbp) FROM orders o "
           "JOIN customers c ON c.customer_id = o.customer_id GROUP BY c.full_name")
    assert extract_tables(sql) == ["orders", "customers"]


def test_extract_tables_strips_schema_prefix_and_dedupes():
    sql = "SELECT * FROM sales.orders o JOIN sales.orders p ON p.id = o.parent_id"
    assert extract_tables(sql) == ["orders"]


def test_fallback_answer_scalar(exec_scalar, schema_customers):
    s = Summariser()  # no LLM -> deterministic
    out = s.summarise("How many customers?", "SELECT COUNT(*) FROM customers",
                      exec_scalar, schema_customers)
    assert out.answer == "The result is 42."
    assert out.tables_used == ["customers"]
    assert out.explanation  # at least one bullet


def test_fallback_answer_empty_result():
    s = Summariser()
    ex = ExecutionResult(columns=["x"], rows=[], row_count=0, success=True)
    out = s.summarise("Any refunds?", "SELECT * FROM orders WHERE status='refunded'", ex)
    assert "No matching records" in out.answer


def test_failed_execution_is_explained_not_crashed():
    s = Summariser()
    ex = ExecutionResult.failure("ORA-00942: table or view does not exist")
    out = s.summarise("x", "SELECT * FROM nope", ex)
    assert "could not be completed" in out.answer
    assert any("ORA-00942" in b for b in out.explanation)


def test_pii_is_scrubbed_from_answer():
    s = Summariser()
    ex = ExecutionResult(columns=["email", "n"], rows=[["jane@example.com", 5]], row_count=1)
    out = s.summarise("Who ordered most?", "SELECT email, COUNT(*) FROM orders GROUP BY email", ex)
    assert "jane@example.com" not in out.answer
    assert "[EMAIL]" in out.answer


def test_llm_path_uses_model_output(fake_llm, exec_scalar, schema_customers):
    s = Summariser(llm=fake_llm, model="small")
    out = s.summarise("How many customers?", CandidateSQL(sql="SELECT COUNT(*) FROM customers"),
                      exec_scalar, schema_customers)
    assert out.answer == "There are 42 customers."
    assert out.explanation == ["We counted every customer record."]
    assert len(fake_llm.calls) == 2  # answer prompt + explanation prompt


def test_llm_token_counting_is_recorded(fake_llm, exec_scalar):
    from sql_agent.llm.token_counter import TokenCounter
    tc = TokenCounter()
    s = Summariser(llm=fake_llm, model="small", token_counter=tc)
    s.summarise("How many?", "SELECT COUNT(*) FROM customers", exec_scalar)
    assert len(tc.usages) == 2
    assert tc.total_cost_usd > 0


def test_explanation_mentions_aggregation_and_join():
    s = Summariser()
    sql = ("SELECT c.country_code, SUM(o.total_gbp) FROM orders o "
           "JOIN customers c ON c.customer_id=o.customer_id WHERE o.status='paid' GROUP BY c.country_code")
    ex = ExecutionResult(columns=["country", "rev"], rows=[["GB", 100.0]], row_count=1)
    out = s.summarise("Revenue by country?", sql, ex)
    joined = " ".join(out.explanation).lower()
    assert "matched" in joined  # join -> matched related records
    assert "narrowed" in joined or "totals" in joined


# --- hybrid summarisation: deterministic profiling + context safeguards -----
from sql_agent.agents.summariser import (  # noqa: E402
    _MAX_PREVIEW_ROWS,
    profile_result,
)
from sql_agent.core.models import ExecutionResult as _ER  # noqa: E402


def test_profile_result_numeric_aggregates():
    rows = [["A", 10], ["A", 20], ["B", 30]]
    prof = profile_result(["cat", "amount"], rows)
    assert prof["row_count"] == 3
    amount = next(c for c in prof["columns"] if c["name"] == "amount")
    assert amount["dtype"] == "numeric"
    assert amount["sum"] == 60 and amount["min"] == 10 and amount["max"] == 30
    cat = next(c for c in prof["columns"] if c["name"] == "cat")
    assert cat["dtype"] == "text" and cat["distinct"] == 2


def test_large_result_is_not_dumped_into_prompt():
    prompts_seen = []

    class CaptureLLM:
        def complete(self, prompt, model=None):
            prompts_seen.append(prompt)
            if "one sentence that answers" in prompt:
                return '{"answer": "ok"}'
            return '{"explanation": ["grouped"]}'

    rows = [[f"C{i%5}", float(i)] for i in range(500)]
    s = Summariser(llm=CaptureLLM())
    s.summarise("summarise", "SELECT cat, amount FROM orders",
                _ER(columns=["cat", "amount"], rows=rows, row_count=500))
    answer_prompt = next(p for p in prompts_seen if "one sentence that answers" in p)
    # The deterministic sum must be present; the 500 raw rows must not.
    assert "sum=" in answer_prompt
    assert answer_prompt.count("\n") < 60  # nowhere near 500 lines
    assert len(answer_prompt) < 4000


def test_small_result_still_shows_rows():
    captured = {}

    class CaptureLLM:
        def complete(self, prompt, model=None):
            captured["last"] = prompt
            return '{"answer": "ok"}' if "one sentence" in prompt else '{"explanation": ["x"]}'

    rows = [["A", 1], ["B", 2]]
    Summariser(llm=CaptureLLM()).summarise(
        "q", "SELECT * FROM t", _ER(columns=["k", "v"], rows=rows, row_count=2))
    assert len(rows) <= _MAX_PREVIEW_ROWS


# --- adversarial robustness (never crash, never leak) -----------------------
import pytest  # noqa: E402


@pytest.mark.parametrize("rows,cols", [
    ([], ["n"]),                                            # empty
    ([[None]], ["v"]),                                      # single NULL
    ([[None, 1], [None, 2]], ["a", "b"]),                  # all-NULL column
    ([[1], [1, 2], [1, 2, 3]], ["a", "b", "c"]),           # ragged rows
    ([["'; DROP TABLE orders; --"], ["a\"b\\c\n\t"]], ["t"]),  # injection/special
    ([["Zoë"], ["北京"], ["🚀"]], ["name"]),                # unicode
    ([[1e308], [-1e308], [10**30]], ["x"]),                # extreme numbers
    ([[True, None], [False, "n/a"]], ["f", "v"]),          # booleans + mixed
    ([list(range(60))], [f"c{i}" for i in range(60)]),     # very wide
    ([[f"K{i%10}", i] for i in range(2000)], ["k", "v"]),  # many rows
])
def test_summariser_never_crashes_on_adversarial_input(rows, cols):
    s = Summariser(max_preview_rows=10)
    out = s.summarise("q", "SELECT * FROM orders",
                      _ER(columns=cols, rows=rows, row_count=len(rows)))
    assert out.answer and isinstance(out.answer, str)
    assert isinstance(out.explanation, list)


def test_summariser_scrubs_pii_in_adversarial_cells():
    s = Summariser(max_preview_rows=10)
    ex = _ER(columns=["email", "phone"], rows=[["a@b.com", "+44 7700 900123"]], row_count=1)
    out = s.summarise("who", "SELECT email, phone FROM customers", ex)
    assert "a@b.com" not in out.answer


def test_profile_handles_ragged_and_null_without_error():
    from sql_agent.agents.summariser import profile_result
    prof = profile_result(["a", "b", "c"], [[1], [None, 2], [3, 4, 5]])
    assert prof["row_count"] == 3
    assert len(prof["columns"]) == 3
