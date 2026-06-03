"""Shared Oracle Autonomous Database connection helpers."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

try:
    import oracledb
except ModuleNotFoundError:  # pragma: no cover - depends on local environment
    oracledb = None  # type: ignore[assignment]


def connect_adb() -> Any:
    """Connect to ADB using the project environment and wallet."""
    load_dotenv()
    if oracledb is None:
        raise RuntimeError("The oracledb package is not installed.")

    wallet_location = _resolve_project_path(_required_env("ADB_WALLET_LOCATION"))
    connect_kwargs: dict[str, str] = {
        "user": _required_env("ADB_USER"),
        "password": _required_env("ADB_PASSWORD"),
        "dsn": resolve_adb_dsn(_required_env("ADB_DSN"), wallet_location),
        "wallet_location": wallet_location,
    }

    wallet_password = os.getenv("ADB_WALLET_PASSWORD")
    if wallet_password:
        connect_kwargs["wallet_password"] = wallet_password

    return oracledb.connect(**connect_kwargs)


def resolve_adb_dsn(dsn: str, wallet_location: str) -> str:
    """Return an explicit TCPS Easy Connect string for a wallet alias when possible."""
    if _is_explicit_dsn(dsn):
        return dsn

    tnsnames_path = Path(wallet_location) / "tnsnames.ora"
    if not tnsnames_path.exists():
        return dsn

    descriptor = _find_tns_descriptor(tnsnames_path.read_text(encoding="utf-8"), dsn)
    if not descriptor:
        return dsn

    host = _extract_descriptor_value(descriptor, "host")
    port = _extract_descriptor_value(descriptor, "port")
    service_name = _extract_descriptor_value(descriptor, "service_name")
    if not host or not port or not service_name:
        return dsn

    return f"tcps://{host}:{port}/{service_name}"


def _is_explicit_dsn(dsn: str) -> bool:
    return dsn.startswith(("tcps://", "tcp://")) or "/" in dsn or "(" in dsn


def _find_tns_descriptor(tnsnames: str, alias: str) -> str | None:
    pattern = re.compile(rf"^\s*{re.escape(alias)}\s*=\s*(?P<descriptor>.+)$", re.MULTILINE)
    match = pattern.search(tnsnames)
    if not match:
        return None
    return match.group("descriptor")


def _extract_descriptor_value(descriptor: str, key: str) -> str | None:
    pattern = re.compile(rf"\b{re.escape(key)}\s*=\s*([^\)]+)", re.IGNORECASE)
    match = pattern.search(descriptor)
    if not match:
        return None
    return match.group(1).strip()


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _resolve_project_path(value: str) -> str:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return str(path.resolve())
