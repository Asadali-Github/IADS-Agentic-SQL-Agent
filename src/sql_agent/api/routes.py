"""API routes for the Streamlit chatbot."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter

from app.agents.query_orchestrator import QueryOrchestrator
from sql_agent.api.schemas import HealthResponse, QueryRequest, QueryResponse

router = APIRouter()

_SESSION_ORCHESTRATORS: dict[str, QueryOrchestrator] = {}


@router.post("/query", response_model=QueryResponse)
def query(request: QueryRequest) -> QueryResponse:
    """Accept a natural-language question and return a structured chat response."""
    session_id = request.session_id or str(uuid.uuid4())
    orchestrator = _SESSION_ORCHESTRATORS.setdefault(session_id, QueryOrchestrator())

    try:
        result = orchestrator.process_question(request.question)
    except Exception as exc:
        return QueryResponse(
            answer="",
            error=f"Something went wrong while answering the question: {exc}",
            session_id=session_id,
            confidence=0.0,
        )

    return _to_query_response(result, session_id)


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness check used by the Streamlit sidebar."""
    return HealthResponse()


def _to_query_response(result: dict[str, Any], session_id: str) -> QueryResponse:
    answer_payload = result.get("answer") or {}
    generated_sql = result.get("generated_sql") or {}
    sql_validation = result.get("sql_validation") or {}
    query_results = result.get("query_results") or {}
    error = _friendly_error(answer_payload, generated_sql, sql_validation, query_results)
    confidence = _confidence(result)

    return QueryResponse(
        answer=str(answer_payload.get("answer") or ""),
        rows=list(query_results.get("rows") or []),
        sql=str(generated_sql.get("sql") or sql_validation.get("safe_sql") or ""),
        explanation=_explanation(result),
        tables_used=_tables_used(result),
        confidence=confidence,
        approximate_match=query_results.get("status") == "fallback_success",
        error=error,
        session_id=session_id,
        clarification=generated_sql.get("clarification_question"),
        insights=_insights(result),
        chart=_chart_hint(query_results),
    )


def _friendly_error(
    answer_payload: dict[str, Any],
    generated_sql: dict[str, Any],
    sql_validation: dict[str, Any],
    query_results: dict[str, Any],
) -> str | None:
    if generated_sql.get("provider") == "local_no_answer" and answer_payload.get("answer"):
        return None
    if answer_payload.get("error") and not answer_payload.get("answer"):
        return str(answer_payload["error"])
    if generated_sql.get("error"):
        return str(generated_sql["error"])
    if not sql_validation.get("is_valid", True):
        return str(sql_validation.get("reason") or "The generated SQL was not safe to run.")
    if query_results.get("status") == "error":
        return str(
            query_results.get("reason")
            or query_results.get("error")
            or "SQL execution failed."
        )
    return None


def _confidence(result: dict[str, Any]) -> float:
    support_assessment = result.get("support_assessment") or {}
    query_results = result.get("query_results") or {}
    generated_sql = result.get("generated_sql") or {}

    if not support_assessment.get("is_supported", True):
        return 0.2
    if generated_sql.get("error"):
        return 0.35
    if query_results.get("status") == "fallback_success":
        return 0.72
    if query_results.get("status") == "success":
        return 0.92
    return 0.6


def _explanation(result: dict[str, Any]) -> str:
    parts: list[str] = []

    resolved_question = result.get("resolved_question")
    original_question = result.get("original_question")
    if resolved_question and resolved_question != original_question:
        parts.append(f"Resolved follow-up question:\n{resolved_question}")

    retrieval_provider = result.get("retrieval_provider")
    if retrieval_provider:
        parts.append(f"Retrieval provider: {retrieval_provider}")

    support_assessment = result.get("support_assessment") or {}
    if support_assessment.get("reason"):
        parts.append(f"Support check: {support_assessment['reason']}")

    generated_sql = result.get("generated_sql") or {}
    if generated_sql.get("reasoning"):
        parts.append(f"SQL reasoning: {generated_sql['reasoning']}")

    sql_validation = result.get("sql_validation") or {}
    if sql_validation.get("reason"):
        parts.append(f"Validation: {sql_validation['reason']}")

    query_results = result.get("query_results") or {}
    if query_results.get("reason"):
        parts.append(f"Execution: {query_results['reason']}")

    answer_payload = result.get("answer") or {}
    if answer_payload.get("provider"):
        parts.append(f"Answer provider: {answer_payload['provider']}")

    return "\n\n".join(parts)


def _tables_used(result: dict[str, Any]) -> list[str]:
    tables: list[str] = []
    for document in result.get("retrieved_documents") or []:
        title = document.get("title")
        doc_type = document.get("type")
        if title and (doc_type == "table" or not tables):
            tables.append(str(title))
    return list(dict.fromkeys(tables))


def _insights(result: dict[str, Any]) -> list[str]:
    query_results = result.get("query_results") or {}
    rows = query_results.get("rows") or []
    row_count = query_results.get("row_count", len(rows))
    if not rows:
        return []
    return [f"Returned {row_count} row{'s' if row_count != 1 else ''}."]


def _chart_hint(query_results: dict[str, Any]) -> dict[str, Any] | None:
    rows = query_results.get("rows") or []
    if not rows:
        return None

    first_row = rows[0]
    numeric_columns = [
        key
        for key, value in first_row.items()
        if isinstance(value, int | float) and not isinstance(value, bool)
    ]
    label_columns = [key for key in first_row if key not in numeric_columns]

    if numeric_columns and label_columns:
        return {"type": "bar", "x": label_columns[0], "y": numeric_columns[0]}
    return None
