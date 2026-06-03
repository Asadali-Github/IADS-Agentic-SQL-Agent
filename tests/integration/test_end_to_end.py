"""End-to-end integration tests — full HTTP round-trip through the API stack.

Owner: Mehdi
Status: implemented against the stub orchestrator.
         Re-runs automatically against the real orchestrator once Omar wires it in.

These tests use FastAPI's TestClient, which runs the full ASGI stack in-process
(middleware, routing, validation, serialisation) without needing a live server.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sql_agent.api.main import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# Full round-trip — question in, structured answer out
# ---------------------------------------------------------------------------

def test_full_round_trip_returns_answer() -> None:
    """A well-formed question must produce a non-empty answer."""
    resp = client.post("/query", json={"question": "What were total UK sales last quarter?"})
    assert resp.status_code == 200
    assert resp.json()["answer"] != ""


def test_full_round_trip_returns_rows() -> None:
    """A well-formed question must return at least one result row."""
    resp = client.post("/query", json={"question": "Show me sales by category."})
    assert resp.status_code == 200
    assert len(resp.json()["rows"]) > 0


def test_full_round_trip_returns_sql() -> None:
    """The response must include the SQL that produced the result."""
    resp = client.post("/query", json={"question": "Top 5 customers by revenue."})
    assert resp.status_code == 200
    assert resp.json()["sql"].strip() != ""


def test_full_round_trip_returns_explanation() -> None:
    """The response must include a plain-English explanation."""
    resp = client.post("/query", json={"question": "Compare monthly order volumes."})
    assert resp.status_code == 200
    assert resp.json()["explanation"].strip() != ""


def test_full_round_trip_no_error_on_valid_question() -> None:
    """A valid question must not produce an error field."""
    resp = client.post("/query", json={"question": "How many orders were placed in 2025?"})
    assert resp.status_code == 200
    assert resp.json()["error"] is None


# ---------------------------------------------------------------------------
# Multi-turn conversation — session continuity
# ---------------------------------------------------------------------------

def test_session_id_persists_across_turns() -> None:
    """The session_id returned on turn 1 must be accepted and echoed on turn 2."""
    turn1 = client.post("/query", json={"question": "Show me total sales."})
    sid = turn1.json()["session_id"]
    assert sid is not None

    turn2 = client.post("/query", json={"question": "Break that down by region.", "session_id": sid})
    assert turn2.status_code == 200
    assert turn2.json()["session_id"] == sid


def test_each_new_conversation_gets_unique_session_id() -> None:
    """Two independent questions (no session_id) must get different session IDs."""
    r1 = client.post("/query", json={"question": "Total sales?"})
    r2 = client.post("/query", json={"question": "Total orders?"})
    assert r1.json()["session_id"] != r2.json()["session_id"]


# ---------------------------------------------------------------------------
# Response contract — shape the UI depends on
# ---------------------------------------------------------------------------

def test_response_contains_all_ui_fields() -> None:
    """All fields that streamlit_app.py reads must be present."""
    resp = client.post("/query", json={"question": "Show revenue by product."})
    data = resp.json()
    required = {"answer", "rows", "sql", "explanation", "tables_used",
                "confidence", "approximate_match", "error", "session_id"}
    assert required.issubset(data.keys())


def test_confidence_is_float_in_range() -> None:
    resp = client.post("/query", json={"question": "Top customers?"})
    c = resp.json()["confidence"]
    assert isinstance(c, float)
    assert 0.0 <= c <= 1.0


def test_approximate_match_is_bool() -> None:
    resp = client.post("/query", json={"question": "Any returns last month?"})
    assert isinstance(resp.json()["approximate_match"], bool)


def test_tables_used_is_list() -> None:
    resp = client.post("/query", json={"question": "Sales by region?"})
    assert isinstance(resp.json()["tables_used"], list)


# ---------------------------------------------------------------------------
# Health check — liveness
# ---------------------------------------------------------------------------

def test_health_check_end_to_end() -> None:
    """Stack must report healthy before any query is processed."""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

