"""Schema obfuscator — swaps real table/column names for generic aliases.

Owner: Asad
Status: scaffold — implement during the hackathon.

Why this exists:
  Real schemas often contain sensitive names (e.g. `employee_salaries_2026`,
  `customer_passwords`, `internal_pricing_model_v3`). Passing these raw to an
  external LLM API leaks the company's data blueprint. The obfuscator
  rewrites the schema to anonymous aliases before the LLM sees it, then maps
  the generated SQL back to real names before execution.

Flow:
                                            ┌─ obfuscate ─┐
  Real schema  ─────────────────────────────┤             │── LLM
                                            └────────────-┘
                                            ┌──── de-obfuscate ────┐
  LLM SQL (with aliases) ───────────────────┤                      │── real SQL
                                            └──────────────────────┘

Wiring:
  `schema_retriever.py` calls obfuscate() before returning the retrieved
  schema. `sql_validator.py` (or the executor) calls deobfuscate() before
  running the SQL.

TODO:
- Public interface:
    obfuscate_schema(schema: RetrievedSchema) -> tuple[ObfuscatedSchema, AliasMap]
    deobfuscate_sql(sql: str, alias_map: AliasMap) -> str
- Alias scheme:
    tables   → Table_A, Table_B, ...
    columns  → Table_A.Column_1, Table_A.Column_2, ...
  Preserve column semantics in descriptions (e.g. "Column_1 is a date").
- AliasMap is a Pydantic model in core/models.py, threaded through the pipeline.
- Toggleable via SCHEMA_OBFUSCATION_ENABLED env var.
- Write tests in tests/unit/test_schema_obfuscator.py

Threat addressed:
  See SECURITY.md → "Data exfiltration" and "Prompt injection".
"""
