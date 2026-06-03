"""Execution accuracy, exact-match, retry rate metrics.

Owner: Aneesh + Asad
Status: placeholder — implement during the hackathon.

TODO:
- Define the public interface here
- Implement the logic
- Write tests in tests/unit/test_metrics.py
"""

from __future__ import annotations


def detect_issue(result: dict) -> str | None:
    """Return a retry-worthy issue code for an agent result, if one exists."""
    generated_sql = result.get("generated_sql") or {}
    query_results = result.get("query_results") or {}

    if not generated_sql.get("sql"):
        return "no_sql_generated"
    if query_results.get("status") == "error":
        return "sql_execution_failed"
    if query_results.get("status") == "success" and not (query_results.get("rows") or []):
        return "zero_rows_returned"
    return None


def reflect(result: dict) -> dict:
    """Shared evaluator reflection check."""
    issue = detect_issue(result)
    return {"ok": issue is None, "issue": issue}
