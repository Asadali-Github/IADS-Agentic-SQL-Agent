"""FastAPI app entry point for the Streamlit chatbot."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sql_agent.api.routes import router

app = FastAPI(
    title="IADS SQL Agent",
    description="Multi-stage agentic text-to-SQL system.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
