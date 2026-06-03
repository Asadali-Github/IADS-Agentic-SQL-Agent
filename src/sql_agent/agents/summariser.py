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
    ChartSpec,
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


_AGG_DESC = {"SUM": "a total", "AVG": "an average", "COUNT": "a count"}


def detect_clarification(question: str):
    """Return a clarifying question if a term in `question` is ambiguous, else None.

    Uses the business glossary: when a phrase resolves to two different canonical
    terms with near-identical confidence but different meanings (different target
    column or different default aggregation), we ask rather than guess. Example:
    "margin" could mean total profit (a sum) or profit margin (profit / revenue).
    """
    try:
        from sql_agent.retrieval.glossary import GlossaryResolver, _ngrams, _norm
    except Exception:  # noqa: BLE001 - glossary optional
        return None
    try:
        resolver = GlossaryResolver()
    except Exception:  # noqa: BLE001 - glossary file missing
        return None

    for span in _ngrams(_norm(question or ""), max_n=3):
        matches = resolver.resolve(span, top_k=2, threshold=0.85)
        if len(matches) < 2:
            continue
        a, b = matches[0], matches[1]
        # Genuine ambiguity = the SAME surface word maps to two different meanings
        # (not two different terms appearing in one phrase).
        same_surface = a.matched_via == b.matched_via
        close = abs(a.score - b.score) <= 0.08 and a.score >= 0.9
        clean = a.method in ("exact", "contains") and b.method in ("exact", "contains")
        different = a.canonical != b.canonical and (
            a.maps_to != b.maps_to or a.default_aggregation != b.default_aggregation
        )
        if same_surface and close and clean and different:
            da = _AGG_DESC.get(a.default_aggregation or "", a.canonical)
            db = _AGG_DESC.get(b.default_aggregation or "", b.canonical)
            return (f"By '{a.matched_via}', did you mean {a.canonical} ({da}) "
                    f"or {b.canonical} ({db})?")
    return None


def confidence_score(execution_ok: bool, n_rows: int, has_clarification: bool) -> float:
    """A simple, honest confidence heuristic in [0, 1]."""
    if not execution_ok:
        return 0.2
    score = 0.9
    if has_clarification:
        score = min(score, 0.55)
    if n_rows == 0:
        score = min(score, 0.5)
    return round(score, 2)


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


_TEMPORAL_HINTS = ("month", "date", "year", "day", "quarter", "week", "period")
_MONEY_HINTS = ("revenue", "profit", "price", "sales", "spend", "amount", "cost", "value")
_PCT_HINTS = ("pct", "percent", "margin", "share", "ratio", "rate", "growth")


def _is_temporal(name: str) -> bool:
    n = str(name).lower()
    return any(h in n for h in _TEMPORAL_HINTS)


def _is_money(name: str) -> bool:
    n = str(name).lower()
    return any(h in n for h in _MONEY_HINTS) and not any(h in n for h in _PCT_HINTS)


def _is_pct(name: str) -> bool:
    return any(h in str(name).lower() for h in _PCT_HINTS)


def _humanize_money(v: float) -> str:
    a = abs(v)
    if a >= 1e9:
        return f"${v/1e9:.1f}B"
    if a >= 1e6:
        return f"${v/1e6:.1f}M"
    if a >= 1e3:
        return f"${v/1e3:.1f}K"
    return f"${v:,.2f}"


def _plural(word: str) -> str:
    w = str(word)
    if w.endswith("y") and len(w) > 1 and w[-2] not in "aeiou":
        return w[:-1] + "ies"
    if w.endswith(("s", "x", "z", "ch", "sh")):
        return w + "es"
    return w + "s"


def _fmt(colname: str, v) -> str:
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return str(v)
    if _is_pct(colname):
        return f"{v:.1f}%"
    if _is_money(colname):
        return _humanize_money(float(v))
    return f"{v:,.0f}" if float(v).is_integer() else f"{v:,.2f}"


def _column_roles(columns, rows, profile=None):
    """Return (dimension_col_idx, measure_col_idx, is_temporal). Best-effort."""
    profile = profile or profile_result(columns, rows)
    dim_idx = measure_idx = None
    _skip = ("rank", "rn", "rnk", "quartile", "ntile")
    for i, c in enumerate(profile["columns"]):
        name = c["name"]
        low = str(name).lower()
        if c["dtype"] == "numeric":
            # a measure is a numeric column that is not an id, rank, or a
            # temporal key (month/year from EXTRACT belongs on the axis).
            if (measure_idx is None and not low.endswith("id")
                    and low not in _skip and not _is_temporal(name)):
                measure_idx = i
        elif dim_idx is None:
            dim_idx = i
    # a numeric temporal column (e.g. month from EXTRACT) can be the dimension
    if dim_idx is None:
        for i, c in enumerate(profile["columns"]):
            if _is_temporal(c["name"]) and i != measure_idx:
                dim_idx = i
                break
    temporal = dim_idx is not None and _is_temporal(profile["columns"][dim_idx]["name"])
    return dim_idx, measure_idx, temporal


