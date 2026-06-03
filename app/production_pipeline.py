"""Production pipeline selector for OCI / Oracle Autonomous Database.

The FastAPI `/query` endpoint should answer from the LIVE Oracle database in a
deployed environment, not from the offline DuckDB seed. This module picks the
right backend automatically:

  * OCI configured  -> app.agents.query_orchestrator.QueryOrchestrator
        live ADB execution (SafeSQLExecutor), Oracle Select AI generation,
        Oracle 23ai vector retrieval (OCITextEmbeddingClient + VECTOR_DISTANCE),
        ConversationMemory for multi-turn.
  * not configured  -> app.pipeline.FullPipeline
        offline DuckDB over db/seed/product_sales.csv (demo / CI / local dev).

Either way the result is normalised to the API's QueryResponse shape and
ENRICHED with the deterministic business insights + chart spec from the
summariser, so the UX is identical regardless of backend.

"OCI configured" = ADB_DSN present AND (SELECT_AI_PROFILE or OCI_COMPARTMENT_ID).
Set DEPLOY_TARGET=oracle to force the live path (fail loudly if misconfigured).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_ROOT), str(_ROOT / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def oci_configured() -> bool:
    """True when enough OCI/ADB settings are present to use the live backend."""
    if os.getenv("DEPLOY_TARGET", "").lower() == "oracle":
        return True
    has_db = bool(os.getenv("ADB_DSN"))
    has_ai = bool(os.getenv("SELECT_AI_PROFILE") or os.getenv("OCI_COMPARTMENT_ID"))
    return has_db and has_ai


def _tables_used(sql: str) -> list[str]:
    if not sql:
        return []
    try:
        import sqlglot
        from sqlglot import exp

        return sorted({t.name.lower() for t in sqlglot.parse_one(sql, read="oracle").find_all(exp.Table)})
    except Exception:  # noqa: BLE001
        return []


def _enrich(question: str, columns: list[str], rows: list[dict]) -> tuple[list[str], Optional[dict]]:
    """Deterministic insights + chart spec computed from live result rows."""
    try:
        from sql_agent.agents.summariser import generate_insights, suggest_chart

        row_lists = [[row.get(c) for c in columns] for row in rows]
        insights = generate_insights(question, columns, row_lists)
        chart = suggest_chart(question, columns, row_lists)
        return insights, (chart.model_dump() if chart else None)
    except Exception:  # noqa: BLE001 - enrichment is best-effort
        return [], None


class ProductionPipeline:
    """Routes each request to the live Oracle backend, normalising the output.

    Keeps one QueryOrchestrator per session so ConversationMemory (multi-turn)
    survives across follow-up questions.
    """

    def __init__(self) -> None:
        self._by_session: dict[str, object] = {}

    def _orchestrator(self, session_id: Optional[str]):
        key = session_id or "_default"
        if key not in self._by_session:
            # Import lazily, only when we actually need to construct one, so a
            # pre-injected orchestrator (tests) never triggers the heavy import.
            from app.agents.query_orchestrator import QueryOrchestrator

            self._by_session[key] = QueryOrchestrator()
        return self._by_session[key]

    def run(self, question: str, session_id: Optional[str] = None) -> dict:
        orch = self._orchestrator(session_id)
        r = orch.process_question(question)

        gen = r.get("generated_sql") or {}
        qr = r.get("query_results") or {}
        ans = r.get("answer") or {}
        rows = qr.get("rows", []) or []
        columns = qr.get("columns", []) or []
        sql = gen.get("sql") or ""
        status = qr.get("status")
        approximate = status == "fallback_success"

        insights, chart = _enrich(question, columns, rows) if rows else ([], None)

        confidence = 0.9 if status == "success" else (0.6 if approximate else 0.3)
        return {
            "question": question,
            "answer": ans.get("answer", ""),
            "rows": rows,
            "columns": columns,
            "sql": sql,
            "explanation": gen.get("reasoning", "") or "",
            "explanation_bullets": [b for b in [gen.get("reasoning")] if b],
            "insights": insights,
            "chart": chart,
            "tables_used": _tables_used(sql),
            "confidence": confidence,
            "clarification": gen.get("clarification_question"),
            "approximate_match": approximate,
            "provider": ans.get("provider") or gen.get("provider"),
            "retrieved_doc_ids": [d.get("id") for d in r.get("retrieved_documents", []) or []],
            "latency_ms": None,
            "error": qr.get("error") or gen.get("error"),
            "session_id": session_id,
            "pipeline_stage": r.get("pipeline_stage"),
        }


_PROD: Optional[ProductionPipeline] = None


def answer_question(question: str, session_id: Optional[str] = None) -> dict:
    """Single entry point: live Oracle backend if configured, else offline pipeline."""
    global _PROD
    if oci_configured():
        try:
            if _PROD is None:
                _PROD = ProductionPipeline()
            return _PROD.run(question, session_id=session_id)
        except Exception:  # noqa: BLE001 - never 500 the API; fall back to offline
            pass
    from app.pipeline import answer_question as offline_answer

    return offline_answer(question, session_id=session_id)
