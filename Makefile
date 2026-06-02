.PHONY: help install dev test lint format typecheck run-api run-ui benchmark seed-db embed-schema docker-build docker-up docker-down clean

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

install:  ## Install package in editable mode
	pip install -e .

dev:  ## Install with dev dependencies + register pre-commit hooks
	pip install -e ".[dev]"
	pre-commit install

test:  ## Run tests
	pytest

lint:  ## Lint with ruff
	ruff check src tests

format:  ## Format with ruff
	ruff format src tests

typecheck:  ## Type-check with mypy
	mypy src

run-api:  ## Start FastAPI on port 8000
	uvicorn sql_agent.api.main:app --reload --port 8000

run-ui:  ## Start Streamlit on port 8501
	streamlit run frontend/streamlit_app.py

benchmark:  ## Run benchmark against the golden query set
	python scripts/run_benchmark.py

seed-db:  ## Seed the Autonomous DB with demo data
	python scripts/seed_database.py

embed-schema:  ## Embed schema descriptions into the vector store
	python scripts/embed_schema.py

docker-build:  ## Build the Docker image
	docker compose build

docker-up:  ## Start the full stack via docker compose
	docker compose up

docker-down:  ## Stop the docker compose stack
	docker compose down

clean:  ## Remove caches
	rm -rf build dist *.egg-info .pytest_cache .mypy_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} +
