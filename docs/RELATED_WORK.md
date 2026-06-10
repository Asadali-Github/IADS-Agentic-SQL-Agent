# Related work

Owner: Asad. Where this project sits relative to the text-to-SQL literature, and
what we borrow from each. Citations are to the canonical papers; confirm exact
arXiv IDs before quoting them verbatim on a slide.

## Benchmarks

**Spider** (Yu et al., EMNLP 2018). The standard large-scale, cross-domain
text-to-SQL benchmark: ~200 databases over 138 domains, with a train/dev split
across *unseen* schemas, so it measures generalisation rather than memorisation.
It popularised **execution accuracy** and **exact-set / component match** as the
evaluation metrics — the same family we implement in `metrics.py`.

**BIRD** (Li et al., NeurIPS 2023). "BIg Bench for laRge-scale Database grounded
text-to-SQL." Moves closer to real industry data: large, messy databases,
external-knowledge evidence, and an emphasis on **execution correctness and
efficiency**. Its headline finding — that there is a wide gap between LLMs and
human performance on dirty real-world schemas — is exactly why our slice invests
so heavily in schema descriptions and a business glossary.

**WikiSQL** (Zhong et al., 2017). The earlier, simpler single-table benchmark
(one table, no joins). Useful historical baseline; too easy to be our target, but
it motivates the "easy" tier of our golden set.

## Methods

**DAIL-SQL** (Gao et al., 2023). Systematically studies prompt engineering for
text-to-SQL: question representation, **example selection**, and example
organisation for the few-shot bank, plus self-consistency. Directly informs how
we build `example_queries.jsonl` (skill-spanning, disjoint from the golden set)
and how the retriever should pick shots.

**DIN-SQL** (Pourreza & Rafiei, NeurIPS 2023). **Decomposed** in-context
learning: schema linking → classification → generation → self-correction. The
self-correction step is the ancestor of our critic/retry loop and the
`retry_rate` metric.

**C3** (Dong et al., 2023). "Clear prompting" with calibration on ChatGPT — a
strong zero-shot recipe emphasising clear schema presentation and output
calibration; supports our bet that better column descriptions raise accuracy.

**MAC-SQL** (Wang et al., 2023). **Multi-agent** text-to-SQL with a selector,
decomposer and refiner — architecturally the closest to ours (planner →
generator → validator → critic → summariser). We follow the multi-agent
decomposition but add a retrieval layer over embedded schema descriptions and an
explicit summariser/explanation stage for non-technical users.

## How our system relates

We adopt Spider/BIRD-style **execution accuracy** as our headline metric and add
partial-match and per-tier breakdowns for finer signal. Architecturally we sit
closest to MAC-SQL's multi-agent decomposition, extended with a RAG layer that
embeds the business-language schema descriptions and glossary this slice owns —
the bet (echoing BIRD and C3) that careful data-modelling of the schema, not just
prompt tricks, is where the accuracy comes from. Our distinctive additions are
the summariser stage (rows → plain-English answer + explanation) and a PII filter
on all user-facing and logged output.
