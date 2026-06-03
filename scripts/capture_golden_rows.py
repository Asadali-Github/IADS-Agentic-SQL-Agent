#!/usr/bin/env python3
"""Capture real expected_rows for the golden set by executing reference SQL.

Owner: Asad.   Run:  python scripts/capture_golden_rows.py

Loads the cleaned seed (db/seed/product_sales.csv) into DuckDB and runs every
golden query's Oracle reference SQL (transpiled oracle->duckdb via sqlglot) to
capture the real result set. Writes evaluation/datasets/golden_queries.jsonl with
populated `expected_rows`. Aggregates that aren't exact (AVG, margins) are wrapped
in ROUND(...,2) in the reference SQL so the rows match regardless of engine.
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import duckdb
import sqlglot

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "db" / "seed" / "product_sales.csv"
OUT = ROOT / "evaluation" / "datasets" / "golden_queries.jsonl"

T = "product_sales"

# (id, difficulty, tags, order_matters, question, oracle_sql)
GOLDEN = [
    # ---------------- EASY ----------------
    ("q001","easy",["count","single-table"],False,
     "How many orders are in the dataset?",
     f"SELECT COUNT(*) AS order_count FROM {T}"),
    ("q002","easy",["sum","aggregate"],False,
     "What is the total revenue across all orders?",
     f"SELECT SUM(revenue) AS total_revenue FROM {T}"),
    ("q003","easy",["sum","aggregate"],False,
     "What is the total profit across all orders?",
     f"SELECT SUM(profit) AS total_profit FROM {T}"),
    ("q004","easy",["sum","aggregate"],False,
     "How many units were sold in total?",
     f"SELECT SUM(quantity) AS total_units FROM {T}"),
    ("q005","easy",["filter","count"],False,
     "How many orders were placed in the West region?",
     f"SELECT COUNT(*) AS west_orders FROM {T} WHERE region = 'West'"),
    ("q006","easy",["avg","aggregate"],False,
     "What is the average order value?",
     f"SELECT ROUND(AVG(revenue), 2) AS aov FROM {T}"),
    ("q007","easy",["min-max","aggregate"],False,
     "What was the single largest order by revenue?",
     f"SELECT MAX(revenue) AS biggest_order FROM {T}"),
    # ---------------- MEDIUM ----------------
    ("q008","medium",["group-by","order-by"],True,
     "What is the total revenue by region, highest first?",
     f"SELECT region, SUM(revenue) AS revenue FROM {T} GROUP BY region ORDER BY revenue DESC"),
    ("q009","medium",["group-by","order-by"],True,
     "What is the total revenue by product category, highest first?",
     f"SELECT category, SUM(revenue) AS revenue FROM {T} GROUP BY category ORDER BY revenue DESC"),
    ("q010","medium",["group-by","top-n","order-by"],True,
     "Which 5 sub-categories generated the most revenue?",
     f"SELECT sub_category, SUM(revenue) AS revenue FROM {T} GROUP BY sub_category "
     f"ORDER BY revenue DESC FETCH FIRST 5 ROWS ONLY"),
    ("q011","medium",["group-by","count"],True,
     "How many orders are there per region?",
     f"SELECT region, COUNT(*) AS orders FROM {T} GROUP BY region ORDER BY orders DESC"),
    ("q012","medium",["filter","date"],False,
     "What was the total revenue in 2024?",
     f"SELECT SUM(revenue) AS revenue_2024 FROM {T} WHERE EXTRACT(YEAR FROM order_date) = 2024"),
    ("q013","medium",["group-by","avg"],True,
     "What is the average profit per order for each category?",
     f"SELECT category, ROUND(AVG(profit), 2) AS avg_profit FROM {T} "
     f"GROUP BY category ORDER BY avg_profit DESC"),
    ("q014","medium",["group-by","sum"],True,
     "How many units were sold in each category?",
     f"SELECT category, SUM(quantity) AS units FROM {T} GROUP BY category ORDER BY units DESC"),
    ("q015","medium",["top-n","order-by"],True,
     "What are the top 5 products by total revenue?",
     f"SELECT product_name, SUM(revenue) AS revenue FROM {T} GROUP BY product_name "
     f"ORDER BY revenue DESC FETCH FIRST 5 ROWS ONLY"),
    # ---------------- HARD ----------------
    ("q016","hard",["window","rank","ratio"],True,
     "Rank categories by revenue and show each one's share of total revenue.",
     f"SELECT category, SUM(revenue) AS revenue, "
     f"RANK() OVER (ORDER BY SUM(revenue) DESC) AS rnk, "
     f"ROUND(SUM(revenue) / SUM(SUM(revenue)) OVER () * 100, 2) AS pct_of_total "
     f"FROM {T} GROUP BY category ORDER BY revenue DESC"),
    ("q017","hard",["group-by","time-series","date"],True,
     "What was the monthly revenue in 2024?",
     f"SELECT EXTRACT(MONTH FROM order_date) AS month, SUM(revenue) AS revenue FROM {T} "
     f"WHERE EXTRACT(YEAR FROM order_date) = 2024 GROUP BY EXTRACT(MONTH FROM order_date) "
     f"ORDER BY month"),
    ("q018","hard",["ratio","group-by","conditional"],True,
     "What is the profit margin percentage by region?",
     f"SELECT region, ROUND(SUM(profit) / SUM(revenue) * 100, 2) AS margin_pct "
     f"FROM {T} GROUP BY region ORDER BY margin_pct DESC"),
    ("q019","hard",["subquery","having"],True,
     "Which categories have above-average total revenue compared to the average category?",
     f"SELECT category, SUM(revenue) AS revenue FROM {T} GROUP BY category "
     f"HAVING SUM(revenue) > (SELECT AVG(cat_rev) FROM "
     f"(SELECT SUM(revenue) AS cat_rev FROM {T} GROUP BY category)) ORDER BY revenue DESC"),
    ("q020","hard",["window","ntile"],True,
     "Split sub-categories into revenue quartiles and count how many fall in each.",
     f"SELECT quartile, COUNT(*) AS sub_categories FROM "
     f"(SELECT sub_category, NTILE(4) OVER (ORDER BY SUM(revenue)) AS quartile "
     f"FROM {T} GROUP BY sub_category) GROUP BY quartile ORDER BY quartile"),
    ("q021","hard",["window","row-number","partition"],True,
     "What is the top-selling sub-category by revenue within each region?",
     f"SELECT region, sub_category, revenue FROM "
     f"(SELECT region, sub_category, SUM(revenue) AS revenue, "
     f"ROW_NUMBER() OVER (PARTITION BY region ORDER BY SUM(revenue) DESC) AS rn "
     f"FROM {T} GROUP BY region, sub_category) WHERE rn = 1 ORDER BY region"),
    ("q022","hard",["window","lag","time-series"],True,
     "What was the month-over-month revenue growth in 2024?",
     f"SELECT month, revenue, "
     f"ROUND((revenue - LAG(revenue) OVER (ORDER BY month)) / LAG(revenue) OVER (ORDER BY month) * 100, 2) AS mom_growth_pct "
     f"FROM (SELECT EXTRACT(MONTH FROM order_date) AS month, SUM(revenue) AS revenue FROM {T} "
     f"WHERE EXTRACT(YEAR FROM order_date) = 2024 GROUP BY EXTRACT(MONTH FROM order_date)) ORDER BY month"),
]


def jsonable(v):
    if isinstance(v, Decimal):
        return round(float(v), 2)
    if isinstance(v, float):
        return round(v, 2)
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return v


def tables_of(sql: str) -> list[str]:
    import sqlglot.expressions as exp
    return sorted({t.name.lower() for t in sqlglot.parse_one(sql, read="oracle").find_all(exp.Table)})


def main() -> int:
    con = duckdb.connect()
    con.execute(f"CREATE TABLE {T} AS SELECT * FROM read_csv_auto('{SEED}', header=true)")
    rows_written = 0
    with OUT.open("w", encoding="utf-8") as fh:
        for qid, diff, tags, order_matters, question, oracle_sql in GOLDEN:
            duck_sql = sqlglot.transpile(oracle_sql, read="oracle", write="duckdb")[0]
            result = con.execute(duck_sql).fetchall()
            expected = [[jsonable(c) for c in row] for row in result]
            rec = {
                "id": qid, "question": question, "expected_sql": oracle_sql,
                "expected_rows": expected, "expected_tables": tables_of(oracle_sql),
                "order_matters": order_matters, "difficulty": diff, "tags": tags,
                "source": "curated", "captured_from": "db/seed/product_sales.csv",
            }
            fh.write(json.dumps(rec) + "\n")
            rows_written += 1
    print(f"[capture] wrote {rows_written} golden queries with REAL expected_rows -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
