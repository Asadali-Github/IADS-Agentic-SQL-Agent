"""FastAPI application — unified entry point for the IADS Agentic SQL Agent.

Architecture:
    This module is the single FastAPI ``app`` instance. It consolidates:
    * CORS policy
    * Rate limiting middleware
    * Monitoring / metrics middleware (query latency, accuracy, error tracking)
    * The canonical REST router from ``src/sql_agent/api/routes.py``
      (which uses ``ProductionPipeline`` — per-session orchestrators with
       ConversationMemory — or falls back to the offline DuckDB pipeline)
    * Observability endpoints: ``/metrics``, ``/metrics/errors``
    * A CLI ``--chat`` mode for local development / demos

    The earlier version of this file defined its OWN ``/query`` and ``/health``
    endpoints, creating a **new QueryOrchestrator per request** — which destroyed
    conversation memory every call. That duplication has been removed.  The
    canonical router (``routes.py``) now handles ``/query`` and ``/health``.

Owner: Asad / Mehdi (integration glue)
"""

from __future__ import annotations

import json
import sys
import time
import os
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_ROOT), str(_ROOT / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import structlog

from app.monitoring import metrics, logger, Timer

# ---------------------------------------------------------------------------
# Import the canonical router (routes.py handles /query, /health)
# ---------------------------------------------------------------------------
try:
    from sql_agent.api.routes import router as _api_router
except Exception:  # noqa: BLE001
    _api_router = None
    structlog.get_logger().warning("could_not_import_canonical_router")

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(
    title="IADS Agentic SQL Agent",
    version="1.0.0",
    description="AI-powered natural language SQL query agent — multi-stage "
                "agentic pipeline with RAG, Oracle 23ai, Select AI, and "
                "conversational memory.",
)

# ---------------------------------------------------------------------------
# CORS configuration (allow frontend access)
# ---------------------------------------------------------------------------
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://localhost:8501",
).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Rate limiting (simple in-memory, production-ready pattern)
# ---------------------------------------------------------------------------
class RateLimiter:
    """Sliding-window in-memory rate limiter keyed by client IP."""

    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: dict[str, list[float]] = {}

    def is_allowed(self, client_id: str) -> bool:
        now = time.time()
        if client_id not in self.requests:
            self.requests[client_id] = []

        # Remove old requests outside window
        self.requests[client_id] = [
            req_time for req_time in self.requests[client_id]
            if now - req_time < self.window_seconds
        ]

        # Check limit
        if len(self.requests[client_id]) >= self.max_requests:
            return False

        self.requests[client_id].append(now)
        return True


rate_limiter = RateLimiter(max_requests=100, window_seconds=60)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Apply rate limiting to all non-health endpoints."""
    # Get client IP
    client_ip = request.client.host if request.client else "unknown"

    # Skip rate limiting for health checks
    if request.url.path in ["/health", "/"]:
        return await call_next(request)

    if not rate_limiter.is_allowed(client_ip):
        return JSONResponse(
            status_code=429,
            content={"error": "Rate limit exceeded. Max 100 requests per minute."},
        )

    return await call_next(request)


@app.middleware("http")
async def monitoring_middleware(request: Request, call_next):
    """Record latency and error metrics for every /query request."""
    if request.url.path != "/query":
        return await call_next(request)

    start_time = time.time()
    response = await call_next(request)
    latency_ms = (time.time() - start_time) * 1000

    # Log the request
    logger.info(
        f"Query completed ({latency_ms:.0f}ms, status={response.status_code})"
    )

    return response


# ---------------------------------------------------------------------------
# Mount the canonical router (/query, /health)
# ---------------------------------------------------------------------------
if _api_router is not None:
    app.include_router(_api_router)


# ---------------------------------------------------------------------------
# Root endpoint (liveness probe)
# ---------------------------------------------------------------------------
@app.get("/")
def read_root() -> dict:
    """Root health check endpoint."""
    return {"status": "ok", "service": "IADS Agentic SQL Agent"}


# ---------------------------------------------------------------------------
# Observability endpoints
# ---------------------------------------------------------------------------
@app.get("/metrics")
def get_metrics(hours: int = 24) -> dict:
    """Get performance metrics for the last N hours."""
    return metrics.get_stats(hours=hours)


@app.get("/metrics/errors")
def get_recent_errors(limit: int = 10) -> dict:
    """Get recent errors."""
    errors = metrics.get_recent_errors(limit=limit)
    return {
        "total_errors": len(errors),
        "recent_errors": errors,
    }


# ---------------------------------------------------------------------------
# CLI modes (local development / demos)
# ---------------------------------------------------------------------------
def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "--chat":
        run_chat()
        return

    sample_question = "What were total sales by product category?"
    user_question = " ".join(sys.argv[1:]).strip() or sample_question

    from app.agents.query_orchestrator import QueryOrchestrator

    orchestrator = QueryOrchestrator()
    response = orchestrator.process_question(user_question)
    print_response(response)


def run_chat() -> None:
    """Run a tiny CLI chat loop that keeps in-process conversation memory."""
    from app.agents.query_orchestrator import QueryOrchestrator

    orchestrator = QueryOrchestrator()
    print("Oracle SQL Agent chat. Type exit to stop.")
    while True:
        user_question = input("\nQuestion: ").strip()
        if user_question.lower() in {"exit", "quit"}:
            return
        if not user_question:
            continue

        response = orchestrator.process_question(user_question)
        print_response(response)


def print_response(response: dict) -> None:
    """Print the pipeline response in a readable debug format."""
    print("\n=== Original Question ===")
    print(response["original_question"])

    print("\n=== Resolved Question ===")
    print(response["resolved_question"])

    print("\n=== Answer ===")
    print(response["answer"]["answer"])

    print("\n=== Support Assessment ===")
    print(json.dumps(response["support_assessment"], indent=2))

    print("\n=== Retrieved Documents ===")
    print(json.dumps(response["retrieved_documents"], indent=2))

    print("\n=== SQL Generation Prompt ===")
    print(response["sql_generation_prompt"])

    print("\n=== Generated SQL ===")
    print(json.dumps(response["generated_sql"], indent=2))

    print("\n=== SQL Validation ===")
    print(json.dumps(response["sql_validation"], indent=2))

    print("\n=== Query Results ===")
    print(json.dumps(response["query_results"], indent=2, default=str))

    print("\n=== Answer Details ===")
    print(json.dumps(response["answer"], indent=2, default=str))

    print("\n=== Pipeline Stage ===")
    print(response["pipeline_stage"])


if __name__ == "__main__":
    main()
