"""Business-glossary resolver - maps user phrasing to schema targets.

Glossary DATA owner: Asad (db/glossary.yaml). This resolver is a thin utility
seeded for the retriever (Zayad) to consume as an extra retrieval signal: given
a user question, it surfaces the canonical business terms and their physical
table/column targets, so "what was our turnover last quarter?" pulls in
orders.total_gbp even though the column name never appears in the question.

Matching strategy (cheap -> rich):
  1. exact surface-form match            score 1.00
  2. surface form contained in phrase    score 0.92
  3. fuzzy similarity (difflib)          score = ratio
  4. semantic similarity (optional)      score = cosine, if an embedder is given

The embedder hook mirrors the PII NER hook: pass any callable
`embedder(text) -> list[float]` (e.g. the OCI embedding model Zayad already
wires up) to get true semantic matching for paraphrases the string methods miss.
With no embedder it degrades to robust lexical matching - no heavy dependency.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Callable, Optional

_DEFAULT_PATH = Path(__file__).resolve().parents[3] / "db" / "glossary.yaml"
Embedder = Callable[[str], "list[float]"]


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", (text or "").lower())).strip()


@dataclass
class GlossaryMatch:
    """One resolved term for a phrase."""

    canonical: str
    maps_to: Optional[str]
    score: float
    matched_via: str            # the surface form that matched
    method: str                 # exact | contains | fuzzy | semantic
    default_aggregation: Optional[str] = None
    type: Optional[str] = None
    parent: Optional[str] = None
    children: Optional[list] = None


class GlossaryResolver:
    """Loads glossary.yaml and resolves phrases to business terms."""

    def __init__(self, path: Path | str = _DEFAULT_PATH, embedder: Optional[Embedder] = None,
                 doc: Optional[dict] = None) -> None:
        self.embedder = embedder
        if doc is None:
            import yaml
            doc = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        self.terms: list[dict] = doc.get("terms", [])
        # surface form -> term, all normalised
        self._surface: list[tuple[str, dict]] = []
        for term in self.terms:
            forms = [term["canonical"]] + list(term.get("variations", []))
            for f in forms:
                self._surface.append((_norm(f), term))
        # Precompute embeddings of surface forms only if an embedder is supplied.
        self._embeds: Optional[list[tuple[list, dict, str]]] = None
        if self.embedder is not None:
            self._embeds = [(self.embedder(s), t, s) for s, t in self._surface]

    # -- scoring ------------------------------------------------------------
    @staticmethod
    def _cosine(a: list, b: list) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        return dot / (na * nb) if na and nb else 0.0

    def _lexical_best(self, phrase: str) -> dict[int, tuple[float, str, str]]:
        """Best lexical score per term index. Returns {term_id: (score, via, method)}."""
        best: dict[int, tuple[float, str, str]] = {}
        for surface, term in self._surface:
            if not surface:
                continue
            if surface == phrase:
                score, method = 1.0, "exact"
            elif re.search(rf"\b{re.escape(surface)}\b", phrase):
                score, method = 0.92, "contains"
            else:
                score, method = SequenceMatcher(None, surface, phrase).ratio(), "fuzzy"
            tid = id(term)
            if tid not in best or score > best[tid][0]:
                best[tid] = (score, surface, method)
        return best

    def resolve(self, phrase: str, top_k: int = 3, threshold: float = 0.6) -> list[GlossaryMatch]:
        """Return the best-matching business terms for a phrase, best first."""
        p = _norm(phrase)
        if not p:
            return []
        # term identity -> (score, via, method, term)
        scores: dict[int, tuple[float, str, str, dict]] = {}
        for surface, term in self._surface:
            tid = id(term)
            if surface == p:
                cand = (1.0, surface, "exact")
            elif surface and re.search(rf"\b{re.escape(surface)}\b", p):
                cand = (0.92, surface, "contains")
            else:
                cand = (SequenceMatcher(None, surface, p).ratio(), surface, "fuzzy")
            if tid not in scores or cand[0] > scores[tid][0]:
                scores[tid] = (*cand, term)

        # Optional semantic pass blends in (takes the max).
        if self._embeds is not None:
            qv = self.embedder(p)  # type: ignore[misc]
            for vec, term, surface in self._embeds:
                tid = id(term)
                sem = self._cosine(qv, vec)
                if tid not in scores or sem > scores[tid][0]:
                    scores[tid] = (sem, surface, "semantic", term)

        matches = [
            GlossaryMatch(
                canonical=t["canonical"], maps_to=t.get("maps_to"), score=round(s, 4),
                matched_via=via, method=method, default_aggregation=t.get("default_aggregation"),
                type=t.get("type"), parent=t.get("parent"), children=t.get("children"),
            )
            for (s, via, method, t) in scores.values() if s >= threshold
        ]
        matches.sort(key=lambda m: m.score, reverse=True)
        return matches[:top_k]

    def annotate(self, question: str, threshold: float = 0.6) -> dict:
        """Scan a whole question and return retrieval hints (terms + targets).

        This is the structure the few-shot / schema retriever can consume.
        """
        seen: dict[str, GlossaryMatch] = {}
        for token_span in _ngrams(_norm(question), max_n=4):
            for m in self.resolve(token_span, top_k=1, threshold=max(threshold, 0.85)):
                if m.canonical not in seen or m.score > seen[m.canonical].score:
                    seen[m.canonical] = m
        hits = sorted(seen.values(), key=lambda m: m.score, reverse=True)
        return {
            "terms": [m.canonical for m in hits],
            "targets": sorted({m.maps_to for m in hits if m.maps_to}),
            "matches": hits,
        }

    def expand_query_terms(
        self, user_query: str, max_per_match: int = 4, threshold: float = 0.85
    ) -> list[str]:
        """Integration hook for the retriever (Zayad).

        Returns the original query followed by business synonyms, canonical names
        and physical targets for every glossary term detected in it. Appending
        these to the text that gets embedded widens vector-search recall - a query
        for "sales" also carries "revenue" and "orders.total_gbp".

        Example:
            >>> expand_query_terms("monthly sales by region")
            ["monthly sales by region", "revenue", "turnover", ..., "orders.total_gbp"]
        """
        ann = self.annotate(user_query, threshold=threshold)
        out: list[str] = [user_query]
        seen = {user_query.lower()} | set(_norm(user_query).split())
        by_canonical = {t["canonical"]: t for t in self.terms}
        for m in ann["matches"]:
            term = by_canonical.get(m.canonical, {})
            extras = [term.get("canonical", m.canonical)]
            extras += list(term.get("variations", []))[:max_per_match]
            if m.maps_to:
                extras.append(m.maps_to)
            if term.get("parent"):
                extras.append(term["parent"])  # climb the hierarchy for recall
            for e in extras:
                if e and e.lower() not in seen:
                    seen.add(e.lower())
                    out.append(e)
        return out

    def enrich_query_terms(self, user_query: str, **kwargs) -> str:
        """Return the query as a single string with business synonyms appended.

        The string form Zayad asked for: pass the user's question through this
        before embedding so the vector for "what was our revenue?" also carries
        "sales turnover ... orders.total_gbp", lifting recall on mismatched
        corporate terminology. Returns the original query unchanged if nothing
        in the glossary matches.
        """
        terms = self.expand_query_terms(user_query, **kwargs)
        extras = terms[1:]  # terms[0] is the original query
        return user_query if not extras else f"{user_query} {' '.join(extras)}"


def _ngrams(text: str, max_n: int = 4):
    words = text.split()
    for n in range(min(max_n, len(words)), 0, -1):
        for i in range(len(words) - n + 1):
            yield " ".join(words[i:i + n])


# --- module-level convenience (default resolver, lexical only) --------------
_DEFAULT_RESOLVER: Optional[GlossaryResolver] = None


def _default() -> GlossaryResolver:
    global _DEFAULT_RESOLVER
    if _DEFAULT_RESOLVER is None:
        _DEFAULT_RESOLVER = GlossaryResolver()
    return _DEFAULT_RESOLVER


def expand_query_terms(user_query: str, **kwargs) -> list[str]:
    """Expand a query with business synonyms/targets using the default glossary."""
    return _default().expand_query_terms(user_query, **kwargs)


def enrich_query_terms(user_query: str, **kwargs) -> str:
    """Return the query enriched with business synonyms as one embeddable string."""
    return _default().enrich_query_terms(user_query, **kwargs)


def resolve(phrase: str, **kwargs) -> "list[GlossaryMatch]":
    """Resolve a phrase to business terms using the default glossary."""
    return _default().resolve(phrase, **kwargs)
