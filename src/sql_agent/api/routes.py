"""API routes: /query, /health.

Owner: Mehdi
Status: implemented — stub orchestrator until Omar wires the real one.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException

from sql_agent.api.schemas import HealthResponse, QueryRequest, QueryResponse
from sql_agent.core.exceptions import (
    DatabaseError,
    LLMError,
    QueryParseError,
    RateLimitError,
    ServiceUnavailableError,
    TimeoutError,
)

router = APIRouter()

# Integration (Asad): the production selector picks the LIVE Oracle backend
# (QueryOrchestrator: ADB + Select AI + 23ai vector) when OCI is configured, and
# the offline DuckDB pipeline otherwise. Imported defensively so the API still
# boots (falling back to the stub) if optional deps are missing.
try:  # pragma: no cover - import guarded
    from app.production_pipeline import answer_question as _pipeline_answer
except Exception:  # noqa: BLE001
    try:
        from app.pipeline import answer_question as _pipeline_answer
    except Exception:  # noqa: BLE001
        _pipeline_answer = None


def _pipeline_query(question: str, session_id: str) -> QueryResponse:
    """Run the full pipeline and map its result onto QueryResponse."""
    r = _pipeline_answer(question, session_id)  # type: ignore[misc]
    explanation = r.get("explanation", "")
    if r.get("insights"):
        explanation = (explanation + "\n\nKey insights:\n- "
                       + "\n- ".join(r["insights"])).strip()
    return QueryResponse(
        answer=r.get("answer", ""),
        rows=r.get("rows", []),
        sql=r.get("sql", ""),
        explanation=explanation,
        tables_used=r.get("tables_used", []),
        confidence=float(r.get("confidence", 1.0) or 0.0),
        approximate_match=bool(r.get("approximate_match", False)),
        error=r.get("error"),
        session_id=session_id,
    )

# ---------------------------------------------------------------------------
# Stub orchestrator — replace this one call with the real orchestrator once
# Omar's implementation is ready:
#
#   from sql_agent.agents.orchestrator import Orchestrator
#   _orchestrator = Orchestrator()
#
# Then in /query:
#   result = _orchestrator.run(request.question, request.session_id)
#   return QueryResponse(**result)
# ---------------------------------------------------------------------------

def _stub_orchestrator(question: str, session_id: str) -> QueryResponse:
    """Returns a hardcoded response so the UI can be built and tested now."""
    return QueryResponse(
        answer=f'(Stub) You asked: "{question}"',
        rows=[
            {"region": "UK", "total_sales": 4200000, "category": "Electronics"},
            {"region": "UK", "total_sales": 3100000, "category": "Clothing"},
            {"region": "UK", "total_sales": 1800000, "category": "Food"},
        ],
        sql="SELECT region, category, SUM(sales) AS total_sales\nFROM orders\nWHERE region = 'UK'\nGROUP BY region, category\nORDER BY total_sales DESC;",
        explanation="I filtered the orders table to the UK region and grouped the results by product category, summing the sales column.",
        tables_used=["orders"],
        confidence=0.92,
        approximate_match=False,
        error=None,
        session_id=session_id,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/query", response_model=QueryResponse)
def query(request: QueryRequest) -> QueryResponse:
    """Accept a natural-language question and return a structured answer."""
    session_id = request.session_id or str(uuid.uuid4())
    try:
        if _pipeline_answer is not None:
            return _pipeline_query(request.question, session_id)
        # Fallback: stub response if the pipeline could not be imported.
        return _stub_orchestrator(request.question, session_id)
    except QueryParseError:
        return QueryResponse(
            answer="",
            error="I understood your question, but our current system doesn't track that. Try asking about sales, orders, customers, or products.",
            session_id=session_id,
        )
    except TimeoutError:
        return QueryResponse(
            answer="",
            error="Your question needed more time than I have available. Try a simpler question.",
            session_id=session_id,
        )
    except DatabaseError:
        return QueryResponse(
            answer="",
            error="There was a problem querying the database. Please try again in a moment.",
            session_id=session_id,
        )
    except LLMError:
        return QueryResponse(
            answer="",
            error="The AI service returned an error. Please try again.",
            session_id=session_id,
        )
    except RateLimitError:
        return QueryResponse(
            answer="",
            error="Too many requests. Please wait a moment and try again.",
            session_id=session_id,
        )
    except ServiceUnavailableError:
        return QueryResponse(
            answer="",
            error="The service is temporarily unavailable. Please try again shortly.",
            session_id=session_id,
        )
    except Exception as exc:  # noqa: BLE001
        return QueryResponse(
            answer="",
            error=f"Something went wrong: {exc}",
            session_id=session_id,
        )


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness check."""
    return HealthResponse()

