"""Simple text term helpers for Oracle-backed RAG retrieval."""

from __future__ import annotations

import re

STOP_WORDS = {
    "a",
    "an",
    "about",
    "again",
    "and",
    "are",
    "as",
    "by",
    "business",
    "context",
    "do",
    "for",
    "from",
    "how",
    "in",
    "is",
    "last",
    "of",
    "on",
    "or",
    "previous",
    "same",
    "show",
    "sql",
    "select",
    "sum",
    "the",
    "to",
    "use",
    "using",
    "what",
    "when",
    "which",
    "who",
    "with",
}

SYNONYMS = {
    "customer": ["customers"],
    "customers": ["customer"],
    "inventory": ["stock"],
    "low": ["reorder"],
    "product": ["products"],
    "products": ["product"],
    "profit": ["margin", "kpi"],
    "region": ["geography"],
    "revenue": ["sales", "kpi"],
    "sales": ["revenue", "orders", "kpi"],
    "stock": ["inventory", "quantity"],
    "total": ["sum", "revenue", "kpi"],
}


def extract_search_terms(text: str) -> list[str]:
    """Return normalized terms plus small business synonyms for retrieval."""
    terms = [_normalize_word(word) for word in re.findall(r"[a-zA-Z0-9_]+", text.lower())]
    filtered_terms = [term for term in terms if term not in STOP_WORDS and len(term) > 1]

    expanded_terms = []
    for term in filtered_terms:
        expanded_terms.append(term)
        expanded_terms.extend(SYNONYMS.get(term, []))

    return _dedupe(expanded_terms)


def build_search_text(document: dict) -> str:
    """Combine document fields into the text Oracle will score."""
    return " ".join(
        [
            document["title"],
            document["type"],
            document["content"],
        ]
    ).lower()


def _normalize_word(word: str) -> str:
    if word.endswith("s") and len(word) > 3:
        return word[:-1]
    return word


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    deduped = []
    for value in values:
        if value not in seen:
            seen.add(value)
            deduped.append(value)
    return deduped
