#!/usr/bin/env python3
"""Preprocess raw demo data into clean seed CSVs.

Owner: Asad.   Make target:  make preprocess

Pipeline:
    data/raw/<source>.csv  ->  [clean]  ->  db/seed/<table>.csv  ->  seed_database.py

Cleaning rules are declared per target table in TABLES below, so adding a new
table is a data change, not a code change. The script is idempotent: it
truncates each output file on every run. It prints a rows-in / rows-out / dropped
report so data loss is always visible.

STATUS: scaffold with one worked example (customers, orders) against the
provisional schema. Wire up the real raw files + rules once the demo dataset is
chosen. Uses only the Python standard library (no pandas dependency).
"""

from __future__ import annotations

import csv
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = _ROOT / "data" / "raw"
SEED_DIR = _ROOT / "db" / "seed"


@dataclass
class TableSpec:
    """How to turn one raw CSV into one seed CSV."""

    source: str                                   # filename under data/raw/
    output: str                                   # filename under db/seed/
    rename: dict[str, str] = field(default_factory=dict)   # raw col -> seed col
    columns: list[str] = field(default_factory=list)       # final column order
    transforms: dict[str, Callable[[str], str]] = field(default_factory=dict)
    dedupe_on: Optional[str] = None               # column whose value must be unique
    required: list[str] = field(default_factory=list)      # drop row if any is blank


def _strip(v: str) -> str:
    return (v or "").strip()


def _to_iso_date(v: str) -> str:
    """Best-effort normalise common date formats to YYYY-MM-DD."""
    v = _strip(v)
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            from datetime import datetime
            return datetime.strptime(v, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return v


# ---- Declare the demo tables here (provisional example) --------------------
TABLES: list[TableSpec] = [
    TableSpec(
        source="customers_raw.csv",
        output="customers.csv",
        rename={"id": "customer_id", "name": "full_name", "country": "country_code"},
        columns=["customer_id", "full_name", "country_code", "created_at"],
        transforms={"country_code": lambda v: _strip(v).upper()[:2], "created_at": _to_iso_date},
        dedupe_on="customer_id",
        required=["customer_id", "full_name"],
    ),
    TableSpec(
        source="orders_raw.csv",
        output="orders.csv",
        rename={"id": "order_id", "cust_id": "customer_id", "amount": "total_gbp"},
        columns=["order_id", "customer_id", "order_date", "status", "total_gbp"],
        transforms={"order_date": _to_iso_date, "status": lambda v: _strip(v).lower(),
                    "total_gbp": lambda v: f"{float(_strip(v) or 0):.2f}"},
        dedupe_on="order_id",
        required=["order_id", "customer_id", "total_gbp"],
    ),
]


def process(spec: TableSpec) -> tuple[int, int, int]:
    """Clean one table. Returns (rows_in, rows_out, rows_dropped)."""
    src = RAW_DIR / spec.source
    if not src.exists():
        print(f"  [skip] {spec.source} not found in data/raw/")
        return (0, 0, 0)

    with src.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    seen: set[str] = set()
    out_rows: list[dict[str, str]] = []
    dropped = 0
    for raw in rows:
        rec = {spec.rename.get(k, k): _strip(v) for k, v in raw.items()}
        for col, fn in spec.transforms.items():
            if col in rec:
                try:
                    rec[col] = fn(rec[col])
                except Exception:  # noqa: BLE001 - a bad cell drops the row
                    rec[col] = ""
        if any(not rec.get(c) for c in spec.required):
            dropped += 1
            continue
        if spec.dedupe_on:
            key = rec.get(spec.dedupe_on, "")
            if key in seen:
                dropped += 1
                continue
            seen.add(key)
        out_rows.append({c: rec.get(c, "") for c in spec.columns})

    SEED_DIR.mkdir(parents=True, exist_ok=True)
    with (SEED_DIR / spec.output).open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=spec.columns)
        writer.writeheader()
        writer.writerows(out_rows)
    return (len(rows), len(out_rows), dropped)


def main() -> int:
    if not RAW_DIR.exists() or not any(RAW_DIR.glob("*.csv")):
        print(f"[preprocess] No raw CSVs in {RAW_DIR} yet - nothing to clean.")
        print("  Drop the demo source files there, then re-run `make preprocess`.")
        return 0
    print("[preprocess] raw -> seed")
    for spec in TABLES:
        rin, rout, drop = process(spec)
        if rin:
            print(f"  {spec.source:<20} -> {spec.output:<16} in={rin} out={rout} dropped={drop}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
