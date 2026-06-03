"""Question suggestions for the UI ('try one of these' buttons).

Owner: Asad (data). Consumed by the frontend (Mehdi).

Provides a small, dependency-light catalogue of demo-ready questions plus a
helper that, given what the user has typed so far, ranks the suggestions by
business-term overlap (via the glossary) - so a half-typed "prof..." surfaces
the profit / margin questions first.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

_CATALOGUE = (
    Path(__file__).resolve().parents[2] / "evaluation" / "datasets" / "suggested_questions.json"
)


def _load() -> list[dict]:
    try:
        data = json.loads(_CATALOGUE.read_text(encoding="utf-8"))
        return data.get("suggestions", [])
    except Exception:  # noqa: BLE001 - never break the UI over a missing file
        return []


def suggest_questions(n: int = 6, partial: Optional[str] = None) -> list[dict]:
    """Return up to `n` suggestion dicts ({label, question, tags}).

    If `partial` (what the user has typed) is given, suggestions are ranked by
    overlap between the glossary terms found in `partial` and each suggestion's
    tags, so the list adapts as the user types. With no input, returns the
    curated order.
    """
    catalogue = _load()
    if not partial or not partial.strip():
        return catalogue[:n]

    wanted: set[str] = set()
    try:
        from sql_agent.retrieval.glossary import GlossaryResolver

        ann = GlossaryResolver().annotate(partial, threshold=0.8)
        wanted = {t.lower() for t in ann["terms"]}
    except Exception:  # noqa: BLE001 - glossary optional
        wanted = set()
    words = {w.lower() for w in partial.split()}

    def score(s: dict) -> int:
        tags = {t.lower() for t in s.get("tags", [])}
        text = s.get("question", "").lower() + " " + s.get("label", "").lower()
        return len(tags & wanted) * 2 + sum(1 for w in words if len(w) > 2 and w in text)

    ranked = sorted(catalogue, key=score, reverse=True)
    ranked = [s for s in ranked if score(s) > 0] or catalogue
    return ranked[:n]
