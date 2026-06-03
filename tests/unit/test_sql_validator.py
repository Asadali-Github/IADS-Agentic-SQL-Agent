"""Unit tests for generated SQL validation."""

from __future__ import annotations

from app.sql.validator import validate_sql


def test_validate_accepts_safe_select_and_adds_limit() -> None:
    result = validate_sql(
        'SELECT "ps"."CATEGORY", SUM("ps"."REVENUE") AS total_sales '
        'FROM "ADMIN"."PRODUCT_SALES_DATASET_FINAL" "ps" '
        'GROUP BY "ps"."CATEGORY"'
    )

    assert result["is_valid"] is True
    assert result["reason"] == "SQL validation passed."
    assert result["tables"] == ["PRODUCT_SALES_DATASET_FINAL"]
    assert result["safe_sql"].endswith("FETCH FIRST 100 ROWS ONLY")


def test_validate_keeps_existing_oracle_fetch_limit() -> None:
    sql = (
        'SELECT "ps"."CATEGORY" FROM "ADMIN"."PRODUCT_SALES_DATASET_FINAL" "ps" '
        "FETCH FIRST 100 ROWS ONLY"
    )

    result = validate_sql(sql)

    assert result["is_valid"] is True
    assert result["safe_sql"] == sql


def test_validate_caps_large_oracle_fetch_limit() -> None:
    result = validate_sql("SELECT * FROM product_sales FETCH FIRST 900 ROWS ONLY")

    assert result["is_valid"] is True
    assert result["safe_sql"] == "SELECT * FROM product_sales FETCH FIRST 500 ROWS ONLY"


def test_validate_rejects_update() -> None:
    result = validate_sql("UPDATE product_sales SET revenue = 0")

    assert result["is_valid"] is False
    assert "Blocked keyword" in result["reason"]


def test_validate_rejects_multiple_statements() -> None:
    result = validate_sql("SELECT * FROM product_sales; SELECT * FROM users")

    assert result["is_valid"] is False
    assert result["reason"] == "Exactly one SQL statement is allowed."


def test_validate_rejects_comments() -> None:
    result = validate_sql("SELECT * FROM product_sales -- bypass")

    assert result["is_valid"] is False
    assert result["reason"] == "SQL comments are not allowed in generated queries."
