"""Unit tests for shared evaluation reflection helpers."""

from __future__ import annotations

from evaluation.metrics import detect_issue, reflect


def test_detect_issue_flags_missing_sql() -> None:
    result = {"generated_sql": {"sql": None}, "query_results": {"status": "skipped"}}

    assert detect_issue(result) == "no_sql_generated"
    assert reflect(result) == {"ok": False, "issue": "no_sql_generated"}


def test_detect_issue_flags_execution_error() -> None:
    result = {
        "generated_sql": {"sql": "SELECT 1 FROM dual"},
        "query_results": {"status": "error"},
    }

    assert detect_issue(result) == "sql_execution_failed"


def test_detect_issue_flags_zero_rows() -> None:
    result = {
        "generated_sql": {"sql": "SELECT 1 FROM dual"},
        "query_results": {"status": "success", "rows": []},
    }

    assert detect_issue(result) == "zero_rows_returned"


def test_detect_issue_allows_successful_rows() -> None:
    result = {
        "generated_sql": {"sql": "SELECT 1 FROM dual"},
        "query_results": {"status": "success", "rows": [{"VALUE": 1}]},
    }

    assert detect_issue(result) is None
    assert reflect(result) == {"ok": True, "issue": None}
