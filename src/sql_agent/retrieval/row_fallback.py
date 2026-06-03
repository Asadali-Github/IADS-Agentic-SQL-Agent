"""Vector / similarity row fallback — return nearest real rows when SQL yields 0.

Owner: retrieval slice; implemented by Asad for the end-to-end pipeline.

The hackathon brief: "if exact data doesn't exist, make vector-based decisions to
yield similar rows." This module is that requirement. When the agent generates
valid SQL but a string equality filter matches nothing (a typo, an out-of-stock
product, a wrong spelling), we don't return "No results". Instead we:

  1. find the string equality filters in the SQL (sqlglot),
  2. score every real distinct value of that column against the requested value,
  3. relax the SQL to the closest real value and re-run it,
  4. return those rows flagged as an APPROXIMATE match, with the substitution.

Scoring is pluggable: offline we use a fast lexical similarity (no deps); in
production set `similarity=` to an embedding-cosine function backed by OCI
Generative AI embeddings / Oracle 23ai Vector Search for true semantic matching.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Callable, Optional

import sqlglot
from sqlglot import exp

# A similarity function: (requested_value, candidate_value) -> score in [0, 1].
Similarity = Callable[[str, str], float]


def _lexical_similarity(a: str, b: str) -> float:
    """Token + character similarity; no embeddings needed (offline default)."""
    a, b = a.lower().strip(), b.lower().strip()
    if not a or not b:
        return 0.0
    char = SequenceMatcher(None, a, b).ratio()
    ta, tb = set(a.split()), set(b.split())
    token = len(ta & tb) / len(ta | tb) if (ta | tb) else 0.0
    contains = 0.85 if (a in b or b in a) else 0.0
    return max(char, token, contains)


@dataclass
class RowFallbackResult:
    """Outcome of a fallback attempt."""

    column: str
    requested_value: str
    matched_value: str
    score: float
    candidates: list[str]
    relaxed_sql: str
    result: object  # ExecutionResult
    approximate: bool = True


def _string_equality_filters(sql: str) -> list[tuple[str, str]]:
    """Return [(column, string_literal)] for `col = 'value'` predicates."""
    try:
        tree = sqlglot.parse_one(sql, read="oracle")
    except Exception:  # noqa: BLE001
        return []
    out: list[tuple[str, str]] = []
    for eq in tree.find_all(exp.EQ):
        col = eq.find(exp.Column)
        lit = eq.find(exp.Literal)
        if col is not None and lit is not None and lit.is_string:
            out.append((col.name.lower(), str(lit.this)))
    return out


def find_similar_rows(
    sql: str,
    executor,
    table: str = "product_sales",
    top_k: int = 5,
    threshold: float = 0.45,
    similarity: Optional[Similarity] = None,
) -> Optional[RowFallbackResult]:
    """If `sql` filters a text column to a value that doesn't exist, re-run it
    against the closest real value. Returns None if no fallback applies/helps."""
    sim = similarity or _lexical_similarity
    for column, requested in _string_equality_filters(sql):
        candidates = executor.execute(f"SELECT DISTINCT {column} FROM {table}")
        if not getattr(candidates, "success", False) or not candidates.rows:
            continue
        scored = sorted(
            ((sim(requested, str(r[0])), str(r[0])) for r in candidates.rows),
            key=lambda p: p[0], reverse=True,
        )
        if not scored or scored[0][0] < threshold:
            continue
        # already exact? then this column wasn't the problem
        if scored[0][0] >= 0.999 and scored[0][1].lower() == requested.lower():
            continue
        best = scored[0][1]
        relaxed = re.sub(rf"'{re.escape(requested)}'", f"'{best}'", sql)
        result = executor.execute(relaxed)
        if getattr(result, "success", False) and result.rows:
            return RowFallbackResult(
                column=column, requested_value=requested, matched_value=best,
                score=round(scored[0][0], 3),
                candidates=[c for _, c in scored[:top_k]],
                relaxed_sql=relaxed, result=result,
            )
    return None
