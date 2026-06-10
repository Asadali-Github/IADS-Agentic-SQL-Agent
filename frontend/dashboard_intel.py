"""Backwards-compatible alias for :mod:`dash_intel`.

The implementation lives in ``dash_intel``; this thin shim keeps any older
``import dashboard_intel`` working.
"""

from __future__ import annotations

try:
    from dash_intel import *  # noqa: F401,F403
    from dash_intel import (  # noqa: F401
        Suggestion, ChartOption, suggest_followups, recommend_charts,
        compute_insights, analyze_intent, explain_answer,
    )
except Exception:  # pragma: no cover
    from frontend.dash_intel import *  # noqa: F401,F403
    from frontend.dash_intel import (  # noqa: F401
        Suggestion, ChartOption, suggest_followups, recommend_charts,
        compute_insights, analyze_intent, explain_answer,
    )
