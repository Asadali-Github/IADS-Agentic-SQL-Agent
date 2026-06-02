"""Placeholder SQL validation module for future safety checks."""

from __future__ import annotations


BLOCKED_KEYWORDS = {
    "DELETE",
    "UPDATE",
    "DROP",
    "INSERT",
    "ALTER",
    "TRUNCATE",
    "MERGE",
}


def validate_sql(sql: str) -> dict:
    """Run minimal placeholder validation for future SQL safety work."""
    normalized_sql = sql.strip().upper()
    blocked_terms_found = [
        keyword for keyword in BLOCKED_KEYWORDS if keyword in normalized_sql.split()
    ]

    if blocked_terms_found:
        return {
            "is_valid": False,
            "reason": f"Blocked keyword found: {', '.join(blocked_terms_found)}",
        }

    if normalized_sql and not normalized_sql.startswith("SELECT"):
        return {
            "is_valid": False,
            "reason": "Future SQL execution should allow SELECT queries only.",
        }

    # Future validation should also:
    # - parse SQL with a library such as sqlglot
    # - block queries without SELECT
    # - block unknown tables
    # - block unknown columns
    # - enforce row limits
    # - reject multiple statements
    # - reject comments or syntax patterns used to bypass safety checks
    return {
        "is_valid": True,
        "reason": "Placeholder validation passed. Full validation will be added later.",
    }
