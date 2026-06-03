#!/usr/bin/env python3
"""Make-targeted benchmark runner.

Owner: Aneesh + Asad.

  make benchmark   ->   python scripts/run_benchmark.py

Wires the real agent pipeline into evaluation/benchmark.py, runs it over the
golden set, writes a timestamped JSON to evaluation/results/runs/, prints the
pass/fail report, and exits non-zero if the pass rate is below the threshold
(so CI / a pre-demo check can fail loudly).

Until Hasan's orchestrator is importable, pass --stub to run the harness against
a perfect stub agent (proves the plumbing, gives the slide a number to format).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make `evaluation` and `sql_agent` importable when run as a plain script.
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "src"))

from evaluation.benchmark import (  # noqa: E402
    DEFAULT_GOLDEN_PATH,
    load_golden,
    MockOrchestrator,
    make_stub_agent,
    print_report,
    run_benchmark,
    save_result,
)


def _real_agent():
    """Adapter from the end-to-end pipeline to the harness's AgentFn.

    Runs app.pipeline (RAG -> SQL -> execute -> summarise) per question and maps
    the result rows onto AgentRunOutput so the harness can score them. Works
    offline (LocalDB over the seed) and against live OCI/Oracle when configured.
    """
    from evaluation.benchmark import AgentRunOutput
    from app.pipeline import answer_question

    def _agent(query):
        r = answer_question(query.text)
        # rows come back as list[dict]; convert to ordered rows by the SQL columns.
        cols = r.get("columns") or (list(r["rows"][0].keys()) if r.get("rows") else [])
        rows = [[row.get(c) for c in cols] for row in r.get("rows", [])]
        return AgentRunOutput(
            sql=r.get("sql", ""),
            columns=cols,
            rows=rows,
            tables_used=r.get("tables_used", []),
            latency_ms=r.get("latency_ms"),
            error=r.get("error"),
        )

    return _agent


def main() -> int:
    ap = argparse.ArgumentParser(description="Run the text-to-SQL benchmark.")
    ap.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN_PATH,
                    help="Path to golden_queries.jsonl")
    ap.add_argument("--stub", action="store_true",
                    help="Use a perfect stub agent instead of the real pipeline.")
    ap.add_argument("--mock", action="store_true",
                    help="Use a realistic (imperfect) mock agent - exercises all metrics.")
    ap.add_argument("--threshold", type=float, default=0.0,
                    help="Minimum pass rate (0-1); exit non-zero if below.")
    args = ap.parse_args()

    try:
        golden = load_golden(args.golden)
    except FileNotFoundError:
        print(f"[run_benchmark] No golden set at {args.golden} yet - nothing to run.")
        return 0
    if not golden:
        print(f"[run_benchmark] Golden set {args.golden} is empty - add questions first.")
        return 0

    import os
    if args.stub:
        agent_fn, mode = make_stub_agent(correct=True), "stub"
    elif args.mock:
        agent_fn, mode = MockOrchestrator(), "mock"
    else:
        agent_fn = _real_agent()
        mode = "live_oci" if os.getenv("SELECT_AI_PROFILE") else "offline_cache"
    result = run_benchmark(agent_fn, golden=golden, mode=mode)
    out = save_result(result)
    print_report(result)
    print(f"\nSaved -> {out}")

    if result.pass_rate < args.threshold:
        print(f"FAIL: pass_rate {result.pass_rate:.1%} < threshold {args.threshold:.1%}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
