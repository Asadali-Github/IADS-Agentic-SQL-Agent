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
         "Which countries spent the most?",
         "SELECT c.country_code, SUM(o.total_gbp) AS spend FROM orders o "
         "JOIN customers c ON c.customer_id=o.customer_id GROUP BY c.country_code "
         "ORDER BY spend DESC FETCH FIRST 3 ROWS ONLY",
         ExecutionResult(columns=["country_code", "spend"],
                         rows=[["GB", 1182004.2], ["US", 640221.75], ["FR", 415992.0]],
                         row_count=3, success=True),
         RetrievedSchema(tables=["orders", "customers"])),
        ("empty result (row-fallback)",
         "How many refunded orders were there in 1990?",
         "SELECT COUNT(*) FROM orders WHERE status='refunded' AND order_date < DATE '1991-01-01'",
         ExecutionResult(columns=["n"], rows=[], row_count=0, success=True),
         RetrievedSchema(tables=["orders"])),
        ("single scalar",
         "How many customers are there?",
         "SELECT COUNT(*) FROM customers",
         ExecutionResult(columns=["n"], rows=[[1000]], row_count=1, success=True),
         RetrievedSchema(tables=["customers"])),
        ("500-row dump (context safeguard)",
         "Break down spend by category.",
         "SELECT category, amount FROM orders",
         ExecutionResult(columns=["category", "amount"], rows=big, row_count=500, success=True),
         RetrievedSchema(tables=["orders"])),
        ("PII in result (privacy gate)",
         "Who is the top customer?",
         "SELECT full_name, email, SUM(total_gbp) FROM customers GROUP BY full_name, email",
         ExecutionResult(columns=["name", "email", "spend"],
                         rows=[["Ada Lovelace", "ada@maths.org", 18420.0]],
                         row_count=1, success=True),
         RetrievedSchema(tables=["customers"])),
        ("failed execution",
         "Average basket size?",
         "SELECT AVG(total_gbp) FROM ordrs",
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
        print("EXPLANATION:")
        for b in out.explanation:
            print(f"  - {b}")
        print(f"TABLES USED: {out.tables_used}")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
