"""End-to-end query pipeline — question in, business answer out.

Owner: Asad (integration glue). This is the missing layer that connects the
team's components into one working flow, without rewriting any of them:

    question
      -> glossary enrich          (retrieval/glossary.py — Asad)
      -> RAG retrieve context     (app.rag — Zayad/team)
      -> generate SQL             (app.sql Oracle Select AI — live; cached offline)
      -> validate (read-only)     (app.sql.validator + sqlglot guard)
      -> execute                  (Oracle when configured; LocalDB/DuckDB offline)
      -> summarise                (agents/summariser.py — Asad: answer, explanation,
                                   insights, chart, confidence, clarification)
      -> QueryResponse-shaped dict (api/schemas.py — Mehdi)

It runs FULLY OFFLINE on the cleaned seed (db/seed/product_sales.csv) for the
curated demo questions, and uses live OCI + Oracle automatically when
SELECT_AI_PROFILE / ADB_* env vars are present. Swapping offline->live is config,
not code.
"""

from __future__ import annotations

import json
import os
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_ROOT), str(_ROOT / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from app.agents.followups import resolve as resolve_follow_up  # noqa: E402
from sql_agent.agents.summariser import Summariser  # noqa: E402
from sql_agent.core.models import ExecutionResult  # noqa: E402

_DATASETS = _ROOT / "evaluation" / "datasets"


def _norm(q: str) -> str:
    import re
    return re.sub(r"[^a-z0-9 ]", " ", (q or "").lower())


class SQLSource:
    """Provides SQL for a question: live OCI Select AI, or an offline cache.

    The offline cache is built from the curated golden + example queries so the
    demo works without cloud credentials. Live generation kicks in automatically
    when SELECT_AI_PROFILE is configured.
    """

    def __init__(self) -> None:
        self._cache: list[tuple[str, str]] = self._build_cache()
        self._live = None
        if os.getenv("SELECT_AI_PROFILE"):
            try:
                from app.sql.generator import OracleSelectAISQLGenerator

                self._live = OracleSelectAISQLGenerator()
            except Exception:  # noqa: BLE001
                self._live = None

    def _build_cache(self) -> list[dict]:
        cache: list[dict] = []
        for name in ("golden_queries.jsonl", "example_queries.jsonl"):
            path = _DATASETS / name
            if not path.exists():
                continue
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                try:
                    row = json.loads(line)
                except Exception:  # noqa: BLE001
                    continue
                q = row.get("question", "")
                sql = row.get("expected_sql") or row.get("sql")
                if q and sql:
                    nq = _norm(q)
                    cache.append({"nq": nq, "tokens": set(nq.split()), "sql": sql,
                                  "group_by": "group by" in sql.lower()})
        return cache

    _ENTITY_RE = re.compile(
        r"\b(revenue|sales|turnover|profit|units|quantity)\b.*?\b(for|of|from|on)\b\s+(the\s+)?(.+)",
        re.I)
    _MEASURE_COL = {"revenue": "revenue", "sales": "revenue", "turnover": "revenue",
                    "profit": "profit", "units": "quantity", "quantity": "quantity"}

    def _entity_filter_sql(self, question: str, require_modelnum: bool = False):
        """Build a single-product filter SQL from a "<measure> for <entity>"
        question, or None. With require_modelnum=True it only fires when the
        entity has BOTH a letter and a digit (model numbers like "iPhone 15"),
        so dimensions (region/category) and bare years never match."""
        m = self._ENTITY_RE.search(question)
        if not m:
            return None
        measure = self._MEASURE_COL.get(m.group(1).lower(), "revenue")
        entity = re.sub(r"[?.!]+$", "", m.group(4)).strip().strip("'\"")
        entity = re.sub(r"\b(category|product|region|in \d{4}.*)\b.*$", "", entity, flags=re.I).strip()
        if not entity:
            return None
        if require_modelnum and not (re.search(r"[A-Za-z]", entity) and re.search(r"\d", entity)):
            return None
        return (f"SELECT product_name, SUM({measure}) AS {measure} FROM product_sales "
                f"WHERE product_name = '{entity}' GROUP BY product_name")

    def generate(self, question: str, prompt: Optional[str] = None) -> dict:
        # Live path (Oracle Select AI) when configured.
        if self._live is not None and prompt:
            result = self._live.generate(prompt)
            if result.get("sql"):
                return {"sql": result["sql"], "provider": "oracle_select_ai",
                        "approximate": False, "clarification": result.get("clarification_question")}

        nq = _norm(question)
        q_tokens = set(nq.split())
        wants_breakdown = " by " in f" {nq} "

        # Specific-product questions (model numbers like "iPhone 15") route straight
        # to the entity-template, ahead of fuzzy cache matching, so the vector
        # row-fallback engages when the product is absent.
        specific = self._entity_filter_sql(question, require_modelnum=True)
        if specific is not None:
            return {"sql": specific, "provider": "offline_template",
                    "approximate": False, "clarification": None}

        best, best_score = None, 0.0
        for entry in self._cache:
            char = SequenceMatcher(None, nq, entry["nq"]).ratio()
            jacc = len(q_tokens & entry["tokens"]) / len(q_tokens | entry["tokens"]) if (q_tokens | entry["tokens"]) else 0.0
            score = 0.5 * char + 0.5 * jacc
            if nq and (nq in entry["nq"] or entry["nq"] in nq):
                score = max(score, 0.9)
            if wants_breakdown and entry["group_by"]:
                score += 0.08  # prefer a GROUP BY query for a "by X" question
            if score > best_score:
                best, best_score = entry, score
        if best and best_score >= 0.62:
            return {"sql": best["sql"], "provider": "offline_cache",
                    "approximate": best_score < 0.9, "clarification": None}

        # Offline entity-filter template: "<measure> for <entity>" -> a product filter.
        # Lets arbitrary single-entity questions run offline AND exercise the
        # similarity row-fallback when the entity doesn't exist / is misspelled.
        tmpl = self._entity_filter_sql(question)
        if tmpl is not None:
            return {"sql": tmpl, "provider": "offline_template", "approximate": False,
                    "clarification": None}
        return {"sql": None, "provider": "offline_cache", "approximate": False,
                "clarification": ("I can only answer the curated demo questions while running "
                                  "offline. Try one of the suggested questions, or set "
                                  "SELECT_AI_PROFILE to enable live SQL generation.")}


def validate_sql(sql: str) -> dict:
    """Read-only safety check: app validator + a sqlglot single-SELECT guard."""
    try:
        from app.sql.validator import validate_sql as app_validate

        base = app_validate(sql)
        if not base.get("is_valid", True):
            return base
    except Exception:  # noqa: BLE001
        pass
    try:
        import sqlglot
        from sqlglot import exp

        statements = [s for s in sqlglot.parse(sql, read="oracle") if s]
        if len(statements) != 1:
            return {"is_valid": False, "reason": "Only a single statement is allowed."}
        if not isinstance(statements[0], (exp.Select, exp.Subquery)) and statements[0].find(exp.Select) is None:
            return {"is_valid": False, "reason": "Only SELECT queries are allowed."}
    except Exception as exc:  # noqa: BLE001
        return {"is_valid": False, "reason": f"Could not parse SQL: {exc}"}
    return {"is_valid": True, "reason": "ok"}


class FullPipeline:
    """Compose retrieval + generation + execution + summarisation."""

    def __init__(self, executor=None, summariser: Optional[Summariser] = None) -> None:
        self.sql_source = SQLSource()
        self.summariser = summariser or Summariser()
        self._executor = executor  # injected; defaults to LocalDB lazily
        self._retriever = None
        self._history: dict[str, list[str]] = {}  # session_id -> prior questions (multi-turn)

    def _execute(self, sql: str) -> ExecutionResult:
        if self._executor is not None:
            return self._executor.execute(sql)
        from evaluation.local_db import get_local_db

        return get_local_db().execute(sql)

    def _retrieve(self, question: str) -> list[dict]:
        """Best-effort RAG context. Uses the team's Oracle 23ai vector retriever
        when OCI is reachable, transparently falling back to its local keyword
        search offline. Never breaks the pipeline."""
        try:
            if self._retriever is None:
                from app.rag.retriever import OracleRAGRetriever

                # auto_seed=False: never touch ADB on construction; retrieve()
                # falls back to local keyword search when OCI is unavailable.
                self._retriever = OracleRAGRetriever(auto_seed=False)
            return self._retriever.retrieve(question)
        except Exception:  # noqa: BLE001 - retrieval optional offline
            return []

    def _resolve_followup(self, question: str, session_id: Optional[str]) -> str:
        """Rewrite a genuine follow-up into a standalone question using the last turn.

        "total revenue by region" then "what about by category?" -> "total revenue
        by category". Standalone questions (e.g. "show total profit by region")
        are returned untouched and answered with a fresh database query — they are
        never merged with the previous turn. Detection/rewriting is delegated to
        :mod:`app.agents.followups`, shared with the live Oracle backend so both
        behave identically.
        """
        q = question.strip()
        if not session_id:            # no multi-turn without an explicit session
            return q
            
        from app.agents.followups import looks_like_follow_up
        
        is_rel = looks_like_follow_up(q)
        if not is_rel:
            # Unrelated new question: reset conversational context
            if session_id in self._history:
                self._history[session_id] = []
            return q
            
        prior = self._history.get(session_id)
        if not prior:
            return q
        return resolve_follow_up(q, prior[-1])

    def run(self, question: str, session_id: Optional[str] = None) -> dict:
        from sql_agent.retrieval.glossary import enrich_query_terms

        # Multi-turn: expand a follow-up into a standalone question before anything else.
        resolved = self._resolve_followup(question, session_id)
        if session_id:
            self._history.setdefault(session_id, []).append(resolved)
        enriched = enrich_query_terms(resolved)
        retrieved = self._retrieve(enriched)

        prompt = None
        try:
            from app.sql.prompt_builder import SQLPromptBuilder

            prompt = SQLPromptBuilder().build_prompt(resolved, retrieved)
        except Exception:  # noqa: BLE001
            prompt = None

        gen = self.sql_source.generate(resolved, prompt=prompt)
        sql = gen.get("sql")
        if not sql:
            return self._empty_response(question, session_id,
                                        clarification=gen.get("clarification"),
                                        retrieved=retrieved, provider=gen.get("provider"))

        check = validate_sql(sql)
        if not check.get("is_valid", True):
            return self._error_response(question, session_id, sql,
                                        f"The generated query was blocked: {check.get('reason')}")

        execution = self._execute(sql)

        # Vector/similarity row fallback: if a string filter matched nothing, find
        # the closest real values and re-run (the brief's "similar results" rule).
        fallback_note = None
        if execution.success and execution.row_count == 0:
            try:
                from sql_agent.retrieval.row_fallback import find_similar_rows
                from evaluation.local_db import get_local_db

                fb = find_similar_rows(sql, self._executor or get_local_db())
                if fb is not None:
                    execution = fb.result
                    sql = fb.relaxed_sql
                    gen["approximate"] = True
                    others = ", ".join(str(c) for c in fb.candidates[1:4])
                    fallback_note = (f"No exact match for '{fb.requested_value}'. Showing the "
                                     f"closest match '{fb.matched_value}'"
                                     + (f" (other near matches: {others})." if others else "."))
            except Exception:  # noqa: BLE001 - fallback is best-effort
                fallback_note = None

        summary = self.summariser.summarise(resolved, sql, execution)

        rows_as_dicts = [dict(zip(execution.columns, r)) for r in execution.rows]
        return {
            "question": question,
            "resolved_question": resolved,
            "answer": summary.answer,
            "important_numbers": summary.important_numbers,
            "trends_anomalies": summary.trends_anomalies,
            "final_takeaway": summary.final_takeaway,
            "rows": rows_as_dicts,
            "columns": execution.columns,
            "sql": sql,
            "explanation": "\n".join(summary.explanation),
            "explanation_bullets": summary.explanation,
            "insights": summary.insights,
            "chart": summary.chart.model_dump() if summary.chart else None,
            "tables_used": summary.tables_used,
            "confidence": summary.confidence if summary.confidence is not None else 1.0,
            "clarification": fallback_note or summary.clarification,
            "approximate_match": bool(gen.get("approximate")),
            "provider": gen.get("provider"),
            "retrieved_doc_ids": [d.get("id") for d in retrieved],
            "latency_ms": execution.latency_ms,
            "error": execution.error if not execution.success else None,
            "session_id": session_id,
        }

    def _empty_response(self, question, session_id, clarification, retrieved, provider):
        return {
            "question": question, "answer": clarification or "No answer available.",
            "rows": [], "columns": [], "sql": "", "explanation": "",
            "explanation_bullets": [], "insights": [], "chart": None, "tables_used": [],
            "confidence": 0.3, "clarification": clarification, "approximate_match": False,
            "provider": provider, "retrieved_doc_ids": [d.get("id") for d in retrieved],
            "latency_ms": None, "error": None, "session_id": session_id,
        }

    def _error_response(self, question, session_id, sql, message):
        return {
            "question": question, "answer": "", "rows": [], "columns": [], "sql": sql,
            "explanation": "", "explanation_bullets": [], "insights": [], "chart": None,
            "tables_used": [], "confidence": 0.0, "clarification": None,
            "approximate_match": False, "provider": "blocked", "retrieved_doc_ids": [],
            "latency_ms": None, "error": message, "session_id": session_id,
        }


_PIPELINE: Optional[FullPipeline] = None


def get_pipeline() -> FullPipeline:
    global _PIPELINE
    if _PIPELINE is None:
        _PIPELINE = FullPipeline()
    return _PIPELINE


def answer_question(question: str, session_id: Optional[str] = None) -> dict:
    """One-call entry point for the whole pipeline."""
    return get_pipeline().run(question, session_id=session_id)
