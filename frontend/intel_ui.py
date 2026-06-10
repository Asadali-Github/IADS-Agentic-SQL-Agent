"""Streamlit rendering for the intelligent dashboard features.

Kept separate from ``streamlit_app.py`` so the heavy UI logic lives in one
testable place. Provides:

* :func:`run_or_transform` - answer a follow-up by transforming the previous
  result in memory (no DB hit) when possible, else fall back to the API.
* :func:`render_intent_preview` - "I understood this as ..." card.
* :func:`render_insights`       - auto highlights & anomalies.
* :func:`render_smart_viz`      - chart picker that recommends the best chart.
* :func:`render_followups`      - clickable, data-aware next-question chips.
* :func:`render_explanation`    - plain-English description of the result.
"""

from __future__ import annotations

import time
from typing import Callable, Optional

import pandas as pd
import plotly.express as px
import streamlit as st

try:
    import result_transforms as rt
    import dash_intel as di
except Exception:  # pragma: no cover
    from frontend import result_transforms as rt  # type: ignore
    from frontend import dash_intel as di  # type: ignore

_COLOURS = px.colors.qualitative.Set2
_QUEUE_KEY = "_queued_question"


# ---------------------------------------------------------------------------
# Follow-up: transform-in-memory or fall back to the database
# ---------------------------------------------------------------------------

def run_or_transform(question: str, session_id: Optional[str],
                     prev_df: Optional[pd.DataFrame],
                     call_api: Callable[[str, Optional[str]], dict]) -> dict:
    """Answer ``question`` against the previous result if it is a pure transform,
    otherwise call the backend API. Returns an API-shaped response dict."""
    if prev_df is not None and len(prev_df) and rt.classify(question):
        t0 = time.perf_counter()
        tr = rt.apply(question, prev_df)
        if tr.applied and tr.df is not None:
            df = tr.df
            return {
                "question": question,
                "resolved_question": None,
                "answer": f"Reshaped the previous result — {tr.description}.",
                "rows": df.to_dict("records"),
                "columns": list(df.columns),
                "sql": "-- Applied to the previous result in memory (no new database query).",
                "explanation": ("This follow-up was answered by transforming the rows already on "
                                "screen, so the database was not queried again."),
                "explanation_bullets": tr.ops,
                "insights": di.compute_insights(df),
                "chart": None,
                "tables_used": [],
                "confidence": 1.0,
                "clarification": None,
                "approximate_match": False,
                "provider": "in_memory_transform",
                "transform_ops": tr.ops,
                "is_transform": True,
                "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
                "error": None,
                "session_id": session_id,
            }
        # tr.fallback -> fall through to the database
    return call_api(question, session_id)


# ---------------------------------------------------------------------------
# Intent preview
# ---------------------------------------------------------------------------

