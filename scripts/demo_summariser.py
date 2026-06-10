#!/usr/bin/env python3
"""Exercise the Summariser over mock inputs - tune prompts without a database.

Owner: Asad.   Run:  python scripts/demo_summariser.py  [--llm] [--show-prompts]

The summariser only needs Question + SQL + Rows, none of which require a live DB.
This driver feeds it a battery of mock result sets - a normal multi-row answer,
an empty result (row-fallback), a single scalar, a 500-row dump (context/token
safeguard), a PII-laden result, and a failed execution - and prints the resulting
AnswerSummary. Use it to make the answers crisp and to confirm large results never
bloat the prompt, all before the team writes a single query.

  --llm           use the real OCI GenAI client (falls back to deterministic mode
                  automatically if it can't be constructed).
  --show-prompts  print the rendered summariser/explanation prompts too.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

from sql_agent.agents.summariser import Summariser, _format_profile, profile_result  # noqa: E402
from sql_agent.core.models import ExecutionResult, RetrievedSchema  # noqa: E402


def _scenarios():
    big = [[f"Cat-{i % 6}", round(1000 - i * 1.7, 2)] for i in range(500)]
    return [
        ("normal multi-row",
         "Which regions generated the most revenue?",
         "SELECT region, SUM(revenue) AS revenue FROM product_sales "
         "GROUP BY region ORDER BY revenue DESC",
         ExecutionResult(columns=["region", "revenue"],
                         rows=[["East", 44980048.22], ["West", 36242841.73],
                               ["Centre", 36081894.34], ["South", 25102960.64]],
                         row_count=4, success=True),
         RetrievedSchema(tables=["product_sales"])),
        ("empty result (row-fallback)",
         "What is the revenue for the product 'iPhone 15'?",
         "SELECT SUM(revenue) FROM product_sales WHERE product_name = 'iPhone 15'",
         ExecutionResult(columns=["revenue"], rows=[], row_count=0, success=True),
         RetrievedSchema(tables=["product_sales"])),
        ("single scalar",
         "How many orders are in the dataset?",
         "SELECT COUNT(*) FROM product_sales",
         ExecutionResult(columns=["order_count"], rows=[[200000]], row_count=1, success=True),
         RetrievedSchema(tables=["product_sales"])),
        ("500-row dump (context safeguard)",
         "Break down revenue by sub-category.",
         "SELECT sub_category, revenue FROM product_sales",
         ExecutionResult(columns=["sub_category", "revenue"], rows=big, row_count=500, success=True),
         RetrievedSchema(tables=["product_sales"])),
        ("PII in result (privacy gate)",
         "Who is the top customer by spend?",
         "SELECT customer_name, SUM(revenue) FROM product_sales GROUP BY customer_name "
         "ORDER BY 2 DESC FETCH FIRST 1 ROWS ONLY",
         ExecutionResult(columns=["customer_name", "revenue"],
                         rows=[["Ada Lovelace (ada@example.com)", 18420.0]],
                         row_count=1, success=True),
         RetrievedSchema(tables=["product_sales"])),
        ("ambiguous term (clarification)",
         "What is the average margin by region?",
         "SELECT region, ROUND(SUM(profit)/SUM(revenue)*100, 2) AS margin FROM product_sales "
         "GROUP BY region",
         ExecutionResult(columns=["region", "margin"],
                         rows=[["South", 23.58], ["West", 22.94], ["Centre", 22.43], ["East", 20.5]],
                         row_count=4, success=True),
         RetrievedSchema(tables=["product_sales"])),
        ("failed execution",
         "Average profit?",
         "SELECT AVG(profit) FROM prodct_sales",
         ExecutionResult.failure("ORA-00942: table or view does not exist"),
         RetrievedSchema(tables=[])),
    ]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--llm", action="store_true")
    ap.add_argument("--show-prompts", action="store_true")
    args = ap.parse_args()

    llm = None
    if args.llm:
        try:
            from sql_agent.llm.client import LLMClient  # type: ignore
            llm = LLMClient()
        except Exception as exc:  # noqa: BLE001
            print(f"[demo] --llm unavailable ({exc}); using deterministic fallback.\n")

    summ = Summariser(llm=llm, max_preview_rows=10)
    for title, question, sql, ex, schema in _scenarios():
        print("=" * 72)
        print(f"SCENARIO: {title}")
        print(f"Q: {question}")
        if args.show_prompts and ex.success:
            prof = _format_profile(profile_result(ex.columns, ex.rows))
            print(f"-- profile fed to model --\n{prof}")
        sent = summ.rows_sent_to_model(len(ex.rows)) if ex.success else 0
        print(f"TOKEN-SAFETY: {len(ex.rows)} rows in result -> {sent} sent to model "
              f"(+ deterministic profile)")
        out = summ.summarise(question, sql, ex, schema)
        print(f"ANSWER:      {out.answer}")
        print(f"CONFIDENCE:  {out.confidence}")
        if out.clarification:
            print(f"CLARIFY:     {out.clarification}")
        if out.insights:
            print("INSIGHTS:")
            for i in out.insights:
                print(f"  * {i}")
        print("EXPLANATION:")
        for b in out.explanation:
            print(f"  - {b}")
        if out.chart:
            print(f"CHART:       {out.chart.type}"
                  + (f" (x={out.chart.x}, y={out.chart.y})" if out.chart.type != 'none' else ""))
        print(f"TABLES USED: {out.tables_used}")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
