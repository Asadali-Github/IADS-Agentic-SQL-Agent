"""API routes: /query, /health.

Owner: Mehdi
Status: implemented — stub orchestrator until Omar wires the real one.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException

from sql_agent.api.schemas import HealthResponse, QueryRequest, QueryResponse

router = APIRouter()

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
        # OMAR: swap the line below with your real call:
        #   result = _orchestrator.run(request.question, session_id)
        #   return QueryResponse(**result)
        return _stub_orchestrator(request.question, session_id)
    except Exception as exc:  # noqa: BLE001
        # OMAR: once core/exceptions.py is defined, catch typed exceptions here
        # and return a specific friendly message for each one instead of the
        # generic fallback below. e.g.:
        #   except OutOfScopeError:
        #       return QueryResponse(answer="", error="That question is outside...", ...)
        return QueryResponse(
            answer="",
            error=f"Something went wrong: {exc}",
            session_id=session_id,
        )


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness check."""
    return HealthResponse()

