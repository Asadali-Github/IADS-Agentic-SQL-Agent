#!/usr/bin/env python3
"""Summariser: turn result rows into a plain-English answer (no DB/LLM needed).

    python examples/summariser_example.py
"""
import _path  # noqa: F401  (sets up imports)

from sql_agent.agents.summariser import Summariser
from sql_agent.core.models import ExecutionResult, RetrievedSchema

summariser = Summariser(max_preview_rows=10)  # deterministic fallback mode

# A normal multi-row result.
ex = ExecutionResult(
    columns=["country_code", "revenue"],
    rows=[["GB", 1182004.20], ["US", 640221.75], ["FR", 415992.00]],
    row_count=3, success=True,
)
schema = RetrievedSchema(tables=["orders", "customers"])
out = summariser.summarise(
    "Which countries generated the most revenue?",
    "SELECT c.country_code, SUM(o.total_gbp) AS revenue FROM orders o "
    "JOIN customers c ON c.customer_id=o.customer_id GROUP BY c.country_code "
    "ORDER BY revenue DESC FETCH FIRST 3 ROWS ONLY",
    ex, schema,
)
print("ANSWER:     ", out.answer)
print("EXPLANATION:")
for bullet in out.explanation:
    print("  -", bullet)
print("TABLES USED:", out.tables_used)

# A large result: only a sample reaches the model; aggregates are computed in code.
big = ExecutionResult(columns=["cat", "amount"],
                      rows=[[f"C{i%6}", float(i)] for i in range(500)], row_count=500)
print("\n500-row result -> rows sent to model:", summariser.rows_sent_to_model(500))
print("ANSWER:     ", summariser.summarise("Break down by category", "SELECT cat, amount FROM orders", big).answer)
