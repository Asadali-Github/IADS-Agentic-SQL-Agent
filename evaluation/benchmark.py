"""Benchmark harness - run the agent against the golden set and score it.

Owner: Asad.

Responsibilities
  1. Load evaluation/datasets/golden_queries.jsonl into GoldenQuery objects.
  2. Run an injected `agent_fn` end-to-end over every question.
  3. Score each case with evaluation/metrics.py.
  4. Persist a timestamped BenchmarkResult JSON to evaluation/results/runs/.
  5. Print a human-readable pass/fail report (used hourly during Day 2).

The harness is decoupled from Hasan's generator: it takes any callable that
maps a GoldenQuery to an AgentRunOutput. A StubAgent is provided so the harness
is runnable (and testable) before the real pipeline is wired in.
"""

from __future__ import annotations

import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional, Protocol

from pydantic import BaseModel, Field

from evaluation.metrics import (
    compute_metrics,
    exact_set_match,
    execution_accuracy,
    partial_match,
    sql_ast_match,
)
from sql_agent.core.models import (
    BenchmarkResult,
    CaseResult,
    GoldenQuery,
    Row,
)

# Repo-relative default locations.
_REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GOLDEN_PATH = _REPO_ROOT / "evaluation" / "datasets" / "golden_queries.jsonl"
DEFAULT_RESULTS_DIR = _REPO_ROOT / "evaluation" / "results" / "runs"


class AgentRunOutput(BaseModel):
    """What the agent returns for one question - the harness scores this."""

    sql: str = ""
    columns: list[str] = Field(default_factory=list)
    rows: list[Row] = Field(default_factory=list)
    tables_used: list[str] = Field(default_factory=list)
    retries: int = 0
    latency_ms: Optional[float] = None
    token_cost_usd: Optional[float] = None
    error: Optional[str] = None


