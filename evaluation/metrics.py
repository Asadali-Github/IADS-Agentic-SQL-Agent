"""Scoring metrics for the text-to-SQL benchmark.

Owner: Asad.

These are pure functions over result rows and per-case run records. No DB, no
LLM, no I/O - which makes them trivial to unit-test and safe to call hourly
during Day 2.

Metric definitions (see docs/EVALUATION.md for the full methodology):

  execution_accuracy  Did the generated SQL produce the SAME result set as the
                      reference SQL? Order-insensitive by default; order-sensitive
                      when the gold query has a meaningful ORDER BY (top-N etc.).
                      This is the headline number.

  exact_set_match     Do the two result sets contain exactly the same rows,
                      ignoring order and duplicates (set equality)? Slightly more
                      forgiving than execution_accuracy on duplicate handling.

  partial_match       What fraction of the expected rows appear in the actual
                      result? Recall over the expected set, in [0, 1]. Lets us
                      show partial credit instead of a hard pass/fail.

  retry_rate          Fraction of questions that needed at least one retry.

  latency p50 / p95   Median and tail end-to-end latency across the run.

  token_cost          Mean (and total) USD cost per request.
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Any, Iterable, Optional, Sequence

from sql_agent.core.models import CaseResult, Metric

Row = Sequence[Any]

# Floats are rounded to this many decimals before comparison so that
# 4200000.0 and 4200000.004 (rounding noise from SUM/AVG) count as equal.
FLOAT_TOLERANCE_DP = 4


# ---------------------------------------------------------------------------
# Row normalisation
# ---------------------------------------------------------------------------
def _norm_cell(value: Any) -> Any:
    """Normalise a single cell so cosmetic differences don't break equality."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return float(value)  # 5 and 5.0 are the same answer
    if isinstance(value, float):
        if math.isnan(value):
            return "NaN"
        return round(value, FLOAT_TOLERANCE_DP)
    if isinstance(value, str):
        return value.strip()
    if value is None:
        return None
    return value


def _norm_row(row: Row) -> tuple:
    return tuple(_norm_cell(c) for c in row)


def _multiset(rows: Iterable[Row]) -> Counter:
    return Counter(_norm_row(r) for r in rows)


def _set(rows: Iterable[Row]) -> set:
    return {_norm_row(r) for r in rows}


# ---------------------------------------------------------------------------
# Per-question comparisons (return primitives)
# ---------------------------------------------------------------------------
def execution_accuracy(
    expected: Sequence[Row],
    actual: Sequence[Row],
    order_matters: bool = False,
) -> bool:
    """True iff `actual` matches `expected` as result sets.

    With order_matters=False (default) this is multiset equality: same rows,
    same multiplicities, any order. With order_matters=True the rows must also
    appear in the same sequence (used for ORDER BY / top-N questions).
    """
    if order_matters:
        return [_norm_row(r) for r in expected] == [_norm_row(r) for r in actual]
    return _multiset(expected) == _multiset(actual)


def exact_set_match(expected: Sequence[Row], actual: Sequence[Row]) -> bool:
    """True iff the two result sets contain the same rows, ignoring order/dupes."""
    return _set(expected) == _set(actual)


def partial_match(expected: Sequence[Row], actual: Sequence[Row]) -> float:
    """Fraction of expected rows present in actual (recall over the row set)."""
    exp = _set(expected)
    if not exp:
        # An empty expected set is matched perfectly only by an empty actual set.
        return 1.0 if not actual else 0.0
    found = exp & _set(actual)
    return len(found) / len(exp)


# ---------------------------------------------------------------------------
# Aggregate statistics
# ---------------------------------------------------------------------------
def percentile(values: Sequence[float], pct: float) -> Optional[float]:
    """Linear-interpolated percentile (pct in [0, 100]); None for empty input."""
    xs = sorted(v for v in values if v is not None)
    if not xs:
        return None
    if len(xs) == 1:
        return float(xs[0])
    rank = (pct / 100.0) * (len(xs) - 1)
    lo = math.floor(rank)
    hi = math.ceil(rank)
    if lo == hi:
        return float(xs[lo])
    frac = rank - lo
    return float(xs[lo] + (xs[hi] - xs[lo]) * frac)


def retry_rate(cases: Sequence[CaseResult]) -> float:
    """Fraction of cases that needed at least one retry."""
    if not cases:
        return 0.0
    return sum(1 for c in cases if c.retries > 0) / len(cases)


def mean(values: Sequence[float]) -> Optional[float]:
    xs = [v for v in values if v is not None]
    return sum(xs) / len(xs) if xs else None


# ---------------------------------------------------------------------------
# Semantic / AST-level SQL comparison (robust to formatting & schema churn)
# ---------------------------------------------------------------------------
# Why: static expected_rows break the instant the schema or seed data changes,
# and exact SQL string matching breaks on a renamed alias or reflowed whitespace.
# Comparing the *logic* of two queries via their parsed AST is far more durable.
# Execution accuracy stays the headline metric; ast_match is a schema-change-
# robust secondary signal (and the only signal available when we cannot execute).

import sqlglot  # noqa: E402
from sqlglot import exp  # noqa: E402

# Commutative operators whose operand order is irrelevant to meaning.
_COMMUTATIVE = (exp.EQ, exp.NEQ, exp.And, exp.Or, exp.Add, exp.Mul)


