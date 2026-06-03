#!/usr/bin/env python3
"""Glossary: enrich a user query with business synonyms before embedding.

    python examples/glossary_example.py
"""
import _path  # noqa: F401

from sql_agent.retrieval.glossary import GlossaryResolver, enrich_query_terms

for q in ["what was our turnover last quarter?",
          "how many orders did we get?",
          "show me ARR by region"]:
    print(f"Q: {q}")
    print("  enriched:", enrich_query_terms(q))
    top = GlossaryResolver().resolve(q.split()[-1], top_k=1)
    print()
