FROM python:3.11-slim

WORKDIR /app

# System deps for oracledb (thin mode needs no Instant Client; libaio kept for safety)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libaio1 curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first for layer caching
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e .

# Copy the WHOLE runtime, not just src/. The API (sql_agent.api.routes) imports
# `app.*` and `evaluation.*`, so those packages MUST be in the image or the API
# silently falls back to the stub responder.
COPY src ./src
COPY app ./app
COPY evaluation ./evaluation
COPY prompts ./prompts
COPY frontend ./frontend
COPY db ./db
COPY data ./data

# `app` and `evaluation` are top-level packages (not under src/), so they must be
# importable. `sql_agent` is installed via `pip install -e .` (packages.find=src).
ENV PYTHONPATH=/app:/app/src \
    PYTHONUNBUFFERED=1

# Run as a non-root user (least privilege).
RUN useradd --create-home --uid 10001 appuser && chown -R appuser /app
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "sql_agent.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
