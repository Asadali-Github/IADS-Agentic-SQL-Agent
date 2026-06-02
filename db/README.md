# Database

Everything related to **defining**, **populating**, and **describing** the
database the agent queries against. Code that *reads* the schema at runtime
lives in `src/sql_agent/database/` — this directory is where the schema is
*designed*.

## Layout

```
db/
├── ddl/                      Schema definition (CREATE TABLE, indexes, views)
│   └── 01_create_tables.sql
├── migrations/               Versioned schema changes after the initial DDL
├── seed/                     Demo data (CSVs or INSERT scripts) loaded by scripts/seed_database.py
├── schema_descriptions.yaml  Business descriptions per table + column (the "features" for RAG)
└── glossary.yaml             Business term synonyms (e.g. "revenue" = "sales" = "turnover")
```

## Owner

Abdul Qayyum (DDL, migrations, seed loading) + Asad (schema descriptions, glossary — the data-modelling and feature-engineering side).

## Workflow

1. **Design** — write or update `ddl/*.sql` and document the ER diagram in [`../docs/diagrams/er_diagram.md`](../docs/diagrams/er_diagram.md).
2. **Describe** — for every table and column added, write a business
   description in `schema_descriptions.yaml`. This is what the RAG layer
   embeds; without good descriptions the agent picks the wrong tables.
3. **Glossary** — capture synonyms in `glossary.yaml` so the agent maps
   "turnover" to the `revenue` column.
4. **Seed** — drop a CSV in `seed/` and update `scripts/seed_database.py`.
5. **Embed** — run `make embed-schema` so the retriever has the new descriptions.

## Why descriptions matter (the "feature engineering" of text-to-SQL)

Traditional ML feature engineering shapes raw numbers into model inputs.
For text-to-SQL, the equivalent is shaping raw schema metadata into
*LLM-friendly descriptions*. A column called `cust_amt_gbp_net` means
nothing to an LLM. A description that says "Net customer transaction
amount in pounds sterling, excluding VAT and shipping" is searchable,
embeddable, and matches user phrasing.

This is where the project earns its data-science credibility.
