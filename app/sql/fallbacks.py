"""Deterministic fallbacks for demo-safe questions when live ADB is unavailable."""

from __future__ import annotations

CATEGORY_SALES_SQL = """SELECT "CATEGORY" AS product_category, SUM("REVENUE") AS total_sales
FROM "ADMIN"."PRODUCT_SALES_DATASET_FINAL"
GROUP BY "CATEGORY"
ORDER BY total_sales DESC
FETCH FIRST 100 ROWS ONLY"""

REGION_REVENUE_SQL = """SELECT "REGION" AS region, SUM("REVENUE") AS total_revenue
FROM "ADMIN"."PRODUCT_SALES_DATASET_FINAL"
GROUP BY "REGION"
ORDER BY total_revenue DESC
FETCH FIRST 100 ROWS ONLY"""

CATEGORY_PROFIT_SQL = """SELECT "CATEGORY" AS product_category, SUM("PROFIT") AS total_profit
FROM "ADMIN"."PRODUCT_SALES_DATASET_FINAL"
GROUP BY "CATEGORY"
ORDER BY total_profit DESC
FETCH FIRST 100 ROWS ONLY"""

REGION_PROFIT_SQL = """SELECT "REGION" AS region, SUM("PROFIT") AS total_profit
FROM "ADMIN"."PRODUCT_SALES_DATASET_FINAL"
GROUP BY "REGION"
ORDER BY total_profit DESC
FETCH FIRST 100 ROWS ONLY"""

REGION_MARGIN_SQL = """SELECT
    "REGION" AS region,
    SUM("PROFIT") AS total_profit,
    SUM("REVENUE") AS total_revenue,
    ROUND(SUM("PROFIT") / NULLIF(SUM("REVENUE"), 0) * 100, 2) AS profit_margin_pct
FROM "ADMIN"."PRODUCT_SALES_DATASET_FINAL"
GROUP BY "REGION"
ORDER BY profit_margin_pct DESC
FETCH FIRST 100 ROWS ONLY"""

MONTHLY_REVENUE_2024_SQL = """SELECT
    TO_CHAR(TO_DATE("ORDER_DATE", 'MM-DD-RR'), 'YYYY-MM') AS sales_month,
    SUM("REVENUE") AS total_revenue
FROM "ADMIN"."PRODUCT_SALES_DATASET_FINAL"
WHERE TO_DATE("ORDER_DATE", 'MM-DD-RR') >= DATE '2024-01-01'
  AND TO_DATE("ORDER_DATE", 'MM-DD-RR') < DATE '2025-01-01'
GROUP BY TO_CHAR(TO_DATE("ORDER_DATE", 'MM-DD-RR'), 'YYYY-MM')
ORDER BY sales_month
FETCH FIRST 100 ROWS ONLY"""

TOP_PRODUCTS_REVENUE_SQL = """SELECT "PRODUCT_NAME" AS product_name, SUM("REVENUE") AS total_revenue
FROM "ADMIN"."PRODUCT_SALES_DATASET_FINAL"
GROUP BY "PRODUCT_NAME"
ORDER BY total_revenue DESC
FETCH FIRST 5 ROWS ONLY"""

CATEGORY_SALES_ROWS = [
    {"PRODUCT_CATEGORY": "Electronics", "TOTAL_SALES": 57485698.06},
    {"PRODUCT_CATEGORY": "Home & Furniture", "TOTAL_SALES": 47674426.96},
    {"PRODUCT_CATEGORY": "Clothing & Apparel", "TOTAL_SALES": 27134365.3},
    {"PRODUCT_CATEGORY": "Accessories", "TOTAL_SALES": 10113254.61},
]

CATEGORY_PROFIT_ROWS = [
    {"PRODUCT_CATEGORY": "Home & Furniture", "TOTAL_PROFIT": 11218596.44},
    {"PRODUCT_CATEGORY": "Clothing & Apparel", "TOTAL_PROFIT": 8826851.49},
    {"PRODUCT_CATEGORY": "Electronics", "TOTAL_PROFIT": 8065113.92},
    {"PRODUCT_CATEGORY": "Accessories", "TOTAL_PROFIT": 3438046.28},
]

REGION_REVENUE_ROWS = [
    {"REGION": "East", "TOTAL_REVENUE": 44980048.22},
    {"REGION": "West", "TOTAL_REVENUE": 36242841.73},
    {"REGION": "Centre", "TOTAL_REVENUE": 36081894.34},
    {"REGION": "South", "TOTAL_REVENUE": 25102960.64},
]

REGION_PROFIT_ROWS = [
    {"REGION": "East", "TOTAL_PROFIT": 9221327.43},
    {"REGION": "West", "TOTAL_PROFIT": 8313962.76},
    {"REGION": "Centre", "TOTAL_PROFIT": 8094863.77},
    {"REGION": "South", "TOTAL_PROFIT": 5918454.17},
]

REGION_MARGIN_ROWS = [
    {
        "REGION": "South",
        "TOTAL_PROFIT": 5918454.17,
        "TOTAL_REVENUE": 25102960.64,
        "PROFIT_MARGIN_PCT": 23.58,
    },
    {
        "REGION": "West",
        "TOTAL_PROFIT": 8313962.76,
        "TOTAL_REVENUE": 36242841.73,
        "PROFIT_MARGIN_PCT": 22.94,
    },
    {
        "REGION": "Centre",
        "TOTAL_PROFIT": 8094863.77,
        "TOTAL_REVENUE": 36081894.34,
        "PROFIT_MARGIN_PCT": 22.43,
    },
    {
        "REGION": "East",
        "TOTAL_PROFIT": 9221327.43,
        "TOTAL_REVENUE": 44980048.22,
        "PROFIT_MARGIN_PCT": 20.5,
    },
]

