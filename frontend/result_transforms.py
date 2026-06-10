"""In-memory result-set transforms for conversational follow-ups.

The agent's follow-up logic rewrites questions like "what about by region?" into
a standalone query and re-runs SQL against the whole database. That is right for
questions that need new data, but wrong for ones that only re-shape the rows the
user already sees ("sort them ascending", "just the top 3", "only the names").
Those should run on the previous result, instantly, with no database hit.

This module is that layer. Pure Python + pandas (no Streamlit, no network) so it
is unit-testable and reusable.

    classify(question)        -> is this a transform of the prior result?
    apply(question, prev_df)  -> TransformResult. ``applied`` = transformed in
                                 memory; ``fallback`` = re-query the database.

Conservative by design: a self-contained question ("total revenue by region")
is never treated as a transform, so it still goes to the database.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

# Words that point back at the previous result instead of the whole database.
_REFERENCE_WORDS = (
    "them", "those", "these", "they", "it", "this", "that", "result", "results",
    "list", "rows", "row", "data", "table", "above", "same", "previous", "ones",
)
_ASC_WORDS = (
    "ascending", "ascend", "asc", "increasing", "lowest first", "low to high",
    "smallest first", "a to z", "a-z", "alphabetical", "alphabetically",
)
_DESC_WORDS = (
    "descending", "descend", "desc", "decreasing", "highest first",
    "high to low", "largest first", "biggest first", "z to a", "z-a", "reverse",
)
_SORT_VERBS = ("sort", "order", "arrange", "rank", "reorder", "sorted", "ordered")
_SELECT_VERBS = ("only show", "show only", "just show", "just the", "only the",
                 "keep only", "keep just", "keep", "select")
_DROP_VERBS = ("drop", "remove", "without", "exclude", "hide")
_MEASURE_WORDS = ("revenue", "sales", "turnover", "profit", "margin",
                  "quantity", "units", "orders", "count", "price")

_COLUMN_ALIASES = {
    "revenue": ("revenue", "sales", "turnover", "total"),
    "sales": ("revenue", "sales", "turnover"),
    "profit": ("profit", "margin"), "margin": ("margin", "profit"),
    "quantity": ("quantity", "units", "qty"), "units": ("quantity", "units", "qty"),
    "price": ("price", "unit_price"),
    "name": ("name", "product", "customer"), "names": ("name", "product", "customer"),
    "product": ("product",), "products": ("product",), "customer": ("customer",),
    "company": ("company", "customer", "name"), "companies": ("company", "customer", "name"),
    "region": ("region",), "category": ("category",), "city": ("city",),
    "state": ("state",), "country": ("country",), "date": ("date", "month", "year", "quarter"),
}


@dataclass
class TransformResult:
    applied: bool = False
    fallback: bool = False
    fallback_reason: str = ""
    df: Optional[pd.DataFrame] = None
    description: str = ""
    ops: list = field(default_factory=list)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _has_any(text: str, words) -> bool:
    return any(re.search(rf"\b{re.escape(w)}\b", text) for w in words)


def _has_reference(text: str) -> bool:
    return _has_any(text, _REFERENCE_WORDS)


def _numeric_cols(df: pd.DataFrame) -> list:
    return df.select_dtypes(include="number").columns.tolist()


def _text_cols(df: pd.DataFrame) -> list:
    return [c for c in df.columns if c not in _numeric_cols(df)]


def _resolve_column(token: str, df: pd.DataFrame) -> Optional[str]:
    token = token.strip().lower().replace(" ", "_")
    lower = {c.lower(): c for c in df.columns}
    if token in lower:
        return lower[token]
    for c in df.columns:
        cl = c.lower()
        if token and (token in cl or cl in token):
            return c
    for alias, needles in _COLUMN_ALIASES.items():
        if token == alias or token.startswith(alias):
            for c in df.columns:
                if any(n in c.lower() for n in needles):
                    return c
    return None


def _primary_numeric(df: pd.DataFrame) -> Optional[str]:
    """Most likely 'measure' column: revenue/profit-like, else any non-id numeric."""
    nums = [c for c in _numeric_cols(df) if not c.lower().endswith("id")] or _numeric_cols(df)
    if not nums:
        return None
    for needle in ("revenue", "sales", "total", "profit", "amount", "value", "count"):
        for c in nums:
            if needle in c.lower():
                return c
    return nums[-1]


def _find_named_column(text: str, df: pd.DataFrame) -> Optional[str]:
    m = re.search(r"\b(?:by|on|using|per)\s+([a-z_ ]+?)(?:\s+(?:asc|desc|ascending|descending|order|first)|[?.!,]|$)", text)
    if m:
        col = _resolve_column(m.group(1).strip(), df)
        if col:
            return col
    for c in df.columns:
        if re.search(rf"\b{re.escape(c.lower().replace('_', ' '))}\b", text) or \
           re.search(rf"\b{re.escape(c.lower())}\b", text):
            return c
    for alias in _COLUMN_ALIASES:
        if re.search(rf"\b{re.escape(alias)}\b", text):
            col = _resolve_column(alias, df)
            if col:
                return col
    return None


def _transform_signals(text: str) -> dict:
    return {
        "sort": _has_any(text, _SORT_VERBS) or _has_any(text, _ASC_WORDS) or _has_any(text, _DESC_WORDS),
        "topn": bool(re.search(r"\b(top|bottom|first|last|highest|lowest)\s+\d+", text))
                 or bool(re.search(r"\b(limit|only|just|show me)\s+\d+\b", text))
                 or bool(re.search(r"\b\d+\s+(rows|records|results)\b", text)),
        "select": _has_any(text, _SELECT_VERBS) or _has_any(text, _DROP_VERBS),
        "filter": bool(re.search(r"\b(greater than|less than|more than|fewer than|at least|at most|over|under|above|below|between)\b", text))
                   or bool(re.search(r"\b(only|just|where|with|for)\b", text)),
    }


def classify(question: str) -> bool:
    """True when ``question`` looks like a transform of the previous result."""
    text = _norm(question)
    if not text:
        return False
    sig = _transform_signals(text)
    if not any(sig.values()):
        return False

    word_count = len(text.split())
    has_ref = _has_reference(text)

    # Self-contained ("<measure> by <dimension>") -> not a transform unless it
    # refers back ("them").
    self_contained = bool(re.search(r"\bby\s+[a-z]", text)) and _has_any(text, _MEASURE_WORDS)
    if self_contained and not has_ref:
        return False

    if sig["sort"] and (_has_any(text, _ASC_WORDS) or _has_any(text, _DESC_WORDS)):
        return True
    if re.search(r"\b(top|bottom|first|last)\s+\d+\b", text) and word_count <= 6:
        return True
    return has_ref or word_count <= 6


def _parse_sort(text: str, df: pd.DataFrame):
    if not (_has_any(text, _SORT_VERBS) or _has_any(text, _ASC_WORDS) or _has_any(text, _DESC_WORDS)):
        return None
    if _has_any(text, _DESC_WORDS):
        ascending = False
    elif _has_any(text, _ASC_WORDS):
        ascending = True
    else:
        ascending = False  # bare "sort"/"rank" -> highest first
    col = _find_named_column(text, df)
    if col is None:
        if _has_any(text, ("alphabetical", "alphabetically", "a to z", "a-z", "z to a", "z-a")):
            txt = _text_cols(df)
            col = txt[0] if txt else None
        if col is None:
            col = _primary_numeric(df) or (df.columns[0] if len(df.columns) else None)
    if col is None:
        return None
    return ("sort", col, ascending)


def _parse_topn(text: str, df: pd.DataFrame):
    for words, kind in (("top|highest|biggest|largest|best", "top"),
                        ("bottom|lowest|smallest|worst|least", "bottom")):
        m = re.search(rf"\b({words})\s+(\d+)", text)
        if m:
            return (kind, int(m.group(2)))
    m = re.search(r"\bfirst\s+(\d+)", text)
    if m:
        return ("head", int(m.group(1)))
    m = re.search(r"\blast\s+(\d+)", text)
    if m:
        return ("tail", int(m.group(1)))
    m = re.search(r"\b(?:limit|only|just|show me)\s+(\d+)\b", text)
    if m:
        return ("head", int(m.group(1)))
    m = re.search(r"\b(\d+)\s+(?:rows|records|results)\b", text)
    if m:
        return ("head", int(m.group(1)))
    return None


def _parse_select(text: str, df: pd.DataFrame):
    drop = _has_any(text, _DROP_VERBS)
    keep = _has_any(text, _SELECT_VERBS)
    if not (drop or keep):
        return None
    mentioned = []
    for c in df.columns:
        names = {c.lower(), c.lower().replace("_", " ")}
        if any(re.search(rf"\b{re.escape(n)}\b", text) for n in names):
            mentioned.append(c)
    for alias in _COLUMN_ALIASES:
        if re.search(rf"\b{re.escape(alias)}\b", text):
            col = _resolve_column(alias, df)
            if col and col not in mentioned:
                mentioned.append(col)
    if not mentioned:
        return None
    if drop and not keep:
        return ([c for c in df.columns if c not in mentioned], mentioned)
    return (mentioned, [c for c in df.columns if c not in mentioned])


def _parse_filter(text: str, df: pd.DataFrame):
    num_pat = re.search(
        r"\b(greater than|more than|over|above|at least|>=|>|less than|fewer than|under|below|at most|<=|<)\s*\$?([\d,.]+)",
        text)
    if num_pat:
        op_word, value = num_pat.group(1), float(num_pat.group(2).replace(",", ""))
        col = _find_named_column(text, df) or _primary_numeric(df)
        if col is not None and col in _numeric_cols(df):
            if op_word in ("greater than", "more than", "over", "above", ">"):
                return ("num", col, ">", value)
            if op_word in ("at least", ">="):
                return ("num", col, ">=", value)
            if op_word in ("less than", "fewer than", "under", "below", "<"):
                return ("num", col, "<", value)
            if op_word in ("at most", "<="):
                return ("num", col, "<=", value)

    cat_pat = re.search(
        r"\b(?:only|just|where|with|for|in)\s+([a-z0-9 &/\-]+?)"
        r"(?:\s+(?:region|category|state|city|country|product|customer))?[?.!,]?\s*$", text)
    if cat_pat:
        candidate = cat_pat.group(1).strip()
        noise = set(_ASC_WORDS) | set(_DESC_WORDS) | set(_SORT_VERBS) | {
            "order", "the", "a", "an", "them", "those", "these", "results", "result",
            "rows", "row", "list", "names", "name", "columns", "column", "data"}
        is_noise = bool(set(candidate.split()) & noise) or any(w in candidate for w in (_ASC_WORDS + _DESC_WORDS))
        if candidate and not is_noise:
            for c in _text_cols(df):
                vals = {str(v).lower(): str(v) for v in df[c].dropna().unique()}
                if candidate in vals:
                    return ("cat", c, "==", vals[candidate])
                for vlower, vreal in vals.items():
                    if len(candidate) >= 3 and (candidate in vlower or vlower in candidate):
                        return ("cat", c, "==", vreal)
            return ("missing", candidate)  # named a value not in current rows
    return None


def apply(question: str, prev_df: Optional[pd.DataFrame]) -> TransformResult:
    """Try to satisfy ``question`` by transforming ``prev_df`` in memory."""
    if prev_df is None or len(prev_df) == 0:
        return TransformResult(fallback=True, fallback_reason="no previous result to transform")

    text = _norm(question)
    df = prev_df.copy()
    ops: list = []

    filt = _parse_filter(text, df)
    if filt and filt[0] == "missing":
        return TransformResult(fallback=True,
                               fallback_reason=f"'{filt[1]}' is not in the current results - querying the database.")

    sort = _parse_sort(text, df)
    topn = _parse_topn(text, df)
    select = _parse_select(text, df)
    if not any((filt, sort, topn, select)):
        return TransformResult(fallback=True, fallback_reason="no transformable operation found")

    if filt:
        kind, col = filt[0], filt[1]
        if kind == "num":
            _, _, op, val = filt
            before = len(df)
            df = {">": df[df[col] > val], ">=": df[df[col] >= val],
                  "<": df[df[col] < val], "<=": df[df[col] <= val]}[op]
            ops.append(f"Filtered to {col} {op} {val:g} ({before} -> {len(df)} rows)")
        elif kind == "cat":
            _, _, _, val = filt
            before = len(df)
            df = df[df[col].astype(str) == str(val)]
            ops.append(f"Filtered to {col} = '{val}' ({before} -> {len(df)} rows)")

    if topn:
        kind, n = topn
        measure = _primary_numeric(df)
        if kind == "top" and measure:
            df = df.sort_values(measure, ascending=False)
            ops.append(f"Sorted by {measure} (high to low)")
            sort = None
        elif kind == "bottom" and measure:
            df = df.sort_values(measure, ascending=True)
            ops.append(f"Sorted by {measure} (low to high)")
            sort = None

    if sort:
        _, sort_col, sort_asc = sort
        df = df.sort_values(sort_col, ascending=sort_asc, kind="stable")
        ops.append(f"Sorted by {sort_col} ({'ascending' if sort_asc else 'descending'})")

    if topn:
        kind, n = topn
        if kind in ("top", "head", "bottom"):
            df = df.head(n)
        elif kind == "tail":
            df = df.tail(n)
        ops.append(f"Kept {len(df)} row(s)")

    if select:
        keep, _drop = select
        keep = [c for c in keep if c in df.columns]
        if keep:
            df = df[keep]
            ops.append(f"Showing columns: {', '.join(keep)}")

    return TransformResult(applied=True, df=df.reset_index(drop=True),
                           description="; ".join(ops), ops=ops)
