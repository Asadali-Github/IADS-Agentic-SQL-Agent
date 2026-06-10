#!/usr/bin/env python3
"""Auto chart generation: turn a query result into a rendered PNG.

The summariser recommends a chart shape (ChartSpec); this example renders it with
matplotlib. Pulls real rows from the golden set (product_sales).

    python examples/chart_example.py
"""
import _path  # noqa: F401

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from sql_agent.agents.summariser import suggest_chart  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent / "charts"
OUT.mkdir(exist_ok=True)

GOLDEN = {q["id"]: q for q in
          (json.loads(l) for l in (ROOT / "evaluation/datasets/golden_queries.jsonl").open())}

# (golden id, output column names) — columns aren't stored in the rows, so name them.
JOBS = [
    ("q008", ["region", "revenue"]),       # categorical -> pie/bar
    ("q009", ["category", "revenue"]),      # categorical -> bar
    ("q017", ["month", "revenue"]),         # temporal -> line
]


def render(spec, columns, rows, path):
    xs = [str(r[0]) for r in rows]
    ys = [float(r[1]) for r in rows]
    fig, ax = plt.subplots(figsize=(7, 4))
    if spec.type == "line":
        ax.plot(xs, ys, marker="o")
    elif spec.type == "pie":
        ax.pie(ys, labels=xs, autopct="%1.0f%%")
    else:  # bar (default)
        ax.bar(xs, ys)
    if spec.type != "pie":
        ax.set_xlabel(spec.x); ax.set_ylabel(spec.y)
        plt.xticks(rotation=30, ha="right")
    ax.set_title(spec.title or "")
    plt.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


for qid, columns in JOBS:
    q = GOLDEN[qid]
    spec = suggest_chart(q["question"], columns, q["expected_rows"])
    out_path = OUT / f"{qid}_{spec.type}.png"
    render(spec, columns, q["expected_rows"], out_path)
    print(f"{qid}: {spec.type:5} -> {out_path.name}   ({spec.reason})")
