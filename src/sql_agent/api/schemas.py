"""Request and response models for the chatbot API."""

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
    resolved_question: Optional[str] = Field(
        default=None,
        description="The resolved question after rewriting follow-ups, or the original question if standalone.",
    )
    important_numbers: list[str] = Field(
        default_factory=list,
        description="Key numbers, totals, or aggregates extracted from the results.",
    )
    trends_anomalies: list[str] = Field(
        default_factory=list,
        description="Major trend shifts, growths, declines, or outlier anomalies.",
    )
    final_takeaway: Optional[str] = Field(
        default=None,
        description="A plain-English actionable conclusion/takeaway for a business manager.",
    )
    rows: list[dict] = Field(default_factory=list, description="Result rows as a list of dicts.")
    sql: str = Field(default="", description="The SQL query that produced the result.")

    # Explainability — two forms for flexibility
    explanation: str = Field(
        default="",
        description="Plain-English breakdown as a single string (newline-joined bullets).",
    )
    explanation_bullets: list[str] = Field(
        default_factory=list,
        description="Same breakdown as an ordered list of bullet strings — preferred for UI rendering.",
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

    # Provenance
    provider: Optional[str] = Field(
        default=None,
        description="Which backend generated the SQL: oracle_select_ai | offline_cache | offline_template.",
    )
    latency_ms: Optional[float] = Field(
        default=None,
        description="End-to-end query execution time in milliseconds.",
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


class SuggestionItem(BaseModel):
    """A single suggested question."""

    label: str
    question: str
    tags: list[str] = Field(default_factory=list)


class SuggestionsResponse(BaseModel):
    """Suggested questions for the UI 'try one of these' buttons."""

    suggestions: list[SuggestionItem]


class HealthResponse(BaseModel):
    """Response for GET /health."""

    status: str = "ok"
    version: str = "0.1.0"
    database: str = "unknown"
