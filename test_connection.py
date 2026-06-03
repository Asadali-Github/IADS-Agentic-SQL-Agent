"""Smoke test for local OCI and Autonomous Database setup."""

from __future__ import annotations

import os

import oci
import oracledb
from dotenv import load_dotenv

from app.sql.oracle_connection import connect_adb


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _validate_oci_config() -> None:
    config_path = _required_env("OCI_CONFIG_PATH")
    profile = os.getenv("OCI_CONFIG_PROFILE", "DEFAULT")
    oci.config.validate_config(oci.config.from_file(config_path, profile))
    print("OCI config valid")


def _connect_adb() -> oracledb.Connection:
    return connect_adb()


def _count_largest_table(connection: oracledb.Connection) -> int:
    with connection.cursor() as cursor:
        cursor.execute("select table_name from user_tables order by table_name")
        table_names = [row[0] for row in cursor.fetchall()]

        if not table_names:
            raise RuntimeError("ADB connected, but no user tables were found")

        table_counts: list[tuple[str, int]] = []
        for table_name in table_names:
            cursor.execute(f"select count(*) from {_quote_identifier(table_name)}")
            table_counts.append((table_name, int(cursor.fetchone()[0])))

    table_name, row_count = max(table_counts, key=lambda item: item[1])
    print(f"ADB connected - {row_count} rows found in {table_name}")
    return row_count


def _test_select_ai(connection: oracledb.Connection, expected_rows: int) -> None:
    profile = os.getenv("SELECT_AI_PROFILE")
    if not profile:
        print("Select AI skipped: SELECT_AI_PROFILE is not set")
        return

    prompt = (
        "Answer in one short sentence. How many rows are in the main dataset? "
        f"The expected row count is {expected_rows}."
    )
    with connection.cursor() as cursor:
        cursor.callproc("DBMS_CLOUD_AI.SET_PROFILE", [profile])
        cursor.execute(f"select ai narrate {prompt}")
        answer = cursor.fetchone()[0]

    print(f"Select AI working: {answer}")


def main() -> None:
    load_dotenv()
    _validate_oci_config()
    with _connect_adb() as connection:
        row_count = _count_largest_table(connection)
        _test_select_ai(connection, row_count)


if __name__ == "__main__":
    main()
