#!/usr/bin/env python3
"""Synthetically generate benchmark queries from the schema.

Owner: Asad.   Make target:  make synth-queries

Moves us off a purely hand-written golden set toward an automated stress-test
pipeline. It reads the structured schema in db/schema_descriptions.yaml (tables,
columns, types, FKs, sample values) and emits a broad, deterministic set of
question + SQL pairs covering the patterns the generator must handle AND the
edge cases that break naive models:

  * single-table counts, sums, averages, min/max
  * group-by over low-cardinality columns (uses sample_values)
  * filters on sample values and date ranges
  * top-N ordering
  * joins inferred from `fk:` relationships
  * EDGE CASES: NULL handling, empty constraints (WHERE 1=0), extreme date ranges

Two modes:
  offline (default)  deterministic templates - runs now, no DB or LLM needed.
  --llm              ask an LLM to generate trickier paraphrases/edge cases from
                     the DDL (requires a client; offline templates are the base).

Output: evaluation/datasets/synthetic_queries.jsonl. These are a STRESS SET for
Hasan's generator - kept separate from the curated golden set. Expected rows are
not captured here (capture on the seeded DB if any are promoted to golden).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterator, Optional

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

SCHEMA_PATH = _ROOT / "db" / "schema_descriptions.yaml"
OUT_PATH = _ROOT / "evaluation" / "datasets" / "synthetic_queries.jsonl"

_NUMERIC = ("number", "numeric", "int", "float", "decimal")
_DATE = ("date", "timestamp")


def _is_type(col: dict, kinds: tuple[str, ...]) -> bool:
    t = str(col.get("type", "")).lower()
    return any(k in t for k in kinds)


def _load_schema(path: Path) -> dict[str, dict]:
    import yaml

    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return doc.get("tables", {})


def _columns(tbl: dict) -> dict[str, dict]:
    return tbl.get("columns", {}) or {}


def _find(cols: dict[str, dict], kinds: tuple[str, ...], measure: bool = False) -> Optional[str]:
    """First column of a matching type. With measure=True, skip id columns
    (primary/foreign keys) - you sum revenue, not a customer_id."""
    for name, col in cols.items():
        if measure and (col.get("pk") or col.get("fk")):
            continue
        if _is_type(col, kinds):
            return name
    return None


def _low_card(cols: dict[str, dict]) -> list[tuple[str, list]]:
    """Columns that declare sample_values (good GROUP BY / filter targets)."""
    return [(n, c["sample_values"]) for n, c in cols.items() if c.get("sample_values")]


def _fks(cols: dict[str, dict]) -> list[tuple[str, str, str]]:
    """Return [(local_col, ref_table, ref_col)] from `fk: table.col` annotations."""
    out = []
    for name, col in cols.items():
        fk = col.get("fk")
        if fk and "." in str(fk):
            rt, rc = str(fk).split(".", 1)
            out.append((name, rt, rc))
    return out


def generate(schema: dict[str, dict]) -> Iterator[dict[str, Any]]:
    """Yield synthetic query rows from the schema (deterministic templates)."""
    n = 0

    all_tables = list(schema.keys())

    def row(question: str, sql: str, tags: list[str], difficulty: str, kind: str) -> dict:
        nonlocal n
        n += 1
        # Emit the SAME schema as golden_queries.jsonl so these rows load directly
        # via evaluation.benchmark.load_golden() for harness dry-runs. expected_rows
        # stay empty until captured against the seeded DB.
        sl = sql.lower()
        tables = [t for t in all_tables if re.search(rf"\b{re.escape(t)}\b", sl)]
        order_matters = "fetch first" in sl or "top-n" in tags
        return {
            "id": f"syn{n:03d}",
            "question": question,
            "expected_sql": sql,
            "expected_rows": [],
            "expected_tables": tables,
            "order_matters": order_matters,
            "difficulty": difficulty,
            "tags": tags,
            "source": f"synthetic-{kind}",
        }

    for tname, tbl in schema.items():
        cols = _columns(tbl)
        if not cols:
            continue
        num = _find(cols, _NUMERIC, measure=True)  # a real measure, not an id
        date = _find(cols, _DATE)

        # --- counts / aggregates ---------------------------------------
        yield row(f"How many records are there in {tname}?",
                  f"SELECT COUNT(*) FROM {tname}", ["count", "single-table"], "easy", "template")
        if num:
            yield row(f"What is the total {num} across all {tname}?",
                      f"SELECT SUM({num}) FROM {tname}", ["sum", "aggregate"], "easy", "template")
            yield row(f"What is the average {num} in {tname}?",
                      f"SELECT AVG({num}) FROM {tname}", ["avg", "aggregate"], "easy", "template")
            yield row(f"What is the highest {num} in {tname}?",
                      f"SELECT MAX({num}) FROM {tname}", ["min-max"], "easy", "template")
            yield row(f"Show the 5 {tname} with the largest {num}.",
                      f"SELECT * FROM {tname} ORDER BY {num} DESC FETCH FIRST 5 ROWS ONLY",
                      ["top-n", "order-by"], "medium", "template")

        # --- group-by + filter on low-cardinality columns --------------
        for col, samples in _low_card(cols):
            yield row(f"How many {tname} are there for each {col}?",
                      f"SELECT {col}, COUNT(*) FROM {tname} GROUP BY {col} ORDER BY COUNT(*) DESC",
                      ["group-by", "order-by"], "medium", "template")
            if samples:
                val = samples[0]
                lit = f"'{val}'" if isinstance(val, str) else val
                yield row(f"How many {tname} have {col} equal to {val}?",
                          f"SELECT COUNT(*) FROM {tname} WHERE {col} = {lit}",
                          ["filter"], "easy", "template")
            if num:
                yield row(f"What is the total {num} for each {col}?",
                          f"SELECT {col}, SUM({num}) FROM {tname} GROUP BY {col} "
                          f"ORDER BY SUM({num}) DESC",
                          ["group-by", "aggregate"], "medium", "template")

        # --- date ranges + EDGE CASES ----------------------------------
        if date:
            yield row(f"How many {tname} occurred in 2026?",
                      f"SELECT COUNT(*) FROM {tname} "
                      f"WHERE {date} >= DATE '2026-01-01' AND {date} < DATE '2027-01-01'",
                      ["filter", "date"], "medium", "template")
            yield row(f"[edge] How many {tname} fall in an impossible future window?",
                      f"SELECT COUNT(*) FROM {tname} "
                      f"WHERE {date} BETWEEN DATE '2999-01-01' AND DATE '2999-12-31'",
                      ["edge-case", "date", "empty-result"], "hard", "edge")
        if num:
            yield row(f"[edge] Total {num} under an always-false constraint (should be empty/zero).",
                      f"SELECT SUM({num}) FROM {tname} WHERE 1 = 0",
                      ["edge-case", "empty-constraint"], "hard", "edge")
        # NULL handling on the first nullable-looking column
        first_col = next(iter(cols))
        yield row(f"[edge] How many {tname} have a missing {first_col}?",
                  f"SELECT COUNT(*) FROM {tname} WHERE {first_col} IS NULL",
                  ["edge-case", "null-handling"], "medium", "edge")

        # --- joins inferred from FKs -----------------------------------
        for local, rtable, rcol in _fks(cols):
            rcols = _columns(schema.get(rtable, {}))
            rlabel = _find(rcols, ("varchar", "char", "text")) or rcol
            yield row(f"Show each {tname} with its related {rtable} {rlabel}.",
                      f"SELECT a.*, b.{rlabel} FROM {tname} a "
                      f"JOIN {rtable} b ON b.{rcol} = a.{local}",
                      ["join"], "medium", "template")
            if num:
                yield row(f"What is the total {num} per {rtable} {rlabel}?",
                          f"SELECT b.{rlabel}, SUM(a.{num}) FROM {tname} a "
                          f"JOIN {rtable} b ON b.{rcol} = a.{local} "
                          f"GROUP BY b.{rlabel} ORDER BY SUM(a.{num}) DESC",
                          ["join", "group-by", "aggregate"], "hard", "template")


def llm_augment(schema: dict, client, model: Optional[str], per_table: int = 3) -> Iterator[dict]:
    """Optional: ask an LLM for trickier edge-case queries. Requires a client."""
    import json as _json
    for tname, tbl in schema.items():
        cols = ", ".join(_columns(tbl).keys())
        prompt = (
            "Generate {k} hard but valid Oracle SQL benchmark questions for table "
            "`{t}` (columns: {c}). Focus on edge cases: NULLs, empty results, "
            "extreme ranges, tie-breaking. Respond as JSON list of "
            '{{"question":..., "sql":...}}.'
        ).format(k=per_table, t=tname, c=cols)
        try:
            data = _json.loads(client.complete(prompt, model=model))
        except Exception:  # noqa: BLE001
            continue
        for i, item in enumerate(data if isinstance(data, list) else []):
            if item.get("question") and item.get("sql"):
                yield {"id": f"synllm-{tname}-{i+1}", "question": item["question"],
                       "expected_sql": item["sql"], "expected_rows": [], "expected_tables": [],
                       "order_matters": False, "tags": ["edge-case", "llm"],
                       "difficulty": "hard", "source": "synthetic-llm"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--schema", type=Path, default=SCHEMA_PATH)
    ap.add_argument("--out", type=Path, default=OUT_PATH)
    ap.add_argument("--llm", action="store_true", help="Augment with LLM-generated edge cases.")
    args = ap.parse_args()

    if not args.schema.exists():
        print(f"[synth] schema not found: {args.schema}")
        return 0
    schema = _load_schema(args.schema)
    if not schema:
        print(f"[synth] no tables in {args.schema} yet - nothing to generate.")
        return 0

    rows = list(generate(schema))
    if args.llm:
        try:
            from sql_agent.llm.client import LLMClient  # type: ignore
            rows += list(llm_augment(schema, LLMClient(), model=None))
        except Exception as exc:  # noqa: BLE001
            print(f"[synth] --llm skipped: {exc}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    tiers = {t: sum(1 for r in rows if r["difficulty"] == t) for t in ("easy", "medium", "hard")}
    print(f"[synth] wrote {len(rows)} synthetic queries -> {args.out}")
    print(f"[synth] tiers: {tiers}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