MONTHLY_REVENUE_2024_ROWS = [
    {"SALES_MONTH": "2024-01", "TOTAL_REVENUE": 4367352.84},
    {"SALES_MONTH": "2024-02", "TOTAL_REVENUE": 2930941.45},
    {"SALES_MONTH": "2024-03", "TOTAL_REVENUE": 4088588.81},
    {"SALES_MONTH": "2024-04", "TOTAL_REVENUE": 4263479.24},
    {"SALES_MONTH": "2024-05", "TOTAL_REVENUE": 4883303.43},
    {"SALES_MONTH": "2024-06", "TOTAL_REVENUE": 4721684.53},
    {"SALES_MONTH": "2024-07", "TOTAL_REVENUE": 4367652.54},
    {"SALES_MONTH": "2024-08", "TOTAL_REVENUE": 4429328.35},
    {"SALES_MONTH": "2024-09", "TOTAL_REVENUE": 4846454.51},
    {"SALES_MONTH": "2024-10", "TOTAL_REVENUE": 8719541.99},
    {"SALES_MONTH": "2024-11", "TOTAL_REVENUE": 13899671.91},
    {"SALES_MONTH": "2024-12", "TOTAL_REVENUE": 10134372.67},
]

TOP_PRODUCTS_REVENUE_ROWS = [
    {"PRODUCT_NAME": "Tempur-Pedic Mattress", "TOTAL_REVENUE": 9061755.86},
    {"PRODUCT_NAME": "Instant Pot", "TOTAL_REVENUE": 8903475.26},
    {"PRODUCT_NAME": "MacBook Air", "TOTAL_REVENUE": 7362516.81},
    {"PRODUCT_NAME": "Apple Watch", "TOTAL_REVENUE": 6834472.35},
    {"PRODUCT_NAME": "Apple iPhone 14", "TOTAL_REVENUE": 5740819.18},
]


def fallback_sql_for_prompt(prompt: str) -> str | None:
    """Return deterministic SQL for narrow, already-rehearsed demo prompts."""
    normalized_prompt = prompt.lower()
    normalized_words = " ".join(normalized_prompt.split())

    if "profit margin" in normalized_words and "region" in normalized_words:
        return REGION_MARGIN_SQL

    if "monthly revenue in 2024" in normalized_words or (
        "revenue" in normalized_words and "2024" in normalized_words and "month" in normalized_words
    ):
        return MONTHLY_REVENUE_2024_SQL

    if "top 5 products" in normalized_words or "top five products" in normalized_words:
        return TOP_PRODUCTS_REVENUE_SQL

    if "profit" in normalized_words and "region" in normalized_words:
        return REGION_PROFIT_SQL

    if "profit" in normalized_words and "category" in normalized_words:
        return CATEGORY_PROFIT_SQL

    if "revenue by region" in normalized_words or "sales by region" in normalized_words:
        return REGION_REVENUE_SQL

    if (
        "what were total sales by product category" in normalized_words
        or "revenue by category" in normalized_words
        or "sales by category" in normalized_words
    ):
        return CATEGORY_SALES_SQL

    return None


def fallback_results_for_sql(sql: str | None) -> dict[str, object] | None:
    """Return cached results for a known safe SQL pattern."""
    if not sql:
        return None

    normalized_sql = " ".join(sql.lower().split())
    if '"admin"."product_sales_dataset_final"' not in normalized_sql:
        return None

    if "round(sum(\"profit\") / nullif(sum(\"revenue\"), 0) * 100" in normalized_sql:
        return {
            "columns": ["REGION", "TOTAL_PROFIT", "TOTAL_REVENUE", "PROFIT_MARGIN_PCT"],
            "rows": REGION_MARGIN_ROWS,
        }

    if "to_char(to_date(\"order_date\"" in normalized_sql and "2024" in normalized_sql:
        return {
            "columns": ["SALES_MONTH", "TOTAL_REVENUE"],
            "rows": MONTHLY_REVENUE_2024_ROWS,
        }

    if "sum(\"revenue\")" in normalized_sql and '"product_name"' in normalized_sql:
        return {
            "columns": ["PRODUCT_NAME", "TOTAL_REVENUE"],
            "rows": TOP_PRODUCTS_REVENUE_ROWS,
        }

    if "sum(\"profit\")" in normalized_sql and '"category"' in normalized_sql:
        return {
            "columns": ["PRODUCT_CATEGORY", "TOTAL_PROFIT"],
            "rows": CATEGORY_PROFIT_ROWS,
        }

    if "sum(\"profit\")" in normalized_sql and '"region"' in normalized_sql:
        return {
            "columns": ["REGION", "TOTAL_PROFIT"],
            "rows": REGION_PROFIT_ROWS,
        }

    if "sum(\"revenue\")" in normalized_sql and '"region"' in normalized_sql:
        return {
            "columns": ["REGION", "TOTAL_REVENUE"],
            "rows": REGION_REVENUE_ROWS,
        }

    if "sum(\"revenue\")" not in normalized_sql:
        return None
    if '"category"' not in normalized_sql:
        return None

    return {
        "columns": ["PRODUCT_CATEGORY", "TOTAL_SALES"],
        "rows": CATEGORY_SALES_ROWS,
    }
