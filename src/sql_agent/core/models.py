"""Pydantic models - typed contracts between agent stages.

Owner of the file: Omar (core contracts).
Seeded by: Asad - the cross-stage models my slice *produces* and *consumes*
must exist before metrics/benchmark/summariser can run. These are deliberately
minimal and additive; Omar can extend them without breaking callers.

Contract summary (per the project briefing):
    Asad produces : AnswerSummary, BenchmarkResult, Metric
    Asad consumes : Question, CandidateSQL, ExecutionResult, RetrievedSchema

Everything here is plain data - no behaviour, no I/O - so any stage can import
it without pulling in heavy dependencies.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

# A "row" is an ordered tuple of cell values. We keep it as a list (JSON-native)
# rather than a tuple so it round-trips cleanly through JSONL / JSON results.
Row = list[Any]


class Difficulty(str, Enum):
    """Benchmark tier for a golden question."""

    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


# ---------------------------------------------------------------------------
# Consumed contracts (produced upstream; my code reads them)
# ---------------------------------------------------------------------------
class Question(BaseModel):
    """A natural-language question entering the pipeline."""

    # Accept either "text" or the dataset's "question" key; ignore extra keys
    # like the datasets' "_note" documentation field.
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    id: str = Field(..., description="Stable id, e.g. 'q001'.")
    text: str = Field(
        ...,
        validation_alias=AliasChoices("text", "question"),
        description="The user's question in natural language.",
    )
    difficulty: Optional[Difficulty] = None
    tags: list[str] = Field(default_factory=list, description="SQL-pattern tags, e.g. 'join'.")


class GoldenQuery(Question):
    """A benchmark question with its ground-truth answer.

    Lives in evaluation/datasets/golden_queries.jsonl. Extends Question with the
    expected SQL and the expected result rows so the benchmark can score a run.
    """

    expected_sql: str = Field(..., description="Canonical reference SQL (Oracle dialect).")
    expected_rows: list[Row] = Field(
        default_factory=list,
        description="Expected result set as ordered rows. Empty list = not yet captured.",
    )
    expected_tables: list[str] = Field(
        default_factory=list,
        description="Tables the reference SQL touches (optional check signal).",
    )
    order_matters: bool = Field(
        False,
        description="True when the reference SQL has a meaningful ORDER BY (top-N etc).",
    )


class CandidateSQL(BaseModel):
    """A SQL statement proposed by the generator for a question."""

    sql: str
    model: Optional[str] = Field(None, description="OCI GenAI model id that produced it.")
    attempt: int = Field(1, ge=1, description="1 = first try; >1 = a retry/correction.")
    reasoning: Optional[str] = None


class ExecutionResult(BaseModel):
    """The outcome of running SQL against the database."""

    columns: list[str] = Field(default_factory=list)
    rows: list[Row] = Field(default_factory=list)
    row_count: int = 0
    success: bool = True
    error: Optional[str] = None
    latency_ms: Optional[float] = Field(None, description="DB execution latency in milliseconds.")

    @classmethod
    def failure(cls, error: str) -> "ExecutionResult":
        return cls(success=False, error=error)


class RetrievedSchema(BaseModel):
    """The schema slice the RAG layer handed to the generator for a question.

    The summariser reads `tables` to populate AnswerSummary.tables_used.
    """

    tables: list[str] = Field(default_factory=list, description="Table names in scope.")
    columns: dict[str, list[str]] = Field(
        default_factory=dict, description="Optional table -> column names map."
    )
    ddl: Optional[str] = Field(None, description="Optional raw DDL snippet shown to the model.")


# ---------------------------------------------------------------------------
# Produced contracts (my slice emits them)
# ---------------------------------------------------------------------------
class ChartSpec(BaseModel):
    """A recommended chart for a result set - the UI (Mehdi) renders it.

    The summariser decides the chart *shape* from the data; rendering is the
    frontend's job. type='none' means a plain table is best.
    """

    type: Literal["bar", "line", "pie", "scatter", "none"] = "none"
    x: Optional[str] = Field(None, description="Column for the x-axis / categories.")
    y: Optional[str] = Field(None, description="Column for the y-axis / values (the measure).")
    title: Optional[str] = None
    reason: Optional[str] = Field(None, description="Why this chart fits the data.")


class AnswerSummary(BaseModel):
    """Natural-language answer the summariser returns to the UI."""

    answer: str = Field(..., description="One-sentence direct answer to the question.")
    explanation: list[str] = Field(
        default_factory=list,
        description="2-4 plain-English bullets explaining how the SQL works.",
    )
    insights: list[str] = Field(
        default_factory=list,
        description="Deterministic business insights derived from the rows (shares, trends).",
    )
    chart: Optional["ChartSpec"] = Field(None, description="Recommended chart for the result.")
    clarification: Optional[str] = Field(
        None, description="A clarifying question when the request is ambiguous (else None)."
    )
    tables_used: list[str] = Field(
        default_factory=list, description="Business-readable tables the query drew on."
    )
    sql: Optional[str] = Field(None, description="The SQL that produced the answer (for the panel).")
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)


class Metric(BaseModel):
    """A single named measurement from a benchmark run."""

    name: str
    value: float
    unit: Optional[str] = Field(None, description="e.g. 'ratio', 'ms', 'usd', 'count'.")
    detail: Optional[str] = None


class CaseResult(BaseModel):
    """Per-question outcome inside a benchmark run."""

    question_id: str
    difficulty: Optional[Difficulty] = None
    generated_sql: Optional[str] = None
    execution_match: bool = False
    exact_set_match: bool = False
    ast_match: bool = False  # logic-level SQL equivalence (alias/format/dialect-insensitive)
    partial_match: float = Field(0.0, ge=0.0, le=1.0)
    retries: int = 0
    latency_ms: Optional[float] = None
    token_cost_usd: Optional[float] = None
    error: Optional[str] = None
    passed: bool = False


class BenchmarkResult(BaseModel):
    """The full result of one benchmark run - what we write to results/runs/."""

    run_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    git_sha: Optional[str] = None
    mode: str = Field("unknown", description="How the agent ran: live_oci | offline_cache | stub | mock.")
    n_questions: int = 0
    n_passed: int = 0
    n_failed: int = 0
    metrics: list[Metric] = Field(default_factory=list)
    cases: list[CaseResult] = Field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        return self.n_passed / self.n_questions if self.n_questions else 0.0

    def metric(self, name: str) -> Optional[Metric]:
        """Convenience lookup by metric name."""
        return next((m for m in self.metrics if m.name == name), None)
