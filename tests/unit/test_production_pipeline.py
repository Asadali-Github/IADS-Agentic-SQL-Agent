"""Tests for the production pipeline selector (offline fallback + output mapping)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT), str(_ROOT / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

duckdb = pytest.importorskip("duckdb")


def test_oci_configured_reads_env(monkeypatch):
    from app import production_pipeline as pp
    monkeypatch.delenv("DEPLOY_TARGET", raising=False)
    monkeypatch.delenv("ADB_DSN", raising=False)
    monkeypatch.delenv("SELECT_AI_PROFILE", raising=False)
    monkeypatch.delenv("OCI_COMPARTMENT_ID", raising=False)
    assert pp.oci_configured() is False
    monkeypatch.setenv("ADB_DSN", "db_high")
    monkeypatch.setenv("SELECT_AI_PROFILE", "AGENT_PROFILE")
    assert pp.oci_configured() is True
    monkeypatch.setenv("DEPLOY_TARGET", "oracle")
    assert pp.oci_configured() is True


def test_offline_fallback_when_not_configured(monkeypatch):
    from app import production_pipeline as pp
    monkeypatch.delenv("DEPLOY_TARGET", raising=False)
    monkeypatch.delenv("ADB_DSN", raising=False)
    r = pp.answer_question("What is the total revenue by region?")
    assert r["sql"] and r["rows"]            # came from the offline FullPipeline
    assert r["chart"]["type"] in ("bar", "pie", "line")


def test_live_output_mapping_with_mock_orchestrator():
    from app.production_pipeline import ProductionPipeline

    class FakeOrch:
        def process_question(self, q):
            return {
                "generated_sql": {"sql": "SELECT region, SUM(revenue) AS revenue "
                                         "FROM product_sales GROUP BY region",
                                  "reasoning": "Grouped revenue by region."},
                "query_results": {"status": "success",
                                  "columns": ["region", "revenue"],
                                  "rows": [{"region": "East", "revenue": 45.0},
                                           {"region": "West", "revenue": 36.0},
                                           {"region": "South", "revenue": 25.0}],
                                  "row_count": 3, "error": None},
                "answer": {"answer": "East led revenue.", "provider": "oracle_select_ai"},
                "retrieved_documents": [{"id": "kpi_revenue"}],
                "support_assessment": {"is_supported": True},
                "pipeline_stage": "sql_executed_successfully",
            }

    pp = ProductionPipeline()
    pp._by_session["_default"] = FakeOrch()
    out = pp.run("revenue by region")
    assert out["answer"] == "East led revenue."
    assert out["tables_used"] == ["product_sales"]
    assert out["insights"]                       # enriched from live rows
    assert out["chart"]["type"] in ("bar", "pie", "line")
    assert out["confidence"] == 0.9
    assert out["approximate_match"] is False
    assert out["provider"] == "oracle_select_ai"


def test_fallback_success_flagged_approximate():
    from app.production_pipeline import ProductionPipeline

    class FakeOrch:
        def process_question(self, q):
            return {
                "generated_sql": {"sql": "SELECT 1 FROM dual", "reasoning": ""},
                "query_results": {"status": "fallback_success", "columns": ["x"],
                                  "rows": [{"x": 1}], "row_count": 1, "error": "ADB timeout"},
                "answer": {"answer": "cached", "provider": "local"},
                "retrieved_documents": [], "support_assessment": {"is_supported": True},
                "pipeline_stage": "sql_executed_with_fallback",
            }

    pp = ProductionPipeline()
    pp._by_session["_default"] = FakeOrch()
    out = pp.run("anything")
    assert out["approximate_match"] is True
    assert out["confidence"] == 0.6
