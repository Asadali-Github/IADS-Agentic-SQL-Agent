"""Profile CSV files so their schema can become RAG context."""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

DEFAULT_SAMPLE_SIZE = 5


def profile_csv(file_path: Path, sample_size: int = DEFAULT_SAMPLE_SIZE) -> dict[str, Any]:
    """Return lightweight schema information for a CSV file."""
    if not file_path.exists():
        raise FileNotFoundError(f"CSV file not found: {file_path}")

    if file_path.stat().st_size == 0:
        raise ValueError(
            f"CSV file is empty: {file_path}. Replace it with the real dataset first."
        )

    sample_values: dict[str, list[str]] = defaultdict(list)
    row_count = 0

    with file_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        raw_columns = reader.fieldnames or []
        columns = [column.strip() for column in raw_columns]

        if not raw_columns:
            raise ValueError(f"CSV file has no header row: {file_path}")

        for row in reader:
            row_count += 1
            for raw_column, column in zip(raw_columns, columns, strict=True):
                value = (row.get(raw_column) or "").strip()
                if value and len(sample_values[column]) < sample_size:
                    sample_values[column].append(value)

    return {
        "file_name": file_path.name,
        "row_count": row_count,
        "columns": [
            {
                "name": column,
                "inferred_type": infer_column_type(sample_values[column]),
                "sample_values": sample_values[column],
            }
            for column in columns
        ],
    }


def profile_to_rag_documents(
    profile: dict[str, Any],
    table_name: str = "product_sales",
) -> list[dict]:
    """Convert a CSV profile into placeholder-style RAG documents."""
    column_summaries = [
        f"{column['name']} ({column['inferred_type']})"
        for column in profile["columns"]
    ]
    table_document = {
        "id": f"schema_{table_name}",
        "title": f"{table_name} Dataset Table Description",
        "type": "table_schema",
        "content": (
            f"The {table_name} dataset comes from {profile['file_name']} and contains "
            f"{profile['row_count']} rows. Columns include: {', '.join(column_summaries)}."
        ),
    }

    column_documents = [
        {
            "id": f"column_{table_name}_{column['name'].lower()}",
            "title": f"{column['name']} Column Description",
            "type": "column_definition",
            "content": (
                f"Column {column['name']} belongs to the {table_name} dataset. "
                f"Inferred type: {column['inferred_type']}. "
                f"Sample values: {', '.join(column['sample_values']) or 'none available'}."
            ),
        }
        for column in profile["columns"]
    ]

    return [table_document, *column_documents]


def infer_column_type(values: list[str]) -> str:
    """Infer a simple beginner-friendly column type from sample values."""
    if not values:
        return "unknown"

    if all(is_integer(value) for value in values):
        return "integer"

    if all(is_float(value) for value in values):
        return "number"

    if all(looks_like_date(value) for value in values):
        return "date"

    return "text"


def is_integer(value: str) -> bool:
    """Return whether a string looks like an integer."""
    try:
        int(value)
    except ValueError:
        return False

    return True


def is_float(value: str) -> bool:
    """Return whether a string looks like a number."""
    try:
        float(value)
    except ValueError:
        return False

    return True


def looks_like_date(value: str) -> bool:
    """Return whether a string looks like a common date format."""
    date_markers = ["-", "/"]
    return any(marker in value for marker in date_markers) and any(
        character.isdigit() for character in value
    )


def main() -> None:
    """Print a CSV profile as JSON for quick inspection."""
    if len(sys.argv) < 2:
        raise SystemExit(
            "Usage: python -m app.data.csv_profiler <path-to-csv> [--rag-docs]"
        )

    try:
        profile = profile_csv(Path(sys.argv[1]))
    except (FileNotFoundError, ValueError) as error:
        raise SystemExit(str(error)) from error

    output = profile_to_rag_documents(profile) if "--rag-docs" in sys.argv else profile
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
