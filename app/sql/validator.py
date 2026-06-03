"""SQL validation for generated read-only queries."""

from __future__ import annotations

import re
from typing import Any

import sqlglot
from sqlglot import exp

BLOCKED_KEYWORDS = {
    "ALTER",
    "CREATE",
    "DELETE",
    "DROP",
    "GRANT",
    "INSERT",
    "MERGE",
    "REPLACE",
    "REVOKE",
    "TRUNCATE",
    "UPDATE",
}

DEFAULT_ROW_LIMIT = 100
MAX_ROW_LIMIT = 500
ORACLE_FETCH_LIMIT_PATTERN = re.compile(
    r"\bFETCH\s+(FIRST|NEXT)\s+(?P<limit>\d+)\s+ROWS?\s+ONLY\b",
    re.IGNORECASE,
)


def validate_sql(sql: str | None, max_rows: int = MAX_ROW_LIMIT) -> dict[str, Any]:
    """Validate that generated SQL is a single safe Oracle SELECT statement."""
    if not sql or not sql.strip():
        return _result(False, "No SQL was generated.")

    cleaned_sql = _strip_trailing_semicolon(sql.strip())
    if _contains_comments(cleaned_sql):
        return _result(False, "SQL comments are not allowed in generated queries.")

    blocked_terms_found = _find_blocked_keywords(cleaned_sql)
    if blocked_terms_found:
        return _result(
            False,
            f"Blocked keyword found: {', '.join(blocked_terms_found)}.",
        )

    try:
        parsed_statements = sqlglot.parse(cleaned_sql, read="oracle")
    except sqlglot.errors.ParseError as exc:
        return _result(False, f"SQL parse failed: {exc}.")

    parsed_statements = [statement for statement in parsed_statements if statement is not None]
    if len(parsed_statements) != 1:
        return _result(False, "Exactly one SQL statement is allowed.")

    statement = parsed_statements[0]
    if not isinstance(statement, exp.Select):
        return _result(False, "Only SELECT statements are allowed.")

    if _has_disallowed_expressions(statement):
        return _result(False, "Only read-only SELECT queries are allowed.")

    enforced_limit = min(max_rows, MAX_ROW_LIMIT)
    limited_sql = _ensure_row_limit(cleaned_sql, statement, enforced_limit)

    return _result(
        True,
        "SQL validation passed.",
        sql=cleaned_sql,
        safe_sql=limited_sql,
        tables=sorted(table.name for table in statement.find_all(exp.Table)),
        max_rows=enforced_limit,
    )


def _strip_trailing_semicolon(sql: str) -> str:
    return sql[:-1].strip() if sql.endswith(";") else sql


def _contains_comments(sql: str) -> bool:
    return "--" in sql or "/*" in sql or "*/" in sql


def _find_blocked_keywords(sql: str) -> list[str]:
    tokens = set(re.findall(r"\b[A-Z_]+\b", sql.upper()))
    return sorted(BLOCKED_KEYWORDS.intersection(tokens))


def _has_disallowed_expressions(statement: exp.Expression) -> bool:
    disallowed_expression_types = (
        exp.Alter,
        exp.Command,
        exp.Create,
        exp.Delete,
        exp.Drop,
        exp.Insert,
        exp.Merge,
        exp.Update,
    )
    return any(statement.find(disallowed_type) for disallowed_type in disallowed_expression_types)


def _ensure_row_limit(sql: str, statement: exp.Select, max_rows: int) -> str:
    oracle_fetch_limit = _extract_oracle_fetch_limit(sql)
    if oracle_fetch_limit is not None:
        if oracle_fetch_limit <= max_rows:
            return sql
        return ORACLE_FETCH_LIMIT_PATTERN.sub(
            f"FETCH FIRST {max_rows} ROWS ONLY",
            sql,
            count=1,
        )

    existing_limit = statement.args.get("limit")
    if existing_limit is not None:
        existing_limit_value = _extract_limit_value(existing_limit)
        if existing_limit_value is not None and existing_limit_value <= max_rows:
            return sql

    return f"{sql} FETCH FIRST {min(DEFAULT_ROW_LIMIT, max_rows)} ROWS ONLY"


def _extract_oracle_fetch_limit(sql: str) -> int | None:
    match = ORACLE_FETCH_LIMIT_PATTERN.search(sql)
    if not match:
        return None
    return int(match.group("limit"))


def _extract_limit_value(limit_expression: exp.Expression) -> int | None:
    expression = limit_expression.expression
    if isinstance(expression, exp.Literal) and expression.is_int:
        return int(expression.this)
    return None


def _result(
    is_valid: bool,
    reason: str,
    sql: str | None = None,
    safe_sql: str | None = None,
    tables: list[str] | None = None,
    max_rows: int = MAX_ROW_LIMIT,
) -> dict[str, Any]:
    return {
        "is_valid": is_valid,
        "reason": reason,
        "sql": sql,
        "safe_sql": safe_sql,
        "tables": tables or [],
        "max_rows": max_rows,
    }
