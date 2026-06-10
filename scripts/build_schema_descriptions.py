#!/usr/bin/env python3
"""Build / refresh db/schema_descriptions.yaml from the DDL.

Owner: Asad.   Make target:  make refresh-schema-descriptions

Keeps the human-written schema descriptions in sync with the real schema. It
reads every CREATE TABLE in db/ddl/*.sql (Oracle dialect, via sqlglot), and for
each table/column:

  * present in the YAML   -> left untouched (human text preserved)
  * missing from the YAML -> added with `description: TODO` and the detected type

So whenever Abdul adds a column to the DDL, running this surfaces the missing
description as a TODO instead of silently leaving the RAG layer blind.

Usage:
  python scripts/build_schema_descriptions.py            # merge into the YAML
  python scripts/build_schema_descriptions.py --check    # exit 1 if TODOs exist
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

DDL_DIR = _ROOT / "db" / "ddl"
YAML_PATH = _ROOT / "db" / "schema_descriptions.yaml"


def parse_ddl(ddl_dir: Path) -> dict[str, dict[str, str]]:
    """Return {table: {column: type}} for every CREATE TABLE found in *.sql."""
    import sqlglot
    from sqlglot import exp

    schema: dict[str, dict[str, str]] = {}
    for sql_file in sorted(ddl_dir.glob("*.sql")):
        text = sql_file.read_text(encoding="utf-8")
        for statement in sqlglot.parse(text, read="oracle"):
            if not isinstance(statement, exp.Create) or statement.kind != "TABLE":
                continue
            table = statement.this
            tbl_name = table.this.name.lower() if hasattr(table, "this") else table.name.lower()
            cols: dict[str, str] = {}
            for col in statement.find_all(exp.ColumnDef):
                cols[col.name.lower()] = col.args.get("kind").sql(dialect="oracle") if col.args.get("kind") else ""
            if cols:
                schema[tbl_name] = cols
    return schema


def merge(existing: dict, schema: dict[str, dict[str, str]]) -> tuple[dict, list[str]]:
    """Merge detected schema into the existing YAML dict; return (yaml, todos)."""
    existing = existing or {}
    existing.setdefault("version", 1)
    tables = existing.setdefault("tables", {})
    todos: list[str] = []

    for tbl, cols in schema.items():
        tnode = tables.setdefault(tbl, {})
        if "description" not in tnode:
            tnode["description"] = "TODO"
            todos.append(f"table {tbl}")
        col_node = tnode.setdefault("columns", {})
        for col, ctype in cols.items():
            if col not in col_node:
                col_node[col] = {"description": "TODO", "type": ctype}
                todos.append(f"{tbl}.{col}")
            elif not col_node[col].get("type") and ctype:
                col_node[col]["type"] = ctype
    return existing, todos


def fetch_db_comments(connection) -> tuple[dict[str, str], dict[tuple[str, str], str]]:
    """Pull table + column comments from the Oracle data dictionary.

    Reads ALL_TAB_COMMENTS / ALL_COL_COMMENTS (scoped to the current schema) so
    that comments maintained by the DBAs / migrations become the source of truth
    for descriptions - no human re-typing into YAML after every migration.

    `connection` is any DB-API connection (e.g. oracledb.connect(...)). Returns
    ({table: comment}, {(table, column): comment}), lower-cased keys.
    """
    cur = connection.cursor()
    cur.execute(
        "SELECT table_name, comments FROM all_tab_comments "
        "WHERE owner = SYS_CONTEXT('USERENV','CURRENT_SCHEMA') AND comments IS NOT NULL"
    )
    tab_comments = {row[0].lower(): row[1] for row in cur.fetchall()}
    cur.execute(
        "SELECT table_name, column_name, comments FROM all_col_comments "
        "WHERE owner = SYS_CONTEXT('USERENV','CURRENT_SCHEMA') AND comments IS NOT NULL"
    )
    col_comments = {(row[0].lower(), row[1].lower()): row[2] for row in cur.fetchall()}
    return tab_comments, col_comments


def apply_db_comments(doc: dict, tab_comments: dict, col_comments: dict, force: bool = False) -> int:
    """Fill descriptions from DB comments. Returns the count filled/updated.

    A DB comment is written when the current description is missing or 'TODO'.
    Existing human-written descriptions are preserved unless force=True (DB wins).
    """
    filled = 0
    tables = doc.setdefault("tables", {})
    for tbl, node in tables.items():
        comment = tab_comments.get(tbl)
        if comment and (force or node.get("description", "TODO") in (None, "", "TODO")):
            node["description"] = comment
            filled += 1
        for col, cnode in (node.get("columns") or {}).items():
            ccomment = col_comments.get((tbl, col))
            if ccomment and (force or cnode.get("description", "TODO") in (None, "", "TODO")):
                cnode["description"] = ccomment
                filled += 1
    return filled


def _open_connection():
    """Best-effort: obtain a DB connection from the project's connection module."""
    from sql_agent.database import connection as conn_mod  # Abdul's module

    for attr in ("get_connection", "connect", "get_engine"):
        fn = getattr(conn_mod, attr, None)
        if callable(fn):
            return fn()
    raise RuntimeError("No connection factory found in sql_agent.database.connection")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="Exit 1 if any TODO descriptions exist.")
    ap.add_argument("--from-db", action="store_true",
                    help="Also pull ALL_TAB_COMMENTS / ALL_COL_COMMENTS from Oracle.")
    ap.add_argument("--force", action="store_true",
                    help="With --from-db, let DB comments overwrite human descriptions.")
    args = ap.parse_args()

    import yaml

    schema = parse_ddl(DDL_DIR)
    if not schema:
        print(f"[build_schema_descriptions] No CREATE TABLE found in {DDL_DIR} yet.")
        print("  -> The DDL is still a scaffold. Re-run once Abdul fills in 01_create_tables.sql.")
        return 0

    existing = {}
    if YAML_PATH.exists():
        existing = yaml.safe_load(YAML_PATH.read_text(encoding="utf-8")) or {}

    merged, todos = merge(existing, schema)

    if args.from_db:
        try:
            connection = _open_connection()
            tabs, cols = fetch_db_comments(connection)
            filled = apply_db_comments(merged, tabs, cols, force=args.force)
            print(f"[build_schema_descriptions] pulled {len(tabs)} table + {len(cols)} column "
                  f"comments from Oracle; filled {filled} description(s).")
        except Exception as exc:  # noqa: BLE001
            print(f"[build_schema_descriptions] --from-db skipped: {exc}")

    if args.check:
        text = yaml.safe_dump(merged, sort_keys=False)
        n = text.count("description: TODO") + text.count("description: 'TODO'")
        print(f"[build_schema_descriptions] {n} TODO descriptions outstanding.")
        return 1 if n else 0

    YAML_PATH.write_text(
        "# Auto-merged by scripts/build_schema_descriptions.py - human text preserved.\n"
        + yaml.safe_dump(merged, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    print(f"[build_schema_descriptions] {len(schema)} tables synced -> {YAML_PATH}")
    if todos:
        print(f"  Added {len(todos)} TODO(s): " + ", ".join(todos[:12]) + ("..." if len(todos) > 12 else ""))
    else:
        print("  No new tables/columns; everything already described.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
