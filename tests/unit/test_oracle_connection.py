"""Unit tests for Oracle connection helpers."""

from __future__ import annotations

from pathlib import Path

from app.sql.oracle_connection import resolve_adb_dsn


def test_resolve_adb_dsn_converts_wallet_alias_to_tcps_easy_connect(tmp_path: Path) -> None:
    wallet = tmp_path / "wallet"
    wallet.mkdir()
    (wallet / "tnsnames.ora").write_text(
        "hackatondb_high = (description= "
        "(address=(protocol=tcps)(port=1522)(host=adb.uk-london-1.oraclecloud.com))"
        "(connect_data=(service_name=g123_hackatondb_high.adb.oraclecloud.com))"
        "(security=(ssl_server_dn_match=yes)))",
        encoding="utf-8",
    )

    dsn = resolve_adb_dsn("hackatondb_high", str(wallet))

    assert dsn == (
        "tcps://adb.uk-london-1.oraclecloud.com:1522/"
        "g123_hackatondb_high.adb.oraclecloud.com"
    )


def test_resolve_adb_dsn_keeps_explicit_dsn(tmp_path: Path) -> None:
    explicit_dsn = "tcps://adb.uk-london-1.oraclecloud.com:1522/service"

    dsn = resolve_adb_dsn(explicit_dsn, str(tmp_path))

    assert dsn == explicit_dsn
