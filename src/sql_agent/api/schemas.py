"""Request and response models for the chatbot API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    """Payload sent by the frontend for every user question."""

    question: str = Field(..., min_length=1, max_length=2000)
    session_id: str | None = Field(
        default=None,
        description="Opaque token echoed by the frontend to maintain multi-turn context.",
    )
    demo_mode: bool = Field(
        default=False,
        description="Reserved frontend flag for cached-demo execution.",
    )


class QueryResponse(BaseModel):
    """Structured answer returned to the Streamlit chat UI."""

    answer: str = Field(default="", description="Concise answer to the user's question.")
    rows: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Result rows as a list of dictionaries.",
    )
    sql: str = Field(default="", description="The SQL query that produced the result.")
    explanation: str = Field(
        default="",
        description="Plain-English breakdown of how the answer was produced.",
    )
    tables_used: list[str] = Field(
        default_factory=list,
        description="Table names or schema documents used by the query.",
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence score. Below 0.7 the UI shows a warning.",
    )
    approximate_match: bool = Field(
        default=False,
        description="True when fallback rows are returned instead of live execution rows.",
    )
    error: str | None = Field(default=None, description="Friendly error message.")
    session_id: str | None = Field(default=None, description="Conversation session token.")
    insights: list[str] = Field(default_factory=list, description="Optional insight bullets.")
    chart: dict[str, Any] | None = Field(default=None, description="Optional chart hint.")
    clarification: str | None = Field(default=None, description="Optional clarification prompt.")


class HealthResponse(BaseModel):
    """Response for GET /health."""

    status: str = "ok"
    version: str = "0.1.0"
