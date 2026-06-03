"""Safe SQL executor: read-only user, timeout, row cap.

Owner: Hassan
Status: INTERFACE SPEC. The read-only executor is realized offline in
`evaluation/local_db.py` (DuckDB) and live via the ADB read-only user.

TODO:
- Define the public interface here
- Implement the logic:
    1. If DEMO_FALLBACK_ENABLED and demo_cache.is_demo_cached(question):
         return demo_cache.get_cached_result(question)
    2. Try real execution against the read-only DB user
    3. On DB error AND DEMO_FALLBACK_ENABLED:
         fall back to demo_cache.get_cached_result(question)
- Enforce 15-second timeout and 500-row cap (from settings)
- Write tests in tests/unit/test_safe_executor.py

See also:
- src/sql_agent/database/demo_cache.py — the fallback cache
- src/sql_agent/retrieval/row_fallback.py — vector fallback when SQL returns 0 rows
"""
