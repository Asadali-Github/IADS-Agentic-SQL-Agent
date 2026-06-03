"""Unit tests for planner and reflector fallback behavior."""

from __future__ import annotations

from app.agents.planner import QueryPlanner
from app.agents.reflector import QueryReflector


def test_planner_returns_single_step_for_simple_question() -> None:
    planner = QueryPlanner(profile_name="")

    plan = planner.plan("What are total sales?", [])

    assert plan["type"] == "single_step"
    assert plan["steps"] == ["What are total sales?"]
    assert plan["provider"] == "local"


def test_planner_falls_back_when_complex_without_profile() -> None:
    planner = QueryPlanner(profile_name="")

    plan = planner.plan("Why did sales decline?", [])

    assert plan["type"] == "single_step"
    assert plan["provider"] == "local"
    assert plan["error"] == "SELECT_AI_PROFILE is not set."


def test_reflector_returns_ok_when_no_issue() -> None:
    reflector = QueryReflector(profile_name="")

    reflection = reflector.reflect(
        question="What are total sales?",
        generated_sql={"sql": "SELECT 1 FROM dual"},
        query_results={"status": "success", "rows": [{"VALUE": 1}]},
        retrieved_documents=[],
    )

    assert reflection == {
        "ok": True,
        "issue": None,
        "corrected_sql": None,
        "provider": "local",
        "error": None,
    }


def test_reflector_reports_issue_without_profile() -> None:
    reflector = QueryReflector(profile_name="")

    reflection = reflector.reflect(
        question="What are total sales?",
        generated_sql={"sql": None},
        query_results={"status": "skipped", "rows": []},
        retrieved_documents=[],
    )

    assert reflection["ok"] is False
    assert reflection["issue"] == "no_sql_generated"
    assert reflection["corrected_sql"] is None
    assert reflection["provider"] == "local"
