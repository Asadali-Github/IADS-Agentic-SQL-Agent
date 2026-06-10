"""Unit tests for follow-up suggestion generation."""

from __future__ import annotations

from app.agents.followup_suggester import FollowUpSuggester


def _response() -> dict:
    return {
        "original_question": "List the top five products by revenue",
        "resolved_question": "List the top five products by revenue",
        "generated_sql": {"sql": "SELECT product_name, SUM(revenue) FROM sales"},
        "query_results": {
            "status": "success",
            "columns": ["PRODUCT_NAME", "TOTAL_REVENUE"],
            "rows": [
                {"PRODUCT_NAME": "A", "TOTAL_REVENUE": 100.0},
                {"PRODUCT_NAME": "B", "TOTAL_REVENUE": 50.0},
            ],
            "row_count": 2,
        },
        "retrieved_documents": [],
        "pipeline_stage": "sql_executed_successfully",
    }


def test_suggester_falls_back_without_profile() -> None:
    suggester = FollowUpSuggester(profile_name="")

    suggestions = suggester.suggest(_response())

    assert suggestions
    assert suggestions[0]["type"] == "TRANSFORM_PREVIOUS_RESULT"
    assert any(suggestion["type"] == "MODIFY_PREVIOUS_SQL" for suggestion in suggestions)


def test_suggester_returns_empty_without_rows() -> None:
    suggester = FollowUpSuggester(profile_name="")
    response = _response()
    response["query_results"]["rows"] = []

    assert suggester.suggest(response) == []


def test_suggester_parses_valid_json_only() -> None:
    suggester = FollowUpSuggester(profile_name="")

    suggestions = suggester._parse_suggestions(
        """
        Here:
        {"suggestions": [
          {
            "label": "Sort",
            "question": "Sort these ascendingly",
            "type": "TRANSFORM_PREVIOUS_RESULT"
          },
          {"label": "Bad", "question": "Delete rows", "type": "DELETE"}
        ]}
        """
    )

    assert suggestions == [
        {
            "label": "Sort",
            "question": "Sort these ascendingly",
            "type": "TRANSFORM_PREVIOUS_RESULT",
        }
    ]
