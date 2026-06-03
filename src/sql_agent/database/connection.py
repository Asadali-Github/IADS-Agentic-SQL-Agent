"""Autonomous Database connection pool.

Owner: Hassan
Status: placeholder — implement during the hackathon.

TODO:
- Define the public interface here
- Implement the logic
- Write tests in tests/unit/test_connection.py
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