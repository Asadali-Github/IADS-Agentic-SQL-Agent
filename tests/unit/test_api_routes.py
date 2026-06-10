"""Unit tests for FastAPI routes: /query and /health.

Owner: Mehdi
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sql_agent.api.main import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------

def test_health_returns_200() -> None:
    resp = client.get("/health")
    assert resp.status_code == 200


def test_health_payload() -> None:
    resp = client.get("/health")
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data


# ---------------------------------------------------------------------------
# /query — happy path
# ---------------------------------------------------------------------------

def test_query_returns_200() -> None:
    resp = client.post("/query", json={"question": "Show total sales by region."})
    assert resp.status_code == 200


def test_query_response_shape() -> None:
    resp = client.post("/query", json={"question": "Show total sales by region."})
    data = resp.json()
    # Required fields defined in QueryResponse
    assert "answer" in data
    assert "rows" in data
    assert "sql" in data
    assert "confidence" in data
    assert "session_id" in data


def test_query_session_id_echoed() -> None:
    """If the caller supplies a session_id, it must be echoed back."""
    sid = "test-session-abc"
    resp = client.post("/query", json={"question": "How many orders?", "session_id": sid})
    assert resp.json()["session_id"] == sid


def test_query_generates_session_id_when_absent() -> None:
    """If no session_id is supplied, the API must create one."""
    resp = client.post("/query", json={"question": "How many orders?"})
    data = resp.json()
    assert data["session_id"] is not None
    assert len(data["session_id"]) > 0


def test_query_confidence_in_range() -> None:
    resp = client.post("/query", json={"question": "Top 5 customers?"})
    confidence = resp.json()["confidence"]
    assert 0.0 <= confidence <= 1.0


def test_query_rows_is_list() -> None:
    resp = client.post("/query", json={"question": "Top 5 customers?"})
    assert isinstance(resp.json()["rows"], list)


# ---------------------------------------------------------------------------
# /query — validation
# ---------------------------------------------------------------------------

def test_query_rejects_empty_question() -> None:
    """Empty string must fail Pydantic min_length=1 validation → 422."""
    resp = client.post("/query", json={"question": ""})
    assert resp.status_code == 422


def test_query_rejects_missing_question() -> None:
    resp = client.post("/query", json={})
    assert resp.status_code == 422


def test_query_rejects_question_over_2000_chars() -> None:
    resp = client.post("/query", json={"question": "x" * 2001})
    assert resp.status_code == 422


def test_query_accepts_question_at_max_length() -> None:
    resp = client.post("/query", json={"question": "x" * 2000})
    assert resp.status_code == 200
