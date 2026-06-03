"""Summariser stage - result rows -> natural-language answer + SQL explanation.

Owner: Asad.

Given the user's question, the SQL we generated, and the rows it returned, the
summariser produces an AnswerSummary:

  * answer       one-sentence direct answer (prompts/summariser.md)
  * explanation  2-4 plain-English bullets on how the query works
                 (prompts/sql_explanation.md)
  * tables_used  business tables the query drew on

Two design choices make this robust for a live demo:

  1. The LLM client is injected and optional. With a client we get fluent text;
     without one (offline, rate-limited, or in unit tests) we fall back to a
     deterministic, template-based summary so the pipeline NEVER returns nothing.

  2. Everything that leaves this stage is passed through the PII filter, so a
     stray email/phone sitting in a result cell can't reach the user or a log.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional, Protocol, Sequence, Union

from sql_agent.core.models import (
    AnswerSummary,
    CandidateSQL,
    ExecutionResult,
    Question,
    RetrievedSchema,
)
from sql_agent.llm import prompts
from sql_agent.llm.token_counter import TokenCounter
from sql_agent.safety import pii_filter

# Context safeguards. We never dump a large result set into the prompt: that
# causes token bloat, latency, and (worst) the model doing unreliable mental
# arithmetic over hundreds of rows. Instead we compute aggregates deterministically
# and show only a small sample.
_MAX_PREVIEW_ROWS = 20      # at or below this, show the rows themselves
_MAX_SAMPLE_ROWS = 5        # above the cap, show only this many sample rows
_LOW_CARDINALITY = 12       # show top-value counts for text columns at/below this


class LLMClient(Protocol):
    """Minimal contract the summariser needs from any LLM client."""

    def complete(self, prompt: str, *, model: Optional[str] = None) -> str: ...


# ---------------------------------------------------------------------------
# SQL helpers
# ---------------------------------------------------------------------------
def extract_tables(sql: str) -> list[str]:
    """Return the table names referenced by `sql`, best-effort.

    Uses sqlglot (Oracle dialect) and falls back to a regex over FROM/JOIN if
    parsing fails. De-duplicated, order-preserving, lower-cased.
    """
    names: list[str] = []
    try:
        import sqlglot
        from sqlglot import exp

        tree = sqlglot.parse_one(sql, read="oracle")
        for tbl in tree.find_all(exp.Table):
            if tbl.name:
                names.append(tbl.name.lower())
    except Exception:  # noqa: BLE001 - parsing is best-effort
        names.extend(t.lower() for t in re.findall(r"(?:from|join)\s+([A-Za-z_][\w.]*)", sql, re.I))

    seen: set[str] = set()
    out: list[str] = []
    for n in names:
        n = n.split(".")[-1]  # strip schema prefix
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def _schema_summary(schema: Optional[RetrievedSchema], sql: str) -> str:
    """Build a short business-data description for the explanation prompt."""
    if schema and schema.tables:
        parts = []
        for t in schema.tables:
            cols = schema.columns.get(t) if schema.columns else None
            parts.append(f"- {t}" + (f" (key fields: {', '.join(cols[:6])})" if cols else ""))
        return "\n".join(parts)
    return "\n".join(f"- {t}" for t in extract_tables(sql)) or "- (schema not supplied)"


def _rows_preview(columns: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    """Render a small, PII-scrubbed preview of the rows for the prompt."""
    head = rows[:_MAX_PREVIEW_ROWS]
    lines = []
    if columns:
        lines.append(" | ".join(str(c) for c in columns))
    for r in head:
        lines.append(" | ".join(pii_filter.scrub(str(c)) for c in r))
    if len(rows) > _MAX_PREVIEW_ROWS:
        lines.append(f"... (+{len(rows) - _MAX_PREVIEW_ROWS} more rows)")
    return "\n".join(lines) if lines else "(no rows)"


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def profile_result(columns: Sequence[str], rows: Sequence[Sequence[Any]]) -> dict:
    """Compute deterministic per-column aggregates over the FULL result set.

    Pure Python (no pandas dependency). These numbers - counts, min/max/mean/sum,
    distinct, top categories - are what we feed the model so it never has to do
    arithmetic over raw rows. O(rows * cols) regardless of result size.
    """
    from collections import Counter

    n = len(rows)
    out: dict[str, Any] = {"row_count": n, "columns": []}
    for ci, col in enumerate(columns):
        values = [r[ci] for r in rows if ci < len(r)]
        nonnull = [v for v in values if v is not None]
        numbers = [v for v in nonnull if _is_number(v)]
        info: dict[str, Any] = {
            "name": col,
            "nulls": len(values) - len(nonnull),
            "distinct": len({str(v) for v in nonnull}),
        }
        if nonnull and len(numbers) == len(nonnull):
            total = float(sum(numbers))
            info.update(
                dtype="numeric",
                min=min(numbers),
                max=max(numbers),
                sum=round(total, 4),
                mean=round(total / len(numbers), 4),
            )
        else:
            info["dtype"] = "text"
            counts = Counter(str(v) for v in nonnull)
            if 0 < len(counts) <= _LOW_CARDINALITY:
                info["top_values"] = counts.most_common(5)
        out["columns"].append(info)
    return out


def _format_profile(profile: dict) -> str:
    """Render a profile as a compact, PII-scrubbed text block for the prompt."""
    lines = [f"rows: {profile['row_count']}"]
    for c in profile["columns"]:
        if c["dtype"] == "numeric":
            lines.append(
                f"- {c['name']} (number): min={c['min']} max={c['max']} "
                f"sum={c['sum']} mean={c['mean']} distinct={c['distinct']} nulls={c['nulls']}"
            )
        else:
            extra = ""
            if c.get("top_values"):
                tops = ", ".join(f"{pii_filter.scrub(str(v))}={n}" for v, n in c["top_values"])
                extra = f" top: {tops}"
            lines.append(f"- {c['name']} (text): distinct={c['distinct']} nulls={c['nulls']}{extra}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Parsing model output
# ---------------------------------------------------------------------------
def _extract_json(text: str) -> Optional[dict]:
    """Pull the first JSON object out of a model response, tolerating prose."""
    try:
        return json.loads(text)
    except Exception:  # noqa: BLE001
        pass
    match = re.search(r"\{.*\}", text, re.S)
    if match:
        try:
            return json.loads(match.group())
        except Exception:  # noqa: BLE001
            return None
    return None


def _coerce_bullets(value: Any) -> list[str]:
    """Normalise an explanation value (list, or bulleted/newline text) to a list."""
    if isinstance(value, list):
        items = [str(v).strip(" -*\t") for v in value]
    else:
        items = [ln.strip(" -*\t") for ln in str(value).splitlines()]
    items = [i for i in items if i]
    return items[:4]


# ---------------------------------------------------------------------------
# Summariser
# ---------------------------------------------------------------------------
class Summariser:
    """Turns an executed query into an AnswerSummary."""

    def __init__(
        self,
        llm: Optional[LLMClient] = None,
        model: Optional[str] = None,
        token_counter: Optional[TokenCounter] = None,
        scrub_pii: bool = True,
        max_preview_rows: int = _MAX_PREVIEW_ROWS,
    ) -> None:
        self.llm = llm
        self.model = model
        self.tokens = token_counter
        self.scrub_pii = scrub_pii
        # Token-safety: at or below this many rows we show them; above it we send
        # only a small sample plus the deterministic profile.
        self.max_preview_rows = max_preview_rows

    def rows_sent_to_model(self, n_rows: int) -> int:
        """How many raw rows would actually be placed in the prompt for n_rows."""
        return n_rows if n_rows <= self.max_preview_rows else _MAX_SAMPLE_ROWS

    def summarise(
        self,
        question: Union[Question, str],
        sql: Union[CandidateSQL, str],
        execution: ExecutionResult,
        schema: Optional[RetrievedSchema] = None,
    ) -> AnswerSummary:
        q_text = question.text if isinstance(question, Question) else str(question)
        sql_text = sql.sql if isinstance(sql, CandidateSQL) else str(sql)
        tables = list(schema.tables) if (schema and schema.tables) else extract_tables(sql_text)

        if execution and not execution.success:
            summary = AnswerSummary(
                answer="The query could not be completed, so there is no answer to show.",
                explanation=[f"The database reported: {execution.error or 'an unknown error'}."],
                tables_used=tables,
                sql=sql_text,
            )
            return self._finalise(summary)

        rows = execution.rows if execution else []
        columns = execution.columns if execution else []

        if self.llm is not None:
            answer = self._llm_answer(q_text, columns, rows, sql_text)
            explanation = self._llm_explanation(q_text, sql_text, schema)
        else:
            answer = self._fallback_answer(q_text, columns, rows)
            explanation = self._fallback_explanation(sql_text, tables)

        summary = AnswerSummary(
            answer=answer,
            explanation=explanation,
            tables_used=tables,
            sql=sql_text,
        )
        return self._finalise(summary)

    # -- LLM path -----------------------------------------------------------
    def _complete(self, prompt: str) -> str:
        response = self.llm.complete(prompt, model=self.model)  # type: ignore[union-attr]
        if self.tokens is not None:
            self.tokens.record(self.model or "unknown", prompt, response)
        return response

    def _llm_answer(self, question, columns, rows, sql) -> str:
        profile = profile_result(columns, rows)
        # Context safeguard: show full rows only for small results; otherwise a
        # small sample + the deterministic profile (which the model must trust).
        sample = rows if len(rows) <= self.max_preview_rows else rows[:_MAX_SAMPLE_ROWS]
        prompt = prompts.render(
            "summariser",
            question=question,
            columns=", ".join(str(c) for c in columns) or "(none)",
            row_count=len(rows),
            data_profile=_format_profile(profile),
            rows_preview=_rows_preview(columns, sample),
            sql=sql,
        )
        data = _extract_json(self._complete(prompt))
        if data and data.get("answer"):
            return str(data["answer"]).strip()
        return self._fallback_answer(question, columns, rows)

    def _llm_explanation(self, question, sql, schema) -> list[str]:
        prompt = prompts.render(
            "sql_explanation",
            question=question,
            sql=sql,
            schema_summary=_schema_summary(schema, sql),
        )
        data = _extract_json(self._complete(prompt))
        if data and data.get("explanation"):
            bullets = _coerce_bullets(data["explanation"])
            if bullets:
                return bullets
        return self._fallback_explanation(sql, extract_tables(sql))

    # -- Deterministic fallback (no LLM) ------------------------------------
    @staticmethod
    def _fallback_answer(question: str, columns, rows) -> str:
        if not rows:
            return "No matching records were found for this question."
        if len(rows) == 1 and len(rows[0]) == 1:
            return f"The result is {rows[0][0]}."
        if len(rows) == 1:
            pairs = ", ".join(f"{c}: {v}" for c, v in zip(columns, rows[0]))
            return f"The query returned a single record - {pairs}."
        return f"The query returned {len(rows)} records matching the question."

    @staticmethod
    def _fallback_explanation(sql: str, tables: list[str]) -> list[str]:
        s = sql.lower()
        bullets: list[str] = []
        if tables:
            noun = tables[0] if len(tables) == 1 else ", ".join(tables)
            bullets.append(f"We looked at the business records in: {noun}.")
        if len(tables) > 1 or " join " in s:
            bullets.append("We matched related records together to combine the information.")
        if " where " in s:
            bullets.append("We narrowed the records down to only those that meet the question's conditions.")
        if any(fn in s for fn in ("count(", "sum(", "avg(", "min(", "max(", "group by")):
            bullets.append("We summarised the matching records into totals or counts.")
        if " order by " in s:
            bullets.append("We ranked the results so the most relevant rows appear first.")
        return bullets[:4] or ["We read the relevant records and returned them directly."]

    # -- Output hygiene -----------------------------------------------------
    def _finalise(self, summary: AnswerSummary) -> AnswerSummary:
        if self.scrub_pii:
            return pii_filter.scrub_summary(summary)
        return summary