def render_intent_preview(question: str, prev_df: Optional[pd.DataFrame]) -> None:
    info = di.analyze_intent(question, prev_df)
    is_followup = info.get("uses_previous_result")
    icon = "🔁" if is_followup else "🗄️"
    colour = "#0d9488" if is_followup else "#0f6b8a"
    bg = "#ecfdf5" if is_followup else "#eff6ff"

    bits = []
    if info.get("operations"):
        bits.append("Will apply: " + "; ".join(info["operations"]))
    else:
        if info.get("measure"):
            bits.append(f"Measure: <b>{info['measure']}</b>")
        if info.get("dimension"):
            bits.append(f"Grouped by: <b>{info['dimension']}</b>")
        if info.get("note"):
            bits.append(info["note"])
    detail = " &nbsp;·&nbsp; ".join(bits) if bits else "Interpreting your question…"

    st.markdown(
        f'<div style="background:{bg};border:1px solid {colour}33;border-left:4px solid {colour};'
        f'border-radius:10px;padding:0.6rem 0.9rem;margin:0.3rem 0 0.6rem;font-size:0.85rem;color:#334155;">'
        f'{icon} <b style="color:{colour};">{info["mode"]}</b><br><span style="font-size:0.8rem;">{detail}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Auto-insights
# ---------------------------------------------------------------------------

def render_insights(df: pd.DataFrame) -> None:
    items = di.compute_insights(df)
    if not items:
        return
    st.markdown('<div style="font-size:0.72rem;font-weight:700;color:#6b7280;'
                'text-transform:uppercase;letter-spacing:1px;margin:0.8rem 0 0.4rem;">'
                '✨ What stands out</div>', unsafe_allow_html=True)
    chips = "".join(
        f'<div style="background:linear-gradient(90deg,#1e3a5f,#0f6b8a);color:#fff;'
        f'border-radius:10px;padding:0.5rem 0.85rem;font-size:0.83rem;line-height:1.4;'
        f'margin-bottom:0.35rem;">{i}</div>' for i in items)
    st.markdown(f'<div style="display:flex;flex-direction:column;gap:0.1rem;">{chips}</div>',
                unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Smart visualization picker
# ---------------------------------------------------------------------------

def _plot(opt, df: pd.DataFrame) -> None:
    t = opt.type
    if t == "metric":
        val = df[opt.y].iloc[0]
        st.metric(label=di._humanize(opt.y), value=f"{val:,.0f}" if isinstance(val, float) else val)
        return
    if t == "table":
        st.dataframe(df, use_container_width=True)
        return
    try:
        if t == "line":
            fig = px.line(df, x=opt.x, y=opt.y, markers=True, template="plotly_white",
                          color_discrete_sequence=["#0f6b8a"])
        elif t == "pie":
            fig = px.pie(df, names=opt.x, values=opt.y, hole=0.38,
                         color_discrete_sequence=_COLOURS)
        elif t == "scatter":
            fig = px.scatter(df, x=opt.x, y=opt.y, template="plotly_white",
                             color_discrete_sequence=_COLOURS)
        else:  # bar
            fig = px.bar(df, x=opt.x, y=opt.y, template="plotly_white", text_auto=".2s",
                         color=opt.x, color_discrete_sequence=_COLOURS)
            fig.update_layout(showlegend=False)
        fig.update_layout(plot_bgcolor="white", paper_bgcolor="white",
                          margin=dict(t=30, b=30, l=10, r=10))
        st.plotly_chart(fig, use_container_width=True)
    except Exception as exc:  # noqa: BLE001
        st.caption(f"Could not render {t} chart: {exc}")
        st.dataframe(df, use_container_width=True)


def render_smart_viz(df: pd.DataFrame, key: str) -> None:
    options = di.recommend_charts(df)
    if not options:
        st.dataframe(df, use_container_width=True)
        return

    labels = [o.label + ("  ⭐" if o.recommended else "") for o in options]
    default = next((i for i, o in enumerate(options) if o.recommended), 0)
    chosen = st.radio("Chart type", labels, index=default, horizontal=True,
                      key=f"viz_{key}", label_visibility="collapsed")
    opt = options[labels.index(chosen)]
    st.caption(f"💡 {opt.reason}")
    _plot(opt, df)


# ---------------------------------------------------------------------------
# Suggested follow-up chips (clickable)
# ---------------------------------------------------------------------------

def render_followups(df: pd.DataFrame, question: str, key: str) -> None:
    sugg = di.suggest_followups(df, question)
    if not sugg:
        return
    st.markdown('<div style="font-size:0.72rem;font-weight:700;color:#6b7280;'
                'text-transform:uppercase;letter-spacing:1px;margin:0.9rem 0 0.4rem;">'
                '💬 Try next</div>', unsafe_allow_html=True)
    cols = st.columns(2)
    for i, s in enumerate(sugg):
        tag = "⚡" if s.kind == "transform" else "📊"
        with cols[i % 2]:
            if st.button(f"{tag} {s.label}", key=f"fu_{key}_{i}", use_container_width=True):
                st.session_state[_QUEUE_KEY] = s.query
                st.rerun()


def pop_queued_question() -> Optional[str]:
    """Return and clear a follow-up question queued by a chip click."""
    q = st.session_state.get(_QUEUE_KEY)
    if q:
        st.session_state[_QUEUE_KEY] = None
    return q


# ---------------------------------------------------------------------------
# Plain-English explanation
# ---------------------------------------------------------------------------

def render_explanation(df: pd.DataFrame, question: str = "") -> None:
    text = di.explain_answer(df, question)
    if text:
        st.markdown(
            f'<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;'
            f'padding:0.7rem 1rem;margin:0.4rem 0;font-size:0.88rem;color:#475569;line-height:1.5;">'
            f'📖 {text}</div>', unsafe_allow_html=True)