def canonicalize_sql(sql: str, dialect: str = "oracle") -> Optional[str]:
    """Return a canonical form of `sql`, or None if it cannot be parsed.

    Canonicalisation removes column aliases, lowercases identifiers, standardises
    formatting, and sorts the operands of commutative operators - so two queries
    that mean the same thing produce the same string.
    """
    try:
        tree = sqlglot.parse_one(sql, read=dialect)
    except Exception:  # noqa: BLE001
        return None
    for alias in list(tree.find_all(exp.Alias)):
        alias.replace(alias.this)
    for node in list(tree.walk(bfs=False)):
        node = node[0] if isinstance(node, tuple) else node
        if isinstance(node, _COMMUTATIVE):
            left, right = node.left, node.right
            if left is not None and right is not None and left.sql() > right.sql():
                node.set("this", right)
                node.set("expression", left)
    try:
        return tree.sql(dialect=dialect, normalize=True, comments=False).lower()
    except Exception:  # noqa: BLE001
        return None


def sql_ast_match(expected_sql: str, actual_sql: str, dialect: str = "oracle") -> bool:
    """True if the two queries are logically equivalent at the AST level."""
    ce = canonicalize_sql(expected_sql, dialect)
    ca = canonicalize_sql(actual_sql, dialect)
    return ce is not None and ce == ca


def _fingerprint(sql: str, dialect: str = "oracle") -> Optional[dict]:
    try:
        t = sqlglot.parse_one(sql, read=dialect)
    except Exception:  # noqa: BLE001
        return None
    select = t.find(exp.Select)
    return {
        "tables": frozenset(n.name.lower() for n in t.find_all(exp.Table)),
        "funcs": frozenset(f.sql_name().upper() for f in t.find_all(exp.Func)),
        "join": bool(list(t.find_all(exp.Join))),
        "where": bool(t.find(exp.Where)),
        "group": bool(t.find(exp.Group)),
        "order": bool(t.find(exp.Order)),
        "having": bool(t.find(exp.Having)),
        "n_select": len(select.expressions) if select else 0,
    }


def sql_structural_similarity(expected_sql: str, actual_sql: str, dialect: str = "oracle") -> float:
    """Coarse [0,1] similarity of two queries' structure (tables/funcs/clauses).

    Useful for partial credit and debugging near-misses when ast_match is False.
    """
    fe, fa = _fingerprint(expected_sql, dialect), _fingerprint(actual_sql, dialect)
    if fe is None or fa is None:
        return 0.0
    score, total = 0.0, 0.0
    for key in ("tables", "funcs"):
        union = fe[key] | fa[key]
        total += 1.0
        score += (len(fe[key] & fa[key]) / len(union)) if union else 1.0
    for key in ("join", "where", "group", "order", "having"):
        total += 1.0
        score += 1.0 if fe[key] == fa[key] else 0.0
    total += 1.0
    score += 1.0 if fe["n_select"] == fa["n_select"] else 0.0
    return round(score / total, 4)


# ---------------------------------------------------------------------------
# Headline metric set for a whole run
# ---------------------------------------------------------------------------
def compute_metrics(cases: Sequence[CaseResult]) -> list[Metric]:
    """Roll a list of per-case results up into the headline Metric list.

    This is what the benchmark harness writes into BenchmarkResult.metrics and
    what the slide deck reads.
    """
    n = len(cases)
    if n == 0:
        return [Metric(name="execution_accuracy", value=0.0, unit="ratio", detail="no cases")]

    ex_acc = sum(1 for c in cases if c.execution_match) / n
    set_acc = sum(1 for c in cases if c.exact_set_match) / n
    part = mean([c.partial_match for c in cases]) or 0.0
    rr = retry_rate(cases)
    latencies = [c.latency_ms for c in cases if c.latency_ms is not None]
    costs = [c.token_cost_usd for c in cases if c.token_cost_usd is not None]

    metrics = [
        Metric(name="execution_accuracy", value=round(ex_acc, 4), unit="ratio",
               detail=f"{sum(c.execution_match for c in cases)}/{n} questions"),
        Metric(name="exact_set_match", value=round(set_acc, 4), unit="ratio"),
        Metric(name="ast_match", value=round(sum(1 for c in cases if c.ast_match) / n, 4),
               unit="ratio", detail="logic-level SQL equivalence (schema-change robust)"),
        Metric(name="partial_match", value=round(part, 4), unit="ratio",
               detail="mean row recall over expected set"),
        Metric(name="retry_rate", value=round(rr, 4), unit="ratio",
               detail=f"{sum(1 for c in cases if c.retries > 0)}/{n} needed a retry"),
    ]

    p50 = percentile(latencies, 50)
    p95 = percentile(latencies, 95)
    if p50 is not None:
        metrics.append(Metric(name="latency_p50_ms", value=round(p50, 1), unit="ms"))
    if p95 is not None:
        metrics.append(Metric(name="latency_p95_ms", value=round(p95, 1), unit="ms"))

    avg_cost = mean(costs)
    if avg_cost is not None:
        metrics.append(Metric(name="token_cost_per_request_usd", value=round(avg_cost, 6),
                              unit="usd", detail=f"total ${round(sum(costs), 4)} over {len(costs)} calls"))

    # Per-tier execution accuracy (easy/medium/hard) for the slide breakdown.
    for tier in ("easy", "medium", "hard"):
        tier_cases = [c for c in cases if c.difficulty and c.difficulty.value == tier]
        if tier_cases:
            acc = sum(1 for c in tier_cases if c.execution_match) / len(tier_cases)
            metrics.append(Metric(name=f"execution_accuracy_{tier}", value=round(acc, 4),
                                  unit="ratio", detail=f"{len(tier_cases)} questions"))

    return metrics
