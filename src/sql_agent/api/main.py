"""FastAPI app entry point for the Streamlit chatbot.

Owner: Mehdi
Status: implemented.

TODO:
- Define the public interface here
- Implement the logic
- Write tests in tests/unit/test_main.py
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sql_agent.api.routes import router

app = FastAPI(
    title="IADS SQL Agent",
    description="Multi-stage agentic text-to-SQL system.",
    version="0.1.0",
)

# Allow the Streamlit frontend (port 8501) to call the API (port 8000).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

