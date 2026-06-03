"""Tests for src/sql_agent/retrieval/glossary.py (glossary resolver)."""

from __future__ import annotations

from sql_agent.retrieval.glossary import GlossaryResolver


def test_exact_synonym_maps_to_revenue():
    r = GlossaryResolver()
    m = r.resolve("turnover", top_k=1)[0]
    assert m.canonical == "revenue"
    assert m.maps_to == "orders.total_gbp"
    assert m.default_aggregation == "SUM"


def test_arr_hierarchy_and_variations():
    r = GlossaryResolver()
    for phrase in ("ARR", "annual recurring revenue", "subscription sales"):
        m = r.resolve(phrase, top_k=1)[0]
        assert m.canonical == "arr"
        assert m.parent == "revenue"          # hierarchy preserved
        assert m.maps_to == "orders.total_gbp"


def test_fuzzy_match_handles_singular_plural():
    r = GlossaryResolver()
    m = r.resolve("client", top_k=1)[0]
    assert m.canonical == "customer"
    assert m.method in ("fuzzy", "contains", "exact")


def test_annotate_extracts_terms_and_targets():
    r = GlossaryResolver()
    ann = r.annotate("What was our total turnover and number of orders last quarter?")
    assert "revenue" in ann["terms"]
    assert "order_count" in ann["terms"]
    assert "orders.total_gbp" in ann["targets"]


def test_no_match_below_threshold():
    r = GlossaryResolver()
    assert r.resolve("xyzzy unrelated gibberish", threshold=0.7) == []


def test_embedder_hook_enables_semantic_match():
    # A paraphrase with no shared surface form should miss lexically but hit
    # via the embedder. Toy embedder: [money, people, order] keyword counts.
    money = {"revenue", "sales", "turnover", "income", "takings", "gross", "spend",
             "money", "earned", "pulled", "made"}
    people = {"customer", "client", "buyer", "account", "shopper"}
    orders = {"order", "orders", "basket"}

    def embed(text: str):
        toks = text.lower().split()
        return [sum(t in money for t in toks),
                sum(t in people for t in toks),
                sum(t in orders for t in toks)]

    phrase = "money the business pulled in"
    lexical_only = GlossaryResolver().resolve(phrase, threshold=0.6)
    assert lexical_only == []  # nothing matches lexically

    semantic = GlossaryResolver(embedder=embed).resolve(phrase, top_k=1, threshold=0.6)
    assert semantic, "embedder should enable a semantic match"
    assert semantic[0].method == "semantic"
    assert semantic[0].maps_to == "orders.total_gbp"  # a money-family term


# --- query expansion hook for the retriever ---------------------------------
def test_expand_query_terms_appends_synonyms_and_target():
    from sql_agent.retrieval.glossary import expand_query_terms
    out = expand_query_terms("monthly sales by region")
    assert out[0] == "monthly sales by region"          # original first
    assert "revenue" in out                              # canonical appended
    assert "orders.total_gbp" in out                    # physical target appended
    assert len(out) == len(set(out))                    # deduped


def test_expand_query_terms_climbs_hierarchy_for_arr():
    from sql_agent.retrieval.glossary import expand_query_terms
    out = expand_query_terms("show me ARR trends")
    assert "revenue" in out          # ARR's parent term added for recall
    assert "orders.total_gbp" in out


def test_expand_query_terms_no_match_returns_query_only():
    from sql_agent.retrieval.glossary import expand_query_terms
    out = expand_query_terms("zzz nonsense qqq")
    assert out == ["zzz nonsense qqq"]
