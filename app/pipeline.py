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
import time
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_ROOT / ".env")
for _p in (str(_ROOT), str(_ROOT / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

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
        m = self._ENTITY_RE.search(question)
        if m:
            measure = self._MEASURE_COL.get(m.group(1).lower(), "revenue")
            entity = re.sub(r"[?.!]+$", "", m.group(4)).strip().strip("'\"")
            entity = re.sub(r"\b(category|product|region|in \d{4}.*)\b.*$", "", entity, flags=re.I).strip()
            if entity:
                sql = (f"SELECT product_name, SUM({measure}) AS {measure} FROM product_sales "
                       f"WHERE product_name = '{entity}' GROUP BY product_name")
                return {"sql": sql, "provider": "offline_template", "approximate": False,
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
        self._last_results: dict[str, dict[str, Any]] = {}

    def _execute(self, sql: str, provider: str | None = None) -> ExecutionResult:
        if self._executor is not None:
            return self._executor.execute(sql)

        if provider == "oracle_select_ai" and os.getenv("ADB_DSN"):
            started = time.perf_counter()
            try:
                from app.sql.executor import OracleSQLExecutor

                result = OracleSQLExecutor().execute(sql)
            except Exception as exc:  # noqa: BLE001
                return ExecutionResult.failure(f"Oracle execution failed: {exc}")

            latency_ms = (time.perf_counter() - started) * 1000
            columns = result.get("columns", [])
            rows_as_dicts = result.get("rows", [])
            rows = [
                [row.get(column) for column in columns]
                for row in rows_as_dicts
            ]
            return ExecutionResult(
                columns=columns,
                rows=rows,
                row_count=result.get("row_count", len(rows)),
                success=bool(result.get("success")),
                error=result.get("error"),
                latency_ms=latency_ms,
            )

        from evaluation.local_db import get_local_db

        return get_local_db().execute(sql)

    def _retrieve(self, question: str) -> list[dict]:
        """Best-effort RAG context (informational); never breaks the pipeline."""
        try:
            if self._retriever is None:
                from app.rag.retriever import LangChainRAGRetriever

                self._retriever = LangChainRAGRetriever()
            return self._retriever.retrieve(question)
        except Exception:  # noqa: BLE001 - retrieval optional offline
            return []

    # Multi-turn: dimensions / measures we can swap into a prior question.
    _DIMS = {"region": "region", "category": "category", "categories": "category",
             "subcategory": "sub_category", "sub-category": "sub_category",
             "sub category": "sub_category", "state": "state", "states": "state",
             "product": "product", "products": "product", "city": "city"}
    _MEAS = {"revenue": "revenue", "sales": "revenue", "turnover": "revenue",
             "profit": "profit", "margin": "profit margin", "units": "units",
             "quantity": "units", "orders": "orders"}
    _TRIGGER = re.compile(r"^\s*(and|what about|how about|now|also|then|by|for|just)\b", re.I)
    _ROW_REF = re.compile(
        r"\b(that|it|that one|the first|first|top|highest|largest|biggest|best|"
        r"the last|last|bottom|lowest|smallest|worst|second|third)\b",
        re.I,
    )
    _DIRECT_RESULT_Q = re.compile(
        r"\b(which|what|how much|how many|show|tell me|give me|compare)\b",
        re.I,
    )

    def _resolve_followup(self, question: str, session_id: Optional[str]) -> str:
        """Rewrite a short follow-up into a standalone question using the last turn.

        "total revenue by region" then "what about by category?" -> "total revenue
        by category". Makes the agent genuinely conversational (multi-turn).
        """
        q = question.strip()
        if not session_id:            # no multi-turn without an explicit session
            return q
        prior = self._history.get(session_id)
        if not prior:
            return q
        low = q.lower()
        mentions_field = any(re.search(rf"\b{re.escape(k)}\b", low)
                             for k in (*self._DIMS, *self._MEAS))
        if not mentions_field or not (self._TRIGGER.match(low) or len(q.split()) <= 5):
            return q
        rewritten = prior[-1]
        for key, canon in self._DIMS.items():
            if re.search(rf"\b{re.escape(key)}\b", low):
                if re.search(r"\bby\b", rewritten, re.I):
                    rewritten = re.sub(r"(\bby\b\s+)([\w\- ]+?)(\s*\??$)",
                                       rf"\1{canon}\3", rewritten, flags=re.I)
                else:
                    rewritten = f"{rewritten} by {canon}"
                break
        for key, canon in self._MEAS.items():
            if re.search(rf"\b{re.escape(key)}\b", low):
                rewritten = re.sub(r"\b(revenue|sales|turnover|profit|units|quantity|orders|margin)\b",
                                   canon, rewritten, count=1, flags=re.I)
                break
        return rewritten

    def _selected_memory_row(self, question: str, memory: dict[str, Any]) -> dict[str, Any] | None:
        rows = memory.get("rows") or []
        if not rows:
            return None

        low = question.lower()
        if re.search(r"\b(second|2nd)\b", low) and len(rows) >= 2:
            return rows[1]
        if re.search(r"\b(third|3rd)\b", low) and len(rows) >= 3:
            return rows[2]
        if re.search(r"\b(last|bottom|lowest|smallest|worst)\b", low):
            return rows[-1]

        mentioned = self._find_row_by_mentioned_value(question, rows)
        if mentioned is not None:
            return mentioned

        return rows[0]

    def _find_row_by_mentioned_value(
        self,
        question: str,
        rows: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        q_norm = _norm(question)
        for row in rows:
            for value in row.values():
                if isinstance(value, str) and value and _norm(value) in q_norm:
                    return row
        return None

    def _dimension_column(self, row: dict[str, Any]) -> str | None:
        preferred = (
            "category",
            "product",
            "region",
            "country",
            "state",
            "city",
            "customer",
            "name",
        )
        for column, value in row.items():
            name = column.lower()
            if isinstance(value, str) and any(token in name for token in preferred):
                return column
        for column, value in row.items():
            if isinstance(value, str):
                return column
        return next(iter(row), None)

    def _numeric_columns(self, row: dict[str, Any]) -> list[str]:
        return [
            column
            for column, value in row.items()
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        ]

    def _business_dimension_name(self, column: str) -> str:
        name = column.lower().replace("total_", "").replace("_", " ")
        if "category" in name:
            return "category"
        if "product" in name:
            return "product"
        if "region" in name:
            return "region"
        if "country" in name:
            return "country"
        if "state" in name:
            return "state"
        if "city" in name:
            return "city"
        if "customer" in name:
            return "customer"
        return name

    def _requested_measure(self, question: str) -> str | None:
        low = question.lower()
        for key, canon in self._MEAS.items():
            if re.search(rf"\b{re.escape(key)}\b", low):
                return canon
        return None

    def _answer_from_memory(
        self,
        question: str,
        session_id: Optional[str],
    ) -> dict[str, Any] | None:
        if not session_id:
            return None
        memory = self._last_results.get(session_id)
        if not memory or not memory.get("rows"):
            return None

        low = question.lower()
        if not (self._DIRECT_RESULT_Q.search(question) or self._ROW_REF.search(question)):
            return None

        row = self._selected_memory_row(question, memory)
        if not row:
            return None

        dimension_column = self._dimension_column(row)
        numeric_columns = self._numeric_columns(row)
        if not dimension_column and not numeric_columns:
            return None

        requested_measure = self._requested_measure(question)
        measure_column = None
        if requested_measure:
            measure_column = next(
                (
                    column
                    for column in numeric_columns
                    if requested_measure.replace(" ", "_") in column.lower()
                    or requested_measure.split()[0] in column.lower()
                ),
                None,
            )
            if measure_column is None:
                return None
        measure_column = measure_column or (numeric_columns[0] if numeric_columns else None)

        if not measure_column:
            return None

        dimension_value = row.get(dimension_column) if dimension_column else None
        measure_value = row.get(measure_column)
        if dimension_value is None:
            answer = f"{measure_column} was {measure_value:,} in the previous result."
        else:
            answer = f"{dimension_value} had {measure_column} of {measure_value:,} in the previous result."

        if re.search(r"\b(all|table|rows|previous result|last result|same data)\b", low):
            rows = memory["rows"]
        else:
            rows = [row]

        return {
            "question": question,
            "answer": answer,
            "rows": rows,
            "columns": list(rows[0].keys()) if rows else [],
            "sql": memory.get("sql", ""),
            "explanation": "Answered from the previous result set in this conversation.",
            "explanation_bullets": ["Used the rows returned by the previous question."],
            "insights": [],
            "chart": None,
            "tables_used": memory.get("tables_used", []),
            "confidence": 0.95,
            "clarification": None,
            "approximate_match": False,
            "provider": "conversation_memory",
            "retrieved_doc_ids": [],
            "latency_ms": 0.0,
            "error": None,
            "session_id": session_id,
        }

    def _rewrite_with_result_memory(self, question: str, session_id: Optional[str]) -> str:
        if not session_id:
            return question
        memory = self._last_results.get(session_id)
        if not memory or not memory.get("rows"):
            return question
        if not self._ROW_REF.search(question):
            return question

        measure = self._requested_measure(question)
        if not measure:
            return question

        row = self._selected_memory_row(question, memory)
        if not row:
            return question

        dimension_column = self._dimension_column(row)
        if not dimension_column:
            return question

        dimension_value = row.get(dimension_column)
        if not isinstance(dimension_value, str) or not dimension_value:
            return question

        dimension_name = self._business_dimension_name(dimension_column)
        return f"What is total {measure} for {dimension_name} {dimension_value}?"

    def _remember_result(
        self,
        session_id: Optional[str],
        question: str,
        sql: str,
        rows: list[dict[str, Any]],
        response: dict[str, Any],
    ) -> None:
        if not session_id or not rows:
            return
        self._last_results[session_id] = {
            "question": question,
            "sql": sql,
            "rows": rows,
            "answer": response.get("answer", ""),
            "tables_used": response.get("tables_used", []),
        }

    def run(self, question: str, session_id: Optional[str] = None) -> dict:
        from sql_agent.retrieval.glossary import enrich_query_terms

        memory_response = self._answer_from_memory(question, session_id)
        if memory_response is not None:
            return memory_response

        # Multi-turn: expand a follow-up into a standalone question before anything else.
        resolved = self._resolve_followup(question, session_id)
        resolved = self._rewrite_with_result_memory(resolved, session_id)
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

        execution = self._execute(sql, provider=gen.get("provider"))

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
        response = {
            "question": question,
            "answer": summary.answer,
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
        if execution.success:
            self._remember_result(session_id, resolved, sql, rows_as_dicts, response)
        return response

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
