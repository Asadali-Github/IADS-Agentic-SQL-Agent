FROM python:3.11-slim

WORKDIR /app

# System deps for oracledb
RUN apt-get update && apt-get install -y --no-install-recommends \
    libaio1 \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first for layer caching
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e .

# Copy source
COPY src ./src
COPY prompts ./prompts
COPY frontend ./frontend

EXPOSE 8000
CMD ["uvicorn", "sql_agent.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
