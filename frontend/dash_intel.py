"""Dashboard intelligence: proactive, data-aware guidance for the frontend.

Pure Python + pandas (no Streamlit) so it is testable and reusable. Each helper
reads a result DataFrame and the user's question and returns guidance the UI
renders:

* :func:`suggest_followups`  - context-aware next questions (clickable chips).
* :func:`recommend_charts`   - ranked chart options for the smart viz picker.
* :func:`compute_insights`   - auto highlights + anomalies above the chart.
* :func:`analyze_intent`     - what the agent understood, before/with the answer.
* :func:`explain_answer`     - a plain-English paragraph describing the result.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

import pandas as pd

try:  # allow running both as a package and as a flat module (Streamlit cwd)
    import result_transforms as rt  # type: ignore
except Exception:  # pragma: no cover
    from frontend import result_transforms as rt  # type: ignore

_numeric_cols = rt._numeric_cols
_text_cols = rt._text_cols
_primary_numeric = rt._primary_numeric
_is_transform = rt.classify

# Dimensions the dataset can usually be broken down by, for drill-down ideas.
_KNOWN_DIMENSIONS = ("region", "category", "sub_category", "state", "city",
                     "country", "product_name", "customer_name", "segment", "month")


def _humanize(col: str) -> str:
    return str(col).replace("_", " ").title()


def _fmt(v) -> str:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return str(v)
    if abs(v) >= 1_000_000:
        return f"{v/1_000_000:,.1f}M"
    if abs(v) >= 1_000:
        return f"{v/1_000:,.1f}K"
    if v == int(v):
        return f"{int(v):,}"
    return f"{v:,.2f}"


@dataclass
class Suggestion:
    label: str          # button text shown to the user
    query: str          # the question submitted when clicked
    kind: str           # "transform" (instant, in-memory) | "drilldown" (DB)


def suggest_followups(df: pd.DataFrame, question: str = "") -> list:
    """Return 3-6 data-aware next questions, preferring instant in-memory ones."""
    if df is None or len(df) == 0:
        return []

    out: list = []
    measure = _primary_numeric(df)
    texts = _text_cols(df)
    n_rows = len(df)

    if measure:
        m = _humanize(measure)
        out.append(Suggestion(f"Sort by {m} (ascending)", f"sort them by {measure} ascending", "transform"))
        out.append(Suggestion(f"Sort by {m} (descending)", f"sort them by {measure} descending", "transform"))
        if n_rows > 5:
            out.append(Suggestion(f"Top 5 by {m}", "show the top 5", "transform"))
            out.append(Suggestion(f"Bottom 5 by {m}", "show the bottom 5", "transform"))

    if texts and measure:
        out.append(Suggestion(f"Show only {_humanize(texts[0])} & {_humanize(measure)}",
                              f"only show {texts[0]} and {measure}", "transform"))

    asked = (question or "").lower()
    for dim in _KNOWN_DIMENSIONS:
        if dim in df.columns or dim in asked:
            continue
        if measure:
            out.append(Suggestion(f"Break {_humanize(measure)} down by {_humanize(dim)}",
                                  f"total {measure} by {dim}", "drilldown"))
        if len([s for s in out if s.kind == "drilldown"]) >= 2:
            break

    seen, deduped = set(), []
    for s in out:
        if s.label not in seen:
            seen.add(s.label)
            deduped.append(s)
    return deduped[:6]


@dataclass
class ChartOption:
    type: str           # bar | line | pie | scatter | table | metric
    label: str
    x: Optional[str]
    y: Optional[str]
    reason: str
    recommended: bool = False


def recommend_charts(df: pd.DataFrame) -> list:
    """Rank chart types for this result; the first is the recommended default."""
    if df is None or len(df) == 0:
        return []

    nums = _numeric_cols(df)
    texts = _text_cols(df)
    date_cols = [c for c in df.columns
                 if any(k in c.lower() for k in ("date", "month", "year", "quarter", "week", "day"))]
    n = len(df)
    opts: list = []

    if n == 1 and len(nums) == 1:
        label = str(df[texts[0]].iloc[0]) if texts else _humanize(nums[0])
        opts.append(ChartOption("metric", "Metric", None, nums[0],
                                f"A single value - best shown as a KPI ({label}).", True))
        opts.append(ChartOption("table", "Table", None, None, "Raw value.", False))
        return opts

    measure = _primary_numeric(df)

    if date_cols and nums:
        opts.append(ChartOption("line", "Line", date_cols[0], measure or nums[0],
                                f"{_humanize(measure or nums[0])} over time reads best as a line.", True))

    if texts and measure:
        opts.append(ChartOption("bar", "Bar", texts[0], measure,
                                f"Comparing {_humanize(measure)} across {_humanize(texts[0])}.",
                                recommended=not (date_cols and nums)))
        if 2 <= n <= 6:
            opts.append(ChartOption("pie", "Pie / Donut", texts[0], measure,
                                    f"Only {n} categories - a donut shows each one's share.", False))

    if len(nums) >= 2 and n > 3:
        opts.append(ChartOption("scatter", "Scatter", nums[0], nums[1],
                                f"Relationship between {_humanize(nums[0])} and {_humanize(nums[1])}.", False))

    opts.append(ChartOption("table", "Table", None, None, "Full detail, every column and row.", not opts))

    # Exactly one recommended.
    rec_seen = False
    for o in opts:
        if o.recommended and not rec_seen:
            rec_seen = True
        else:
            o.recommended = False
    if not rec_seen and opts:
        opts[0].recommended = True
    return opts


def compute_insights(df: pd.DataFrame, max_items: int = 5) -> list:
    """Notable highlights and simple anomaly flags from the result."""
    if df is None or len(df) == 0:
        return []

    insights: list = []
    nums = _numeric_cols(df)
    texts = _text_cols(df)
    measure = _primary_numeric(df)
    n = len(df)

    if measure and n > 1:
        s = df[measure]
        total = s.sum()
        top_idx, bot_idx = s.idxmax(), s.idxmin()
        label_col = texts[0] if texts else None

        if label_col is not None:
            top_name, bot_name = df.loc[top_idx, label_col], df.loc[bot_idx, label_col]
            top_share = (s.loc[top_idx] / total * 100) if total else 0
            insights.append(f"{top_name} leads with {_fmt(s.loc[top_idx])} {_humanize(measure)}"
                            + (f" ({top_share:.0f}% of the total)." if total else "."))
            insights.append(f"{bot_name} is lowest at {_fmt(s.loc[bot_idx])} {_humanize(measure)}.")
        insights.append(f"Total {_humanize(measure)} across {n} rows: {_fmt(total)} (avg {_fmt(s.mean())}).")

        if n >= 4 and s.std(ddof=0) > 0:
            z = (s - s.mean()) / s.std(ddof=0)
            outliers = z[abs(z) >= 2]
            if len(outliers) and texts:
                oi = outliers.abs().idxmax()
                direction = "above" if z.loc[oi] > 0 else "below"
                insights.append(f"Outlier: {df.loc[oi, texts[0]]} is well {direction} the rest "
                                f"at {_fmt(s.loc[oi])} {_humanize(measure)}.")
    elif measure and n == 1:
        insights.append(f"Single value: {_humanize(measure)} = {_fmt(df[measure].iloc[0])}.")

    if not insights and nums:
        insights.append(f"{n} rows, {len(df.columns)} columns returned.")
    return insights[:max_items]


def analyze_intent(question: str, prev_df: Optional[pd.DataFrame]) -> dict:
    """Describe what the agent will do *before* it runs."""
    q = (question or "").strip()
    is_followup = bool(prev_df is not None and len(prev_df) and _is_transform(q))

    info: dict = {
        "question": q,
        "mode": "Follow-up on previous result" if is_followup else "New database query",
        "uses_previous_result": is_followup,
        "operations": [], "measure": None, "dimension": None,
    }

    if is_followup and prev_df is not None:
        tr = rt.apply(q, prev_df)
        if tr.applied:
            info["operations"] = tr.ops
        elif tr.fallback:
            info["mode"] = "New database query"
            info["uses_previous_result"] = False
            info["note"] = tr.fallback_reason
        return info

    low = q.lower()
    for meas in ("revenue", "sales", "profit", "margin", "quantity", "units", "orders", "count", "price"):
        if re.search(rf"\b{meas}\b", low):
            info["measure"] = meas
            break
    for dim in _KNOWN_DIMENSIONS + ("region", "category", "product", "customer", "month", "year"):
        if re.search(rf"\b{dim.replace('_', ' ')}\b", low) or re.search(rf"\b{dim}\b", low):
            info["dimension"] = dim.replace("_", " ")
            break
    return info


def explain_answer(df: pd.DataFrame, question: str = "") -> str:
    """A short paragraph explaining what the result shows, in plain English."""
    if df is None or len(df) == 0:
        return "No rows matched - try widening the question or removing a filter."

    nums = _numeric_cols(df)
    texts = _text_cols(df)
    measure = _primary_numeric(df)
    n = len(df)

    if n == 1 and len(nums) == 1:
        return f"This is a single figure: {_humanize(nums[0])} of {_fmt(df[nums[0]].iloc[0])}."

    cols_preview = ", ".join(_humanize(c) for c in df.columns[:5]) + ("..." if len(df.columns) > 5 else "")
    parts = [f"The result has {n} row{'s' if n != 1 else ''} and "
             f"{len(df.columns)} column{'s' if len(df.columns) != 1 else ''} ({cols_preview})."]

    if measure and texts and n > 1:
        s = df[measure]
        top_name = df.loc[s.idxmax(), texts[0]]
        parts.append(f"{_humanize(texts[0])} is broken down by {_humanize(measure)}; "
                     f"{top_name} is the highest at {_fmt(s.max())}, and the values total {_fmt(s.sum())}.")
    elif measure and n > 1:
        s = df[measure]
        parts.append(f"{_humanize(measure)} ranges from {_fmt(s.min())} to {_fmt(s.max())}, "
                     f"averaging {_fmt(s.mean())}.")
    return " ".join(parts)
