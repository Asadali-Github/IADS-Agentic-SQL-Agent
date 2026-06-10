"""Unit tests for structured next-action decisions."""

from __future__ import annotations

from app.agents.action_decider import QueryActionDecider


def _state(has_previous_result: bool = True, has_previous_sql: bool = True) -> dict:
    return {
        "has_previous_result": has_previous_result,
        "has_previous_sql": has_previous_sql,
        "last_question": "List the top five products by revenue",
        "last_sql": "SELECT ...",
        "last_columns": ["PRODUCT_NAME", "TOTAL_REVENUE"],
        "last_row_count": 5,
    }


def test_decider_transforms_sort_request() -> None:
    decider = QueryActionDecider(profile_name="")

    decision = decider.decide_next_action("Sort them ascendingly", _state())

    assert decision["action"] == "TRANSFORM_PREVIOUS_RESULT"
    assert decision["needs_sql"] is False
    assert decision["uses_previous_result"] is True


def test_decider_runs_new_sql_for_new_customer_question() -> None:
    decider = QueryActionDecider(profile_name="")

    decision = decider.decide_next_action("Show top customers by revenue", _state())

    assert decision["action"] == "RUN_NEW_SQL"
    assert decision["needs_sql"] is True


def test_decider_modifies_previous_sql_for_year_constraint() -> None:
    decider = QueryActionDecider(profile_name="")

    decision = decider.decide_next_action("For 2024 only", _state())

    assert decision["action"] == "MODIFY_PREVIOUS_SQL"
    assert decision["uses_previous_sql"] is True


def test_decider_refresh_executes_sql() -> None:
    decider = QueryActionDecider(profile_name="")

    decision = decider.decide_next_action("Refresh the result", _state())

    assert decision["action"] == "MODIFY_PREVIOUS_SQL"
    assert decision["needs_sql"] is True


def test_decider_explains_previous_result() -> None:
    decider = QueryActionDecider(profile_name="")

    decision = decider.decide_next_action("Explain this", _state())

    assert decision["action"] == "TRANSFORM_PREVIOUS_RESULT"


def test_decider_asks_when_transform_has_no_previous_result() -> None:
    decider = QueryActionDecider(profile_name="")

    decision = decider.decide_next_action(
        "Sort them ascendingly",
        _state(has_previous_result=False),
    )

    assert decision["action"] == "ASK_CLARIFICATION"


def test_decider_asks_when_bare_modify_has_no_previous_sql() -> None:
    decider = QueryActionDecider(profile_name="")

    decision = decider.decide_next_action(
        "modify the previous sql",
        _state(has_previous_result=False, has_previous_sql=False),
    )

    assert decision["action"] == "ASK_CLARIFICATION"


def test_decider_asks_when_bare_use_previous_result_has_no_result() -> None:
    decider = QueryActionDecider(profile_name="")

    decision = decider.decide_next_action(
        "use previous result",
        _state(has_previous_result=False, has_previous_sql=False),
    )

    assert decision["action"] == "ASK_CLARIFICATION"
