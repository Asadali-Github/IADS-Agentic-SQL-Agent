# ADR-002: Schema-aware retrieval as the RAG layer

**Status:** Accepted
**Date:** 2026-06-02
**Deciders:** Team 4

## Context

The hackathon brief requires Retrieval-Augmented Generation (RAG) and a vector database. The intuitive RAG application — retrieving documents to answer questions — does not naturally fit a text-to-SQL system.

But there is a real retrieval problem: **wide schemas don't fit in a prompt**. A schema with 200 tables and 3,000 columns is too long to include in every LLM call, and stuffing irrelevant tables hurts SQL quality.

## Decision

Use RAG to retrieve **relevant schema** rather than relevant documents.

Implementation:
1. For each table, write a natural-language description (one paragraph per table, plus a sentence per column).
2. Embed each description using `cohere.embed-english-v3.0`.
3. Store embeddings in Oracle Database 23ai's native vector store.
4. At query time, embed the user's question and retrieve the top-k most relevant tables.
5. Pass only those tables' schemas into the SQL generation prompt.

## Consequences

**Positive:**
- Genuinely satisfies the RAG requirement of the brief
- Scales to large schemas — token cost stays constant as schema grows
- Better SQL: fewer hallucinated columns because the LLM sees only relevant context
- Reusable pattern: same approach works for any database

**Negative:**
- Requires writing schema descriptions (one-time setup cost)
- Retrieval quality depends on description quality
- A poorly-described table won't be retrieved even when relevant

**Mitigations:**
- Auto-generate first-draft descriptions from column names and sample rows, then refine
- Include synonyms and common business terms in descriptions ("customer" → also matches "client", "account")
- Fall back to including all tables if retrieval confidence is low

## Alternatives considered

- **Pass full schema every time.** Rejected: doesn't scale beyond ~30 tables, wastes tokens.
- **Heuristic keyword matching (BM25) instead of embeddings.** Rejected: misses semantic matches (e.g. "revenue" vs "earnings").
- **Fine-tune the LLM on the schema.** Rejected: out of scope for 48 hours, requires labelled data we don't have.
