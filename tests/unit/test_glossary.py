"""Tests for src/sql_agent/retrieval/glossary.py (glossary resolver).

Targets the product_sales schema (revenue/profit/quantity in USD).
"""

from __future__ import annotations

from sql_agent.retrieval.glossary import GlossaryResolver


def test_exact_synonym_maps_to_revenue():
    r = GlossaryResolver()
    m = r.resolve("turnover", top_k=1)[0]
    assert m.canonical == "revenue"
    assert m.maps_to == "product_sales.revenue"
    assert m.default_aggregation == "SUM"


def test_profit_and_units_terms():
    r = GlossaryResolver()
    assert r.resolve("margin", top_k=1)[0].maps_to == "product_sales.profit"
    assert r.resolve("units", top_k=1)[0].maps_to == "product_sales.quantity"


def test_profit_margin_hierarchy():
    r = GlossaryResolver()
    m = r.resolve("margin percent", top_k=1)[0]
    assert m.canonical == "profit margin"
    assert m.parent == "profit"           # hierarchy preserved
    assert m.maps_to == "product_sales.profit"


def test_fuzzy_match_handles_singular_plural():
    r = GlossaryResolver()
    m = r.resolve("client", top_k=1)[0]
    assert m.canonical == "customer"
    assert m.method in ("fuzzy", "contains", "exact")


def test_annotate_extracts_terms_and_targets():
    r = GlossaryResolver()
    ann = r.annotate("What was our total turnover and number of orders by category?")
    assert "revenue" in ann["terms"]
    assert "order_count" in ann["terms"]
    assert "product_sales.revenue" in ann["targets"]


def test_no_match_below_threshold():
    r = GlossaryResolver()
    assert r.resolve("xyzzy unrelated gibberish", threshold=0.7) == []


def test_embedder_hook_enables_semantic_match():
    money = {"revenue", "sales", "turnover", "income", "takings", "gross", "spend",
             "money", "earned", "pulled", "made"}
    people = {"customer", "client", "buyer", "shopper"}
    items = {"product", "item", "unit", "units"}

    def embed(text: str):
        toks = text.lower().split()
        return [sum(t in money for t in toks),
                sum(t in people for t in toks),
                sum(t in items for t in toks)]

    phrase = "money the business pulled in"
    assert GlossaryResolver().resolve(phrase, threshold=0.6) == []  # misses lexically
    semantic = GlossaryResolver(embedder=embed).resolve(phrase, top_k=1, threshold=0.6)
    assert semantic and semantic[0].method == "semantic"
    assert semantic[0].maps_to == "product_sales.revenue"


def test_expand_query_terms_appends_synonyms_and_target():
    from sql_agent.retrieval.glossary import expand_query_terms
    out = expand_query_terms("monthly sales by region")
    assert out[0] == "monthly sales by region"
    assert "revenue" in out
    assert "product_sales.revenue" in out
    assert len(out) == len(set(out))


def test_expand_query_terms_climbs_hierarchy_for_margin():
    from sql_agent.retrieval.glossary import expand_query_terms
    # "profit" is not a literal word here, so the parent term must be appended.
    out = expand_query_terms("margin percent by region")
    assert "profit" in out                       # margin's parent term added
    assert "product_sales.profit" in out


def test_enrich_query_terms_returns_string():
    from sql_agent.retrieval.glossary import enrich_query_terms
    s = enrich_query_terms("what was our revenue?")
    assert s.startswith("what was our revenue?")
    assert "product_sales.revenue" in s
    assert enrich_query_terms("zzz nonsense qqq") == "zzz nonsense qqq"