def generate_insights(question, columns, rows, profile=None):
    """Deterministic business insights computed from the rows (no hallucination)."""
    if not rows:
        return []
    profile = profile or profile_result(columns, rows)
    # single scalar -> the answer already states it; no extra insight
    if len(rows) == 1 and len(columns) == 1:
        return []
    dim_idx, measure_idx, temporal = _column_roles(columns, rows, profile)
    if dim_idx is None or measure_idx is None:
        return []
    dname, mname = columns[dim_idx], columns[measure_idx]
    pairs = [(r[dim_idx], r[measure_idx]) for r in rows
             if dim_idx < len(r) and measure_idx < len(r) and isinstance(r[measure_idx], (int, float)) and not isinstance(r[measure_idx], bool)]
    if not pairs:
        return []
    insights = []

    if temporal:
        first_x, first_v = pairs[0]
        last_x, last_v = pairs[-1]
        if first_v:
            change = (last_v - first_v) / abs(first_v) * 100
            direction = "rose" if change >= 0 else "fell"
            insights.append(f"{mname} {direction} {abs(change):.0f}% from {first_x} ({_fmt(mname, first_v)}) to {last_x} ({_fmt(mname, last_v)}).")
        peak_x, peak_v = max(pairs, key=lambda p: p[1])
        insights.append(f"{mname} peaked at {peak_x} with {_fmt(mname, peak_v)}.")
        return insights[:3]

    ordered = sorted(pairs, key=lambda p: p[1], reverse=True)
    top_x, top_v = ordered[0]
    bottom_x, bottom_v = ordered[-1]
    if _is_pct(mname):
        # Share-of-total is meaningless for a percentage measure; just rank.
        insights.append(f"{top_x} has the highest {mname} at {_fmt(mname, top_v)}.")
        if bottom_x != top_x:
            insights.append(f"{bottom_x} has the lowest at {_fmt(mname, bottom_v)} "
                            f"({top_v - bottom_v:.1f} points below {top_x}).")
        return insights[:3]
    total = sum(v for _, v in pairs)
    if total:
        share = top_v / total * 100
        insights.append(f"{top_x} leads {mname} with {_fmt(mname, top_v)} ({share:.0f}% of the total).")
        if share >= 40:
            insights.append(f"Results are concentrated: {top_x} alone is over {share:.0f}% of {mname}.")
        elif len(ordered) >= 3:
            top3 = sum(v for _, v in ordered[:3]) / total * 100
            insights.append(f"The top 3 {dname}s account for {top3:.0f}% of {mname}.")
    if len(ordered) >= 2 and bottom_x != top_x:
        insights.append(f"{bottom_x} is lowest at {_fmt(mname, bottom_v)}.")
    return insights[:3]


def suggest_chart(question, columns, rows, profile=None):
    """Recommend a chart shape for the result set."""
    if not rows or (len(rows) == 1 and len(columns) == 1):
        return ChartSpec(type="none", reason="A single value is best shown as text.")
    profile = profile or profile_result(columns, rows)
    dim_idx, measure_idx, temporal = _column_roles(columns, rows, profile)
    if dim_idx is None or measure_idx is None:
        return ChartSpec(type="none", reason="No clear category/measure pair to plot.")
    x, y = columns[dim_idx], columns[measure_idx]
    title = (question or "").strip().rstrip("?")[:80] or None
    if temporal:
        return ChartSpec(type="line", x=x, y=y, title=title, reason="A measure over time reads best as a line.")
    if _is_pct(y):
        return ChartSpec(type="bar", x=x, y=y, title=title, reason="Comparing percentages across categories.")
    if len(rows) <= 6:
        return ChartSpec(type="pie", x=x, y=y, title=title, reason="A few categories summing to a total suit a pie.")
    return ChartSpec(type="bar", x=x, y=y, title=title, reason="Comparing a measure across categories.")


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
                chart=ChartSpec(type="none", reason="No result to chart."),
                clarification=detect_clarification(q_text),
                confidence=confidence_score(False, 0, False),
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

        clarification = detect_clarification(q_text)
        summary = AnswerSummary(
            answer=answer,
            explanation=explanation,
            insights=generate_insights(q_text, columns, rows),
            chart=suggest_chart(q_text, columns, rows),
            clarification=clarification,
            tables_used=tables,
            sql=sql_text,
            confidence=confidence_score(True, len(rows), bool(clarification)),
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
            return f"The result is {_fmt(columns[0] if columns else '', rows[0][0])}."
        if len(rows) == 1:
            pairs = ", ".join(f"{c}: {_fmt(c, v)}" for c, v in zip(columns, rows[0]))
            return f"The query returned a single record - {pairs}."
        # Multi-row: name the leading row on its measure - a real answer, not a count.
        dim_idx, measure_idx, _ = _column_roles(columns, rows)
        if dim_idx is not None and measure_idx is not None:
            try:
                top = max(rows, key=lambda r: r[measure_idx])
                dname, mname = columns[dim_idx], columns[measure_idx]
                return (f"{top[dim_idx]} had the highest {mname} "
                        f"({_fmt(mname, top[measure_idx])}), across {len(rows)} {_plural(dname)}.")
            except Exception:  # noqa: BLE001
                pass
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
