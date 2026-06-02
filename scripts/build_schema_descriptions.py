"""Build / refresh db/schema_descriptions.yaml from the live DDL.

Owner: Asad
Status: scaffold — implement during the hackathon.

What it does:
  Introspects the live DB (via src/sql_agent/database/schema_introspector.py)
  and *seeds* db/schema_descriptions.yaml with every table and column found.
  Existing human-written descriptions are preserved; only new tables and
  columns are added with `description: TODO` placeholders.

Why:
  Keeps the schema descriptions and the real DDL in sync. Whenever someone
  adds a column to ddl/, running this script will surface the missing
  description as a TODO instead of silently leaving the RAG layer blind.

TODO:
- Connect to the DB
- Read existing schema_descriptions.yaml
- For each table/column in the DB:
    if missing in yaml → add with description: 'TODO'
    if present in yaml → leave untouched
- Write yaml back
- Print a summary of TODOs added

Make target:
  make refresh-schema-descriptions
"""
