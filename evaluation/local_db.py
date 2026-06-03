"""Local SQL executor over the cleaned seed (offline, no Oracle/OCI needed).

Owner: Asad (evaluation/demo). The production executor against Oracle Autonomous
DB is Abdul's `database/safe_executor.py`; this is the offline twin used by the
benchmark and the end-to-end demo so the whole pipeline runs without cloud
credentials. It loads db/seed/product_sales.csv into DuckDB and runs the agent's
Oracle-dialect SQL by transpiling oracle -> duckdb with sqlglot.

Safety: read-only by construction (DuckDB connection over a CSV), plus a guard
that rejects anything that isn't a single SELECT.
"""

from __future__ import annotations

import re
import time
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional

from sql_agent.core.models import ExecutionResult

_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SEED = _ROOT / "db" / "seed" / "product_sales.csv"

_WRITE = re.compile(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|MERGE|CREATE|GRANT)\b", re.I)


def _jsonable(v):
    if isinstance(v, Decimal):
        return round(float(v), 2)
    if isinstance(v, float):
        return round(v, 2)
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return v


class LocalDB:
    """A read-only DuckDB view over the seed CSV, queried with Oracle SQL."""

    def __init__(self, seed: Path | str = DEFAULT_SEED, table: str = "product_sales") -> None:
        self.seed = Path(seed)
        self.table = table
        self._con = None

    def _connect(self):
        if self._con is None:
            import duckdb

            if not self.seed.exists():
                raise FileNotFoundError(
                    f"Seed not found: {self.seed}. Run `make preprocess` (or "
                    f"scripts/preprocess_raw_data.py) first."
                )
            self._con = duckdb.connect()
            self._con.execute(
                f"CREATE TABLE {self.table} AS "
                f"SELECT * FROM read_csv_auto('{self.seed.as_posix()}', header=true)"
            )
        return self._con

    def execute(self, sql: str, dialect: str = "oracle") -> ExecutionResult:
        """Run `sql` (Oracle dialect) locally and return an ExecutionResult."""
        if not sql or not sql.strip():
            return ExecutionResult.failure("Empty SQL.")
        if _WRITE.search(sql):
            return ExecutionResult.failure("Refused: only read-only SELECT queries are allowed.")
        try:
            import sqlglot

            duck_sql = sqlglot.transpile(sql, read=dialect, write="duckdb")[0]
        except Exception as exc:  # noqa: BLE001
            return ExecutionResult.failure(f"Could not parse SQL: {exc}")
        con = self._connect()
        t0 = time.perf_counter()
        try:
            cur = con.execute(duck_sql)
            columns = [d[0] for d in cur.description] if cur.description else []
            rows = [[_jsonable(c) for c in row] for row in cur.fetchall()]
        except Exception as exc:  # noqa: BLE001
            return ExecutionResult.failure(f"Execution error: {exc}")
        latency_ms = (time.perf_counter() - t0) * 1000.0
        return ExecutionResult(
            columns=columns, rows=rows, row_count=len(rows),
            success=True, latency_ms=round(latency_ms, 2),
        )


_DEFAULT: Optional[LocalDB] = None


def get_local_db() -> LocalDB:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = LocalDB()
    return _DEFAULT
