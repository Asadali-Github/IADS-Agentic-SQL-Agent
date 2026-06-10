"""Backwards-compatible alias for :mod:`result_transforms`.

The implementation lives in ``result_transforms``; this thin shim keeps any
older ``import result_ops`` working.
"""

from __future__ import annotations

try:
    from result_transforms import *  # noqa: F401,F403
    from result_transforms import (  # noqa: F401
        TransformResult, classify, apply,
        _numeric_cols, _text_cols, _primary_numeric,
    )
except Exception:  # pragma: no cover
    from frontend.result_transforms import *  # noqa: F401,F403
    from frontend.result_transforms import (  # noqa: F401
        TransformResult, classify, apply,
        _numeric_cols, _text_cols, _primary_numeric,
    )
