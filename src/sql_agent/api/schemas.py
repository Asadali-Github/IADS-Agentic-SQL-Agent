"""Request/response Pydantic models for the API.

Owner: Mehdi
Status: implemented.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    """Payload sent by the frontend for every user question."""

    question: str = Field(..., min_length=1, max_length=2000)
    session_id: str | None = Field(
        default=None,
        description="Opaque token the frontend echoes back to maintain multi-turn context.",
    )


class QueryResponse(BaseModel):
    """
    Full response returned to the frontend after the pipeline runs.

    OMAR: your orchestrator.run() must return a dict matching these fields.
    ASAD: fill in `sql`, `explanation`, and `tables_used` from your summariser output.
    All fields have defaults so you only need to set what your stage produces.
    """

    # Core answer
    answer: str = Field(..., description="One-sentence direct answer to the user's question.")
    rows: list[dict] = Field(default_factory=list, description="Result rows as a list of dicts.")
    sql: str = Field(default="", description="The SQL query that produced the result.")

    # Explainability
    explanation: str = Field(
        default="",
        description="Plain-English breakdown of how the SQL was constructed.",
    )
    tables_used: list[str] = Field(
        default_factory=list,
        description="Table names touched by the query.",
    )

    # Enrichment — computed by the summariser
    insights: list[str] = Field(
        default_factory=list,
        description="Deterministic business insights derived from the result rows.",
    )
    chart: Optional[dict[str, Any]] = Field(
        default=None,
        description="Chart spec: {type, x, y, title, reason}. None means no chart.",
    )
    clarification: Optional[str] = Field(
        default=None,
        description="Clarifying question when the query term is ambiguous.",
    )

    # Quality signals
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Critic confidence score. Below 0.7 the UI shows a warning.",
    )
    approximate_match: bool = Field(
        default=False,
        description="True when the row-fallback path returned semantically similar rows.",
    )

    # Error path — None means success
    error: str | None = Field(
        default=None,
        description="Friendly error message. Set only when the pipeline could not answer.",
    )

    # Session continuity
    session_id: str | None = Field(
        default=None,
        description="Echo of the request session_id, or a new token if one was not provided.",
    )


class HealthResponse(BaseModel):
    """Response for GET /health."""

    status: str = "ok"
    version: str = "0.1.0"
    database: str = "unknown"
