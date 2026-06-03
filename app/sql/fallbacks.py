"""Deterministic fallbacks for demo-safe questions when live ADB is unavailable."""

from __future__ import annotations

CATEGORY_SALES_SQL = """SELECT "CATEGORY" AS product_category, SUM("REVENUE") AS total_sales
FROM "ADMIN"."PRODUCT_SALES_DATASET_FINAL"
GROUP BY "CATEGORY"
ORDER BY total_sales DESC
FETCH FIRST 100 ROWS ONLY"""

CATEGORY_SALES_ROWS = [
    {"PRODUCT_CATEGORY": "Electronics", "TOTAL_SALES": 57485698.06},
    {"PRODUCT_CATEGORY": "Home & Furniture", "TOTAL_SALES": 47674426.96},
    {"PRODUCT_CATEGORY": "Clothing & Apparel", "TOTAL_SALES": 27134365.3},
    {"PRODUCT_CATEGORY": "Accessories", "TOTAL_SALES": 10113254.61},
]


def fallback_sql_for_prompt(prompt: str) -> str | None:
    """Return deterministic SQL for narrow, already-rehearsed demo prompts."""
    normalized_prompt = prompt.lower()
    if (
        "what were total sales by product category" in normalized_prompt
        or "revenue by category" in normalized_prompt
    ):
        return CATEGORY_SALES_SQL

    return None


def fallback_results_for_sql(sql: str | None) -> dict[str, object] | None:
    """Return cached results for a known safe SQL pattern."""
    if not sql:
        return None

    normalized_sql = " ".join(sql.lower().split())
    if "sum(\"revenue\")" not in normalized_sql:
        return None
    if '"category"' not in normalized_sql:
        return None
    if '"admin"."product_sales_dataset_final"' not in normalized_sql:
        return None

    return {
        "columns": ["PRODUCT_CATEGORY", "TOTAL_SALES"],
        "rows": CATEGORY_SALES_ROWS,
    }
