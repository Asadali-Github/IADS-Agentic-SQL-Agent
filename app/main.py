"""Run a simple RAG-to-SQL-prompt pipeline with placeholder documents."""

from __future__ import annotations

import json
import sys
import time
import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.agents.query_orchestrator import QueryOrchestrator
from app.sql.oracle_connection import connect_adb
from app.monitoring import metrics, logger, Timer

# Initialize app
app = FastAPI(
    title="IADS Agentic SQL Agent",
    version="1.0.0",
    description="AI-powered natural language SQL query agent"
)

# CORS configuration (allow frontend access)
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:8501").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting (simple in-memory)
class RateLimiter:
    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = {}
    
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
    """Apply rate limiting to requests."""
    # Get client IP
    client_ip = request.client.host if request.client else "unknown"
    
    # Skip rate limiting for health checks
    if request.url.path in ["/health", "/"]:
        return await call_next(request)
    
    if not rate_limiter.is_allowed(client_ip):
        return JSONResponse(
            status_code=429,
            content={"error": "Rate limit exceeded. Max 100 requests per minute."}
        )
    
    return await call_next(request)


class QueryRequest(BaseModel):
    question: str


@app.get("/")
def read_root() -> dict:
    """Health check endpoint."""
    return {"status": "ok", "service": "IADS Agentic SQL Agent"}


@app.get("/health")
def health_check() -> dict:
    """Check API and database health."""
    try:
        connection = connect_adb()
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM dual")
        connection.close()
        return {"status": "healthy", "database": "connected"}
    except Exception as exc:
        return {"status": "unhealthy", "database": "disconnected", "error": str(exc)}


@app.post("/query")
def process_query(request: QueryRequest) -> dict:
    """Process a natural language question and return SQL results."""
    # Validate input
    if not request.question or not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")
    
    if len(request.question) > 1000:
        raise HTTPException(status_code=400, detail="Question too long (max 1000 characters)")
    
    start_time = time.time()
    error_msg = None
    
    try:
        with Timer("query_processing"):
            orchestrator = QueryOrchestrator()
            response = orchestrator.process_question(request.question)
        
        latency_ms = (time.time() - start_time) * 1000
        accuracy = response.get("confidence", 1.0)
        rows_returned = len(response.get("rows", []))
        
        # Record metrics
        metrics.record_query(
            question=request.question,
            latency_ms=latency_ms,
            accuracy=accuracy,
            rows_returned=rows_returned,
        )
        
        logger.info(
            f"Query processed: {request.question[:50]}... "
            f"({latency_ms:.0f}ms, accuracy={accuracy:.0%}, rows={rows_returned})"
        )
        
        return response
    
    except Exception as exc:
        error_msg = str(exc)
        latency_ms = (time.time() - start_time) * 1000
        
        metrics.record_query(
            question=request.question,
            latency_ms=latency_ms,
            accuracy=0.0,
            rows_returned=0,
            error=error_msg,
        )
        
        logger.error(f"Query failed: {error_msg}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Query processing failed. Check logs for details."
        )


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


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "--chat":
        run_chat()
        return

    sample_question = "What were total sales by product category?"
    user_question = " ".join(sys.argv[1:]).strip() or sample_question

    orchestrator = QueryOrchestrator()
    response = orchestrator.process_question(user_question)
    print_response(response)


def run_chat() -> None:
    """Run a tiny CLI chat loop that keeps in-process conversation memory."""
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
