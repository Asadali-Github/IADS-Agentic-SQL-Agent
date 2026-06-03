"""Tests for the end-to-end pipeline (app/pipeline.py) + local executor."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT), str(_ROOT / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

duckdb = pytest.importorskip("duckdb")  # offline executor needs duckdb


def _seed_exists() -> bool:
    return (_ROOT / "db" / "seed" / "product_sales.csv").exists()


pytestmark = pytest.mark.skipif(not _seed_exists(), reason="seed CSV not present")


def test_local_db_executes_and_blocks_writes():
    from evaluation.local_db import LocalDB
    db = LocalDB()
    r = db.execute("SELECT region, SUM(revenue) AS revenue FROM product_sales GROUP BY region")
    assert r.success and r.columns == ["region", "revenue"] and len(r.rows) == 4
    assert db.execute("DELETE FROM product_sales").success is False


def test_validate_sql_rejects_non_select():
    from app.pipeline import validate_sql
    assert validate_sql("SELECT 1 FROM product_sales")["is_valid"] is True
    assert validate_sql("DROP TABLE product_sales")["is_valid"] is False
    assert validate_sql("SELECT 1; SELECT 2")["is_valid"] is False


def test_pipeline_end_to_end_known_question():
    from app.pipeline import answer_question
    r = answer_question("What is the total revenue by region?")
    assert r["sql"] and r["rows"]
    assert r["chart"]["type"] in ("bar", "pie", "line")
    assert r["insights"]
    assert r["confidence"] is not None
    assert r["error"] is None
    assert set(r["rows"][0].keys()) == {"region", "revenue"}


def test_pipeline_offline_gracefully_handles_unknown_question():
    from app.pipeline import answer_question
    r = answer_question("xyzzy unrelated gibberish question about nothing")
    assert r["sql"] == ""
    assert r["clarification"]  # asks instead of guessing
