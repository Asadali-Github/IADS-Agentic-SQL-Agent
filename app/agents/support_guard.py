"""Guardrails that stop unsupported questions before SQL generation."""

from __future__ import annotations

from app.rag.embeddings import build_search_text, extract_search_terms

MIN_MATCHED_TERMS = 1


def assess_question_support(user_question: str, retrieved_documents: list[dict]) -> dict:
    """Decide whether retrieved context is strong enough to generate SQL."""
    if not retrieved_documents:
        return _result(
            is_supported=False,
            reason="No relevant schema or business documents were retrieved.",
        )

    search_terms = extract_search_terms(user_question)
    if not search_terms:
        return _result(
            is_supported=False,
            reason="The question did not contain enough searchable business terms.",
        )

    context_terms = set()
    for document in retrieved_documents:
        context_terms.update(extract_search_terms(build_search_text(document)))

    matched_terms = sorted(set(search_terms).intersection(context_terms))
    if len(matched_terms) < MIN_MATCHED_TERMS:
        return _result(
            is_supported=False,
            reason="Retrieved documents did not match the business meaning of the question.",
            matched_terms=matched_terms,
        )

    return _result(
        is_supported=True,
        reason="Retrieved context supports SQL generation.",
        matched_terms=matched_terms,
    )


def unsupported_answer(reason: str) -> dict:
    """Return a clear no-answer payload rather than inventing SQL or numbers."""
    return {
        "answer": (
            "I do not have enough retrieved schema or business context to answer that "
            f"question safely. {reason}"
        ),
        "provider": "local_no_answer",
        "prompt_row_count": 0,
        "error": None,
    }


def _result(
    is_supported: bool,
    reason: str,
    matched_terms: list[str] | None = None,
) -> dict:
    return {
        "is_supported": is_supported,
        "reason": reason,
        "matched_terms": matched_terms or [],
    }
