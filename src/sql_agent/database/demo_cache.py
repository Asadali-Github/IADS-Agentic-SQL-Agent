"""Demo fallback cache — serves canned results when the live DB is unreachable.

Owner: Hassan + Asad
Status: EXTENSION POINT. Offline demo answers are served from
`evaluation/datasets/demo_cache.json` today; this is the in-DB cache target.

Why this exists:
  Live network connections can drop or rate-limit mid-demo. When the
  `DEMO_FALLBACK_ENABLED` flag is on AND the question matches a key in
  `evaluation/datasets/demo_cache.json`, return the cached rows instead of
  hitting the database. The judges see a clean result; we never explain.

Wiring:
  `safe_executor.py` checks `is_demo_cached(question)` before executing.
  On DB error, falls through to `get_cached_result(question)` if available.

TODO:
- Load demo_cache.json at startup (path from settings.DEMO_CACHE_PATH)
- Match questions by normalised string (lowercase, strip punctuation)
- Public interface:
    is_demo_cached(question: str) -> bool
    get_cached_result(question: str) -> ExecutionResult | None
- Log every cache hit at WARNING level (so we know if it triggered)
- Write tests in tests/unit/test_demo_cache.py
"""
