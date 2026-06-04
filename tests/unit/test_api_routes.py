"""Unit tests for API response mapping."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from sql_agent.api.routes import _to_query_response


def test_action_decider_clarification_is_not_mapped_to_error() -> None:
    result = {
        "original_question": "Sort them ascendingly",
        "resolved_question": "Sort them ascendingly",
        "retrieved_documents": [],
        "retrieval_provider": "not_run_action_decider",
        "support_assessment": {"is_supported": True},
        "generated_sql": {
            "sql": None,
            "clarification_question": (
                "Do you want me to use the previous result, modify the previous SQL, "
                "or run a new query?"
            ),
            "reasoning": "SQL generation skipped by action decision.",
            "provider": "action_decider",
            "error": None,
        },
        "sql_validation": {"is_valid": False, "reason": "No SQL was generated."},
        "query_results": {"status": "skipped", "rows": [], "row_count": 0},
        "answer": {
            "answer": "No previous result is available to transform.",
            "provider": "action_decider",
            "error": None,
        },
        "suggestions": [],
        "pipeline_stage": "action_decision_asked_clarification",
    }

    response = _to_query_response(result, "session-1")

    assert response.error is None
    assert response.answer == "No previous result is available to transform."
    assert response.clarification is not None


def test_api_maps_followup_suggestions() -> None:
    result = {
        "generated_sql": {"sql": "SELECT 1 FROM dual", "provider": "fake"},
        "sql_validation": {"is_valid": True},
        "query_results": {"status": "success", "rows": [{"VALUE": 1}], "row_count": 1},
        "answer": {"answer": "Done", "provider": "fake"},
        "suggestions": [
            {
                "label": "Explain",
                "question": "Explain this result",
                "type": "TRANSFORM_PREVIOUS_RESULT",
            }
        ],
        "pipeline_stage": "sql_executed_successfully",
    }

    response = _to_query_response(result, "session-1")

    assert response.suggestions == [
        {
            "label": "Explain",
            "question": "Explain this result",
            "type": "TRANSFORM_PREVIOUS_RESULT",
        }
    ]
