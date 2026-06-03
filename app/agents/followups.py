"""Shared, conservative follow-up resolution for multi-turn questions.

This is the single source of truth used by BOTH backends:

* the live Oracle path  (app.agents.memory.ConversationMemory), and
* the offline DuckDB path (app.pipeline.FullPipeline._resolve_followup).

Design goals (why this module exists)
--------------------------------------
The agent must answer every question *from the database*, not from the previous
turn. Earlier versions treated almost any short question as a "follow-up" and
then pasted the previous question **and its SQL** into the next prompt. The SQL
generator, seeing a ready-made query, simply echoed it back — so the second
question was answered with the first question's data ("answering from memory,
not the database").

This module fixes that with two rules:

1.  ``looks_like_follow_up`` is *conservative*. A question that already stands on
    its own (it names both a measure and a dimension, e.g. "total sales by
    region") is NEVER treated as a follow-up, regardless of length. Only
    genuinely elliptical questions ("what about profit?", "and by region?")
    continue the previous turn.

2.  ``rewrite_follow_up`` produces a clean, standalone natural-language question
    by swapping the new measure/dimension into the *previous question text*. It
    never emits SQL and never asks the generator to reuse a prior query, so the
    database is always queried afresh.
"""

from __future__ import annotations

import re

# --- Business vocabulary -----------------------------------------------------
# Measures (the thing being aggregated) and dimensions (the thing it is grouped
# or filtered by). Kept deliberately small and schema-agnostic — these are only
# used to (a) decide whether a question is self-contained and (b) swap terms
# when rewriting a follow-up. Order matters: longer phrases first so e.g.
# "sub category" wins over "category".
MEASURE_WORDS: tuple[str, ...] = (
    "revenue",
    "sales",
    "turnover",
    "profit",
    "margin",
    "units",
    "unit",
    "quantity",
    "orders",
    "order",
    "count",
)

DIMENSION_WORDS: tuple[str, ...] = (
    "sub category",
    "sub-category",
    "subcategory",
    "category",
    "categories",
    "region",
    "regions",
    "state",
    "states",
    "country",
    "countries",
    "city",
    "cities",
    "product",
    "products",
    "customer",
    "customers",
    "segment",
    "segments",
    "channel",
    "channels",
    "store",
    "stores",
    "month",
    "months",
    "quarter",
    "quarters",
    "year",
    "years",
)

# Explicit "this continues the previous turn" signals.
TRIGGER_PREFIXES: tuple[str, ...] = (
    "what about",
    "how about",
    "what if",
    "and by",
    "and for",
    "and ",
    "also",
    "now ",
    "then ",
    "instead",
    "same",
    "compare",
    "break ",
    "drill ",
    "by ",
    "for ",
)

# Whole-word markers that, anywhere in a short question, signal continuation.
FOLLOW_UP_MARKERS: frozenset[str] = frozenset(
    {"instead", "also", "same", "compare", "again", "those", "that"}
)


def _normalize(question: str) -> str:
    return re.sub(r"\s+", " ", (question or "").strip().lower())


def _word_regex(words: tuple[str, ...]) -> re.Pattern[str]:
    # Escape, allow a space or hyphen to match interchangeably inside phrases,
    # and require word boundaries so "order" does not match "ordered".
    parts = [re.escape(w).replace(r"\ ", r"[ \-]") for w in words]
    return re.compile(r"\b(?:" + "|".join(parts) + r")\b", re.IGNORECASE)


_MEASURE_RE = _word_regex(MEASURE_WORDS)
_DIMENSION_RE = _word_regex(DIMENSION_WORDS)


def _has_measure(text: str) -> bool:
    return _MEASURE_RE.search(text) is not None


def _has_dimension(text: str) -> bool:
    return _DIMENSION_RE.search(text) is not None


def _starts_with_trigger(normalized: str) -> bool:
    return any(
        normalized == trigger.strip() or normalized.startswith(trigger)
        for trigger in TRIGGER_PREFIXES
    )


def looks_like_follow_up(question: str) -> bool:
    """Return True only for genuinely elliptical follow-up questions.

    A self-contained question (one that names both a measure and a dimension,
    such as "total sales by region") is treated as standalone even when it is
    short, so it is always answered with a fresh database query.
    """
    normalized = _normalize(question)
    if not normalized:
        return False

    words = normalized.split()
    has_measure = _has_measure(normalized)
    has_dimension = _has_dimension(normalized)
    starts_trigger = _starts_with_trigger(normalized)
    has_marker = bool(FOLLOW_UP_MARKERS & set(words))

    # 1) Fully self-contained question -> NOT a follow-up. This is the key guard
    #    that stops standalone questions from being merged with the prior turn.
    if has_measure and has_dimension and not starts_trigger and not has_marker:
        return False

    # 2) Explicit continuation signal ("what about ...", "and by ...", "also").
    if starts_trigger or has_marker:
        return True

    # 3) Bare elliptical fragment: very short and supplying only one of
    #    measure/dimension (e.g. "profit?", "by region"). Longer fragments are
    #    treated as standalone and queried fresh.
    if len(words) <= 3 and (has_measure != has_dimension):
        return True

    return False


def _first_match(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    return match.group(0) if match else None


def rewrite_follow_up(question: str, previous_question: str) -> str | None:
    """Rewrite an elliptical follow-up into a standalone question.

    Uses the *previous question text* (never its SQL) as a template and swaps in
    the new measure and/or dimension mentioned in the follow-up. Returns the
    rewritten standalone question, or ``None`` when there is nothing to swap (in
    which case callers should fall back to the raw question and still query the
    database).
    """
    previous_question = (previous_question or "").strip()
    if not previous_question:
        return None

    normalized = _normalize(question)
    new_measure = _first_match(_MEASURE_RE, normalized)
    new_dimension = _first_match(_DIMENSION_RE, normalized)

    if not new_measure and not new_dimension:
        return None

    rewritten = previous_question

    # Swap the measure term, e.g. "...total sales..." -> "...total profit...".
    if new_measure:
        if _MEASURE_RE.search(rewritten):
            rewritten = _MEASURE_RE.sub(new_measure, rewritten, count=1)
        # If the previous question had no measure we leave it untouched rather
        # than guess where the measure belongs.

    # Swap or append the dimension term, e.g. "...by category" -> "...by region",
    # or "total revenue" -> "total revenue by region".
    if new_dimension:
        by_clause = re.compile(r"(\bby\s+)([\w\- ]+?)(\s*\?*\s*$)", re.IGNORECASE)
        if by_clause.search(rewritten):
            rewritten = by_clause.sub(
                lambda m: f"{m.group(1)}{new_dimension}{m.group(3)}", rewritten
            )
        else:
            rewritten = re.sub(r"\s*\?+\s*$", "", rewritten).rstrip()
            rewritten = f"{rewritten} by {new_dimension}"

    rewritten = re.sub(r"\s+", " ", rewritten).strip()
    if rewritten.lower() == previous_question.lower():
        # Nothing actually changed; let the caller fall back to the raw question.
        return None
    return rewritten


def resolve(question: str, previous_question: str | None) -> str:
    """High-level helper: return a standalone question to run against the DB.

    * No previous turn, or not a follow-up -> the original question, untouched.
    * A genuine follow-up -> the rewritten standalone question, or the original
      question when it cannot be rewritten. Either way the result is a real
      question that gets generated and executed against the database fresh.
    """
    original = (question or "").strip()
    if not previous_question or not looks_like_follow_up(original):
        return original
    return rewrite_follow_up(original, previous_question) or original
