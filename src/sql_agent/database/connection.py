"""Autonomous Database connection pool.

Owner: Hassan
Status: INTERFACE SPEC. Live runs connect to OCI Autonomous Database via
`oracledb`; offline runs use `evaluation/local_db.py` (DuckDB over the seed).

"""
"""
Managed Oracle Autonomous Database connection pool.
One pool per process, reused across all requests.
"""

import oracledb
from sql_agent.config.settings import settings

_pool: oracledb.AsyncConnectionPool | None = None


async def get_pool() -> oracledb.AsyncConnectionPool:
    """Return the singleton pool, creating it on first call."""
    global _pool
    if _pool is None:
        _pool = oracledb.create_pool_async(
            user=settings.adb_user,
            password=settings.adb_password,
            dsn=settings.adb_dsn,
            config_dir=settings.adb_wallet_location,
            wallet_location=settings.adb_wallet_location,
            wallet_password=settings.adb_wallet_password,
            min=settings.db_pool_min,
            max=settings.db_pool_max,
            increment=1,
        )
    return _pool


async def close_pool() -> None:
    """Graceful shutdown — call from app lifespan teardown."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None