class AgentFn(Protocol):
    """Any callable mapping a question to an AgentRunOutput."""

    def __call__(self, query: GoldenQuery) -> AgentRunOutput: ...


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def load_golden(path: Path | str = DEFAULT_GOLDEN_PATH) -> list[GoldenQuery]:
    """Read a JSONL golden file into validated GoldenQuery objects.

    Blank lines and lines starting with '#' (allowed as comments) are skipped.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Golden set not found at {path}")
    out: list[GoldenQuery] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            out.append(GoldenQuery.model_validate_json(line))
        except Exception as exc:  # noqa: BLE001 - surface the bad line clearly
            raise ValueError(f"{path}:{lineno} invalid golden row: {exc}") from exc
    return out


# ---------------------------------------------------------------------------
# Scoring one case
# ---------------------------------------------------------------------------
def score_case(query: GoldenQuery, output: AgentRunOutput, latency_ms: float) -> CaseResult:
    """Compare one agent output against its golden reference."""
    ex_match = execution_accuracy(query.expected_rows, output.rows, query.order_matters)
    set_match = exact_set_match(query.expected_rows, output.rows)
    part = partial_match(query.expected_rows, output.rows)
    ast_match = bool(output.sql) and sql_ast_match(query.expected_sql, output.sql)
    return CaseResult(
        question_id=query.id,
        difficulty=query.difficulty,
        generated_sql=output.sql or None,
        execution_match=ex_match,
        exact_set_match=set_match,
        ast_match=ast_match,
        partial_match=round(part, 4),
        retries=output.retries,
        latency_ms=round(output.latency_ms if output.latency_ms is not None else latency_ms, 2),
        token_cost_usd=output.token_cost_usd,
        error=output.error,
        passed=ex_match,
    )


# ---------------------------------------------------------------------------
# Running a whole benchmark
# ---------------------------------------------------------------------------
def _git_sha() -> Optional[str]:
    try:
        return (
            subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=_REPO_ROOT,
                                    stderr=subprocess.DEVNULL)
            .decode()
            .strip()
        )
    except Exception:  # noqa: BLE001
        return None


def run_benchmark(
    agent_fn: AgentFn,
    golden: Optional[list[GoldenQuery]] = None,
    golden_path: Path | str = DEFAULT_GOLDEN_PATH,
    mode: str = "unknown",
) -> BenchmarkResult:
    """Execute the agent over the golden set and return a scored BenchmarkResult."""
    if golden is None:
        golden = load_golden(golden_path)

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    cases: list[CaseResult] = []
    for query in golden:
        t0 = time.perf_counter()
        try:
            output = agent_fn(query)
        except Exception as exc:  # noqa: BLE001 - a crashing agent is a failed case, not a crashed run
            output = AgentRunOutput(error=f"agent raised: {exc}")
        latency_ms = (time.perf_counter() - t0) * 1000.0
        cases.append(score_case(query, output, latency_ms))

    n_passed = sum(1 for c in cases if c.passed)
    return BenchmarkResult(
        run_id=run_id,
        git_sha=_git_sha(),
        mode=mode,
        n_questions=len(cases),
        n_passed=n_passed,
        n_failed=len(cases) - n_passed,
        metrics=compute_metrics(cases),
        cases=cases,
    )


# ---------------------------------------------------------------------------
# Persistence + reporting
# ---------------------------------------------------------------------------
def save_result(result: BenchmarkResult, results_dir: Path | str = DEFAULT_RESULTS_DIR) -> Path:
    """Write the result to results/runs/<run_id>.json and return the path."""
    results_dir = Path(results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    out_path = results_dir / f"{result.run_id}.json"
    out_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    return out_path


def format_report(result: BenchmarkResult) -> str:
    """Render a compact pass/fail report as a string."""
    lines: list[str] = []
    lines.append("=" * 64)
    lines.append(f"BENCHMARK RUN {result.run_id}  (git {result.git_sha or 'n/a'}, mode={result.mode})")
    lines.append("=" * 64)
    for m in result.metrics:
        val = f"{m.value:.4f}" if m.unit == "ratio" else f"{m.value:g}"
        unit = "" if m.unit in (None, "ratio") else f" {m.unit}"
        detail = f"   ({m.detail})" if m.detail else ""
        lines.append(f"  {m.name:<32} {val}{unit}{detail}")
    lines.append("-" * 64)
    lines.append(f"  {'PASS':<6}{result.n_passed:>4}    {'FAIL':<6}{result.n_failed:>4}"
                 f"    pass_rate {result.pass_rate:.1%}")
    lines.append("-" * 64)
    for c in result.cases:
        flag = "PASS" if c.passed else "FAIL"
        tier = c.difficulty.value if c.difficulty else "-"
        extra = f"  partial={c.partial_match:.2f}" if not c.passed else ""
        err = f"  ERR: {c.error}" if c.error else ""
        lines.append(f"  [{flag}] {c.question_id:<6} {tier:<6}{extra}{err}")
    if result.mode in ("offline_cache", "stub", "mock"):
        lines.append(f"  NOTE: mode='{result.mode}' validates the execution+scoring path,")
        lines.append("        NOT live generation accuracy. Run with OCI for the headline number.")
    lines.append("=" * 64)
    return "\n".join(lines)


def print_report(result: BenchmarkResult) -> None:
    print(format_report(result))


# ---------------------------------------------------------------------------
# Stub agent - lets the harness run end-to-end before Hasan's generator lands
# ---------------------------------------------------------------------------
def make_stub_agent(correct: bool = True) -> Callable[[GoldenQuery], AgentRunOutput]:
    """Return a fake agent.

    correct=True  -> echoes the golden expected rows/sql (a perfect run; used to
                     prove the harness end-to-end and as a metrics fixture).
    correct=False -> returns empty rows (a total-miss run).
    """

    def _agent(query: GoldenQuery) -> AgentRunOutput:
        if correct:
            return AgentRunOutput(
                sql=query.expected_sql,
                rows=list(query.expected_rows),
                tables_used=query.expected_tables,
                retries=0,
                token_cost_usd=0.0,
            )
        return AgentRunOutput(sql="SELECT 1 FROM dual", rows=[], retries=1)

    return _agent


def make_mock_agent(seed: int = 7, accuracy: float = 0.85) -> Callable[[GoldenQuery], AgentRunOutput]:
    """A realistic mock pipeline for finishing the eval logic before the real agent.

    Unlike the perfect stub, this returns VARIED, plausible outputs - imperfect at
    the given `accuracy`, with realistic latencies, token costs and occasional
    retries - so the full metric surface (latency p50/p95, token cost per request,
    retry_rate, partial_match) shows non-trivial numbers. Deterministic for a given
    seed. Swap this for the real orchestrator adapter when it lands.
    """
    import random as _random

    rng = _random.Random(seed)

    def _agent(query: GoldenQuery) -> AgentRunOutput:
        correct = rng.random() < accuracy
        if correct:
            rows = list(query.expected_rows)
            retries = 0 if rng.random() < 0.8 else 1
        else:
            # A near-miss: drop or perturb rows so partial_match is interesting.
            if query.expected_rows and rng.random() < 0.5:
                rows = query.expected_rows[: max(0, len(query.expected_rows) - 1)]
            else:
                rows = []
            retries = rng.choice([1, 1, 2, 3])  # wrong answers tend to retry more
        latency = max(120.0, rng.gauss(750, 220)) + (rng.random() < 0.1) * rng.uniform(400, 1200)
        cost = round(rng.uniform(0.0006, 0.0035) * (1 + 0.4 * retries), 6)
        return AgentRunOutput(
            sql=query.expected_sql,
            rows=rows,
            tables_used=query.expected_tables,
            retries=retries,
            latency_ms=round(latency, 1),
            token_cost_usd=cost,
            error=None if (correct or rows) else "no rows returned",
        )

    return _agent


class MockOrchestrator:
    """Drop-in stand-in for the real pipeline until Omar's orchestrator lands.

    Mirrors the interface the real orchestrator is expected to expose - a
    ``run(query) -> AgentRunOutput`` method - and is also directly usable as an
    AgentFn (it is callable). Going live is a one-line swap:

        # now:
        orchestrator = MockOrchestrator()
        # later:
        from sql_agent.agents.orchestrator import Orchestrator as orchestrator_cls
        orchestrator = orchestrator_cls(...)

        run_benchmark(orchestrator, golden=golden)   # unchanged either way
    """

    def __init__(self, seed: int = 7, accuracy: float = 0.85) -> None:
        self._agent = make_mock_agent(seed=seed, accuracy=accuracy)

    def run(self, query: GoldenQuery) -> AgentRunOutput:
        return self._agent(query)

    def __call__(self, query: GoldenQuery) -> AgentRunOutput:
        return self.run(query)
