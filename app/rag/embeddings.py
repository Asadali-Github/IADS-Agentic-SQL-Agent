"""Embedding helpers for the LangChain RAG prototype."""

from __future__ import annotations

import math
import re
from collections import Counter

from langchain_core.embeddings import Embeddings


STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "by",
    "for",
    "from",
    "in",
    "is",
    "of",
    "on",
    "or",
    "show",
    "the",
    "to",
    "what",
    "which",
    "with",
}

SYNONYMS = {
    "sales": ["revenue"],
    "revenue": ["sales", "turnover"],
    "turnover": ["revenue", "sales"],
    "profit": ["margin", "earnings"],
    "margin": ["profit"],
    "units": ["quantity"],
    "quantity": ["units"],
    "customer": ["customers"],
    "customers": ["customer"],
    "product": ["products"],
    "products": ["product"],
    "category": ["categories"],
    "region": ["area", "zone"],
    "total": ["sum"],
}


class LocalKeywordEmbeddings(Embeddings):
    """Small local embedding model for demo RAG without an external API key.

    It uses normalized bag-of-words vectors. LangChain can use it exactly like
    a real embedding model, but later we can replace it with OCI, Cohere,
    OpenAI, or another production embedding provider.
    """

    def __init__(self, reference_texts: list[str]) -> None:
        self.vocabulary = self._build_vocabulary(reference_texts)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of document texts."""
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        """Embed one user query."""
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        terms = Counter(self._expand_terms(self._extract_terms(text)))
        vector = [float(terms.get(term, 0)) for term in self.vocabulary]
        length = math.sqrt(sum(value * value for value in vector))

        if length == 0:
            return vector

        return [value / length for value in vector]

    def _build_vocabulary(self, texts: list[str]) -> list[str]:
        vocabulary = set()
        for text in texts:
            vocabulary.update(self._expand_terms(self._extract_terms(text)))

        return sorted(vocabulary)

    def _extract_terms(self, text: str) -> list[str]:
        words = re.findall(r"[a-zA-Z0-9_]+", text.lower())
        return [
            self._normalize_word(word)
            for word in words
            if word not in STOP_WORDS and len(word) > 1
        ]

    def _expand_terms(self, terms: list[str]) -> list[str]:
        expanded_terms = list(terms)
        for term in terms:
            expanded_terms.extend(SYNONYMS.get(term, []))

        return expanded_terms

    def _normalize_word(self, word: str) -> str:
        if word.endswith("s") and len(word) > 3:
            return word[:-1]

        return word


class EmbeddingClient:
    """Placeholder for a real embedding model client."""

    def embed_text(self, text: str) -> list[float]:
        """Return an embedding vector for text in a future implementation."""
        raise NotImplementedError(
            "Production embeddings are not implemented yet. Later this can connect to "
            "Oracle AI Vector Search, Chroma, FAISS, or another vector store."
        )


class VectorStoreRetriever:
    """Placeholder for future external vector database retrieval."""

    def search(self, query: str, top_k: int = 4) -> list[dict]:
        """Search documents semantically in a future implementation."""
        raise NotImplementedError(
            "External vector search is not implemented yet. The current prototype uses "
            "LangChain's in-memory vector store."
        )
