"""Streamlit frontend — calls the FastAPI backend.

Owner: Mehdi
Status: implemented.
"""

from __future__ import annotations

import os

import httpx
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

API_URL = os.getenv("API_URL", "http://localhost:8000")
CONFIDENCE_THRESHOLD = 0.7

_PLACEHOLDER_TABLES: list[str] = []

# ---------------------------------------------------------------------------
# Copy strings
# ---------------------------------------------------------------------------

COPY = {
    "app_name": "IADS SQL Agent",
    "app_caption": "AI-powered natural language querying",
    "db_section": "Database",
    "db_connected": "Connected",
    "db_not_connected": "Not connected",
    "db_waiting": "Waiting for OCI connection…",
    "tables_label": "Tables available",
    "demo_section": "Demo mode",
    "demo_caption": "Use cached results instead of live DB — safe for presentations.",
    "demo_toggle": "Use cached data",
    "clear_button": "🗑  Clear conversation",
    "chat_placeholder": "Ask a question about your data…",
    "confidence_ok": "High confidence",
    "confidence_warn": "Low confidence — double-check before acting on this.",
    "approx_match": "No exact match found. Showing the closest results instead.",
    "expander_label": "🔬 How did the AI calculate this?",
    "insights_label": "Key insights",
    "clarify_label": "I need a quick clarification",
    "tables_used_label": "Tables used",
    "explanation_label": "Plain-English breakdown",
    "sql_label": "Generated SQL",
    "api_unreachable": "Could not reach the API at {url}. Make sure the backend is running.",
}

# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

CUSTOM_CSS = """
<style>
/* ── Global ────────────────────────────────────────────────── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

/* ── Keyframe animations ───────────────────────────────────── */
@keyframes fadeInUp {
    from { opacity: 0; transform: translateY(24px); }
    to   { opacity: 1; transform: translateY(0); }
}
@keyframes fadeIn {
    from { opacity: 0; }
    to   { opacity: 1; }
}
@keyframes pulse {
    0%, 100% { opacity: 1; transform: scale(1); }
    50%      { opacity: 0.6; transform: scale(0.95); }
}
@keyframes shimmer {
    0%   { background-position: 0% 50%; }
    50%  { background-position: 100% 50%; }
    100% { background-position: 0% 50%; }
}
@keyframes float {
    0%, 100% { transform: translateY(0); }
    50%      { transform: translateY(-4px); }
}
@keyframes gradientBorder {
    0%   { border-color: rgba(15, 107, 138, 0.3); }
    50%  { border-color: rgba(13, 148, 136, 0.5); }
    100% { border-color: rgba(15, 107, 138, 0.3); }
}

/* ── Page header — animated gradient ───────────────────────── */
.iads-header {
    background: linear-gradient(135deg, #1e3a5f 0%, #0f6b8a 30%, #0d9488 60%, #065f46 100%);
    background-size: 300% 300%;
    animation: shimmer 8s ease-in-out infinite;
    border-radius: 20px;
    padding: 2.5rem 2.5rem 2.2rem;
    margin-bottom: 1.8rem;
    box-shadow: 0 12px 40px rgba(14, 107, 138, 0.3), 0 0 0 1px rgba(255,255,255,0.05) inset;
    text-align: center;
    position: relative;
    overflow: hidden;
}
.iads-header::before {
    content: '';
    position: absolute;
    top: -50%;
    left: -50%;
    width: 200%;
    height: 200%;
    background: radial-gradient(circle at 30% 50%, rgba(255,255,255,0.06) 0%, transparent 50%);
    pointer-events: none;
}
.iads-header h1 {
    color: #ffffff;
    font-size: 2.5rem;
    font-weight: 700;
    margin: 0 0 0.4rem;
    letter-spacing: -0.5px;
    position: relative;
    text-shadow: 0 2px 8px rgba(0,0,0,0.15);
}
.iads-header p {
    color: rgba(255,255,255,0.85);
    font-size: 1.08rem;
    margin: 0;
    position: relative;
}
.iads-badge {
    display: inline-block;
    background: rgba(255,255,255,0.14);
    border: 1px solid rgba(255,255,255,0.25);
    border-radius: 24px;
    padding: 5px 18px;
    font-size: 0.76rem;
    color: #fff;
    margin-top: 0.9rem;
    letter-spacing: 0.6px;
    font-weight: 500;
    position: relative;
    animation: float 4s ease-in-out infinite;
    backdrop-filter: blur(4px);
}

/* ── Summary stats cards — glassmorphism ───────────────────── */
.summary-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 1rem;
    margin-bottom: 2rem;
    animation: fadeInUp 0.6s ease-out 0.15s both;
}
.summary-card {
    background: rgba(255, 255, 255, 0.65);
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
    border: 1px solid rgba(255, 255, 255, 0.35);
    border-radius: 18px;
    padding: 1.4rem 1rem;
    text-align: center;
    transition: transform 0.25s ease, box-shadow 0.25s ease, border-color 0.25s ease;
    box-shadow: 0 4px 24px rgba(0, 0, 0, 0.05);
    position: relative;
    overflow: hidden;
}
.summary-card::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 3px;
    background: linear-gradient(90deg, #0f6b8a, #0d9488, #34d399);
    opacity: 0;
    transition: opacity 0.25s ease;
}
.summary-card:hover {
    transform: translateY(-5px);
    box-shadow: 0 12px 36px rgba(14, 107, 138, 0.15);
    border-color: rgba(15, 107, 138, 0.3);
}
.summary-card:hover::before {
    opacity: 1;
}
.summary-card .card-icon {
    font-size: 2.2rem;
    margin-bottom: 0.6rem;
    display: block;
}
.summary-card .card-value {
    font-size: 1.4rem;
    font-weight: 700;
    color: #1e3a5f;
    margin-bottom: 0.25rem;
    line-height: 1.3;
}
.summary-card .card-label {
    font-size: 0.72rem;
    color: #6b7280;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.8px;
}

/* ── How It Works section ──────────────────────────────────── */
.how-section {
    margin: 1.5rem 0 2rem;
    animation: fadeInUp 0.6s ease-out 0.3s both;
}
.how-section-title {
    font-size: 0.76rem;
    font-weight: 700;
    color: #6b7280;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    margin-bottom: 1rem;
    text-align: center;
}
.how-steps {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 1.2rem;
    position: relative;
}
.how-step {
    text-align: center;
    padding: 1.5rem 1.1rem 1.3rem;
    background: linear-gradient(145deg, #f0f9ff 0%, #e8f4f8 100%);
    border-radius: 16px;
    border: 1px solid #bae6fd;
    transition: transform 0.25s ease, box-shadow 0.25s ease;
    position: relative;
}
.how-step:hover {
    transform: translateY(-4px);
    box-shadow: 0 8px 28px rgba(14, 107, 138, 0.12);
}
.how-step .step-num {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 38px;
    height: 38px;
    background: linear-gradient(135deg, #0f6b8a, #0d9488);
    color: #fff;
    border-radius: 50%;
    font-weight: 700;
    font-size: 1rem;
    margin-bottom: 0.8rem;
    box-shadow: 0 4px 12px rgba(15, 107, 138, 0.3);
}
.how-step .step-title {
    font-size: 1.05rem;
    font-weight: 700;
    color: #1e3a5f;
    margin-bottom: 0.35rem;
}
.how-step .step-desc {
    font-size: 0.83rem;
    color: #64748b;
    line-height: 1.5;
}
.step-connector {
    display: flex;
    align-items: center;
    justify-content: center;
    color: #94a3b8;
    font-size: 1.2rem;
    font-weight: 700;
}

/* ── Feature highlight cards ───────────────────────────────── */
.features-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 0.9rem;
    margin: 0.8rem 0 2rem;
    animation: fadeInUp 0.6s ease-out 0.45s both;
}
.feature-card {
    display: flex;
    align-items: flex-start;
    gap: 0.85rem;
    padding: 1.15rem 1.2rem;
    background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
    border: 1.5px solid #e2e8f0;
    border-radius: 14px;
    transition: all 0.25s ease;
    cursor: default;
}
.feature-card:hover {
    background: linear-gradient(135deg, #ffffff 0%, #f0f9ff 100%);
    border-color: #0f6b8a;
    box-shadow: 0 6px 20px rgba(14, 107, 138, 0.1);
    transform: translateY(-3px);
}
.feature-card .feat-icon {
    font-size: 1.6rem;
    flex-shrink: 0;
    margin-top: 0.15rem;
}
.feature-card .feat-title {
    font-size: 0.9rem;
    font-weight: 700;
    color: #1e3a5f;
    margin-bottom: 0.2rem;
}
.feature-card .feat-desc {
    font-size: 0.78rem;
    color: #64748b;
    line-height: 1.45;
}

/* ── Data summary card ─────────────────────────────────────── */
.data-summary-card {
    background: linear-gradient(135deg, #f0f9ff 0%, #e8f4f8 40%, #f0fdf4 100%);
    border: 1.5px solid #bae6fd;
    border-radius: 14px;
    padding: 1rem 1.3rem 1.1rem;
    margin: 0.6rem 0 1rem;
    box-shadow: 0 3px 16px rgba(14, 107, 138, 0.08);
    animation: fadeIn 0.4s ease-out;
}
.data-summary-card .ds-title {
    font-size: 0.68rem;
    font-weight: 700;
    color: #0369a1;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-bottom: 0.7rem;
}
.data-summary-stats {
    display: flex;
    flex-wrap: wrap;
    gap: 0.8rem;
}
.ds-stat {
    flex: 1;
    min-width: 110px;
    text-align: center;
    padding: 0.65rem 0.5rem;
    background: rgba(255, 255, 255, 0.75);
    backdrop-filter: blur(8px);
    border-radius: 11px;
    border: 1px solid rgba(255, 255, 255, 0.5);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.03);
}
.ds-stat .ds-val {
    font-size: 1.15rem;
    font-weight: 700;
    color: #1e3a5f;
    line-height: 1.3;
}
.ds-stat .ds-lbl {
    font-size: 0.68rem;
    color: #64748b;
    font-weight: 500;
    margin-top: 0.15rem;
    text-transform: uppercase;
    letter-spacing: 0.3px;
}

/* ── Answer card ────────────────────────────────────────────── */
.answer-card {
    background: linear-gradient(135deg, #f0fdf4 0%, #ecfdf5 100%);
    border: 1.5px solid #34d399;
    border-radius: 14px;
    padding: 1.3rem 1.5rem;
    margin: 0.75rem 0 1rem;
    box-shadow: 0 4px 16px rgba(52, 211, 153, 0.12);
    animation: fadeInUp 0.4s ease-out;
}
.answer-card .answer-label {
    font-size: 0.68rem;
    font-weight: 700;
    color: #059669;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-bottom: 0.4rem;
}
.answer-card .answer-text {
    font-size: 1.15rem;
    font-weight: 600;
    color: #064e3b;
    line-height: 1.55;
}

/* ── Warning answer card ────────────────────────────────────── */
.answer-card-warn {
    background: linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%);
    border: 1.5px solid #f59e0b;
    border-radius: 14px;
    padding: 1.3rem 1.5rem;
    margin: 0.75rem 0 1rem;
    box-shadow: 0 4px 16px rgba(245,158,11,0.1);
    animation: fadeInUp 0.4s ease-out;
}
.answer-card-warn .answer-label {
    font-size: 0.68rem;
    font-weight: 700;
    color: #d97706;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-bottom: 0.4rem;
}
.answer-card-warn .answer-text {
    font-size: 1.15rem;
    font-weight: 600;
    color: #78350f;
    line-height: 1.55;
}

/* ── Insights strip ─────────────────────────────────────────── */
.insights-strip {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    margin: 0.5rem 0 1rem;
}
.insight-chip {
    background: linear-gradient(90deg, #1e3a5f 0%, #0f6b8a 100%);
    color: #fff;
    border-radius: 20px;
    padding: 0.35rem 0.9rem;
    font-size: 0.82rem;
    font-weight: 500;
    line-height: 1.4;
    box-shadow: 0 2px 8px rgba(30,58,95,0.2);
    transition: transform 0.2s ease, box-shadow 0.2s ease;
}
.insight-chip:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(30,58,95,0.3);
}

/* ── Confidence bar ─────────────────────────────────────────── */
.conf-row {
    display: flex;
    align-items: center;
    gap: 0.7rem;
    margin-bottom: 0.6rem;
}
.conf-label {
    font-size: 0.78rem;
    font-weight: 600;
    color: #6b7280;
    white-space: nowrap;
    width: 120px;
}
.conf-bar-bg {
    flex: 1;
    height: 8px;
    background: #e5e7eb;
    border-radius: 99px;
    overflow: hidden;
}
.conf-bar-fill-high {
    height: 100%;
    border-radius: 99px;
    background: linear-gradient(90deg, #34d399, #10b981);
    transition: width 0.6s ease-out;
}
.conf-bar-fill-low {
    height: 100%;
    border-radius: 99px;
    background: linear-gradient(90deg, #fbbf24, #f59e0b);
    transition: width 0.6s ease-out;
}
.conf-pct {
    font-size: 0.82rem;
    font-weight: 700;
    width: 38px;
    text-align: right;
}

/* ── Pipeline steps ─────────────────────────────────────────── */
.pipeline-row {
    display: flex;
    gap: 0.4rem;
    align-items: center;
    flex-wrap: wrap;
    margin: 0.5rem 0 1rem;
}
.pipeline-step {
    display: flex;
    align-items: center;
    gap: 0.3rem;
    background: #f3f4f6;
    border-radius: 8px;
    padding: 0.3rem 0.7rem;
    font-size: 0.76rem;
    color: #374151;
    font-weight: 500;
    transition: all 0.2s ease;
}
.pipeline-step.done {
    background: linear-gradient(135deg, #dcfce7, #d1fae5);
    color: #166534;
    border: 1px solid rgba(34, 197, 94, 0.2);
}
.pipeline-arrow {
    color: #9ca3af;
    font-size: 0.7rem;
}

/* ── Section header ─────────────────────────────────────────── */
.section-title {
    font-size: 0.72rem;
    font-weight: 700;
    color: #6b7280;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin: 1rem 0 0.4rem;
}

/* ── Metric tiles ───────────────────────────────────────────── */
.metric-tile {
    background: linear-gradient(135deg, #f9fafb 0%, #f3f4f6 100%);
    border: 1px solid #e5e7eb;
    border-radius: 12px;
    padding: 0.9rem 1rem;
    text-align: center;
    transition: transform 0.2s ease, box-shadow 0.2s ease;
}
.metric-tile:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(0,0,0,0.06);
}
.metric-tile .mt-val {
    font-size: 1.6rem;
    font-weight: 700;
    color: #1e3a5f;
}
.metric-tile .mt-lbl {
    font-size: 0.72rem;
    color: #9ca3af;
    font-weight: 500;
    margin-top: 0.1rem;
}

/* ── Clarification box ──────────────────────────────────────── */
.clarify-box {
    background: #eff6ff;
    border: 1px solid #bfdbfe;
    border-radius: 12px;
    padding: 0.75rem 1rem;
    margin: 0.5rem 0;
    font-size: 0.9rem;
    color: #1e40af;
}

/* ── Approx match banner ────────────────────────────────────── */
.approx-banner {
    background: #fff7ed;
    border: 1px solid #fed7aa;
    border-radius: 12px;
    padding: 0.6rem 1rem;
    font-size: 0.85rem;
    color: #c2410c;
    margin-bottom: 0.5rem;
}

/* ── Sidebar tweaks ─────────────────────────────────────────── */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0f172a 0%, #1e293b 100%);
}
section[data-testid="stSidebar"] * {
    color: #e2e8f0 !important;
}
section[data-testid="stSidebar"] .stButton > button {
    background: rgba(255,255,255,0.08) !important;
    border: 1px solid rgba(255,255,255,0.15) !important;
    color: #f1f5f9 !important;
    border-radius: 10px !important;
    font-weight: 500 !important;
    transition: all 0.2s ease !important;
}
section[data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(255,255,255,0.14) !important;
    border-color: rgba(255,255,255,0.25) !important;
    transform: translateY(-1px) !important;
}
section[data-testid="stSidebar"] hr {
    border-color: rgba(255,255,255,0.08) !important;
}

/* ── Sidebar status badges ──────────────────────────────────── */
.sidebar-status-ok {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 0.75rem;
    background: rgba(52,211,153,0.12);
    border: 1px solid rgba(52,211,153,0.3);
    border-radius: 10px;
    font-size: 0.84rem;
    color: #6ee7b7;
}
.sidebar-status-err {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 0.75rem;
    background: rgba(239,68,68,0.1);
    border: 1px solid rgba(239,68,68,0.25);
    border-radius: 10px;
    font-size: 0.84rem;
    color: #fca5a5;
}
.pulse-dot {
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #34d399;
    animation: pulse 2s ease-in-out infinite;
    box-shadow: 0 0 6px rgba(52,211,153,0.5);
}
.pulse-dot-err {
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #ef4444;
    animation: pulse 2s ease-in-out infinite;
    box-shadow: 0 0 6px rgba(239,68,68,0.5);
}

/* ── Sidebar version badge ──────────────────────────────────── */
.version-badge {
    text-align: center;
    padding: 0.6rem;
    margin-top: 0.5rem;
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 10px;
}
.version-badge .vb-name {
    font-size: 0.72rem;
    font-weight: 600;
    color: #94a3b8;
}
.version-badge .vb-ver {
    font-size: 0.65rem;
    color: #64748b;
    margin-top: 0.1rem;
}

/* ── Example question buttons ───────────────────────────────── */
div[data-testid="column"] .stButton > button {
    background: #f8fafc !important;
    border: 1.5px solid #e2e8f0 !important;
    color: #1e3a5f !important;
    border-radius: 12px !important;
    font-size: 0.88rem !important;
    font-weight: 500 !important;
    text-align: left !important;
    padding: 0.7rem 1rem !important;
    transition: all 0.2s ease !important;
    line-height: 1.4 !important;
    white-space: normal !important;
    height: auto !important;
}
div[data-testid="column"] .stButton > button:hover {
    background: #eff6ff !important;
    border-color: #3b82f6 !important;
    color: #1d4ed8 !important;
    box-shadow: 0 4px 12px rgba(59,130,246,0.15) !important;
    transform: translateY(-2px) !important;
}

/* ── Expander ───────────────────────────────────────────────── */
details summary {
    font-weight: 600;
    color: #374151;
}

/* ── Chat messages ──────────────────────────────────────────── */
[data-testid="stChatMessage"] {
    border-radius: 14px !important;
}

/* ── Tables ─────────────────────────────────────────────────── */
[data-testid="stDataFrame"] {
    border-radius: 10px;
    overflow: hidden;
    border: 1px solid #e5e7eb;
}

/* ── Tab active ─────────────────────────────────────────────── */
button[data-baseweb="tab"][aria-selected="true"] {
    color: #0f6b8a !important;
    border-bottom-color: #0f6b8a !important;
}

/* ── Gradient divider ───────────────────────────────────────── */
.gradient-divider {
    height: 1px;
    background: linear-gradient(90deg, transparent, rgba(14,107,138,0.15), transparent);
    border: none;
    margin: 1.5rem 0;
}
</style>
"""

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

def _init_state() -> None:
    defaults = {
        "session_id": None,
        "history": [],
        "demo_mode": False,
        "db_tables": _PLACEHOLDER_TABLES,
        "uploaded_db": None,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val

# ---------------------------------------------------------------------------
# API client
# ---------------------------------------------------------------------------

def _empty_error_response(msg: str, session_id: str | None) -> dict:
    return {
        "answer": "",
        "rows": [],
        "sql": "",
        "explanation": "",
        "insights": [],
        "chart": None,
        "clarification": None,
        "tables_used": [],
        "confidence": 0.0,
        "approximate_match": False,
        "error": msg,
        "session_id": session_id,
    }


def call_api(question: str, session_id: str | None) -> dict:
    payload = {"question": question, "session_id": session_id}
    try:
        resp = httpx.post(f"{API_URL}/query", json=payload, timeout=90)
        resp.raise_for_status()
        return resp.json()
    except httpx.ConnectError:
        return _empty_error_response(COPY["api_unreachable"].format(url=API_URL), session_id)
    except httpx.ReadTimeout:
        return _empty_error_response(
            "The query took too long to process. Try a simpler question or check the database.",
            session_id,
        )
    except Exception as exc:  # noqa: BLE001
        return _empty_error_response(str(exc), session_id)

# ---------------------------------------------------------------------------
# Chart rendering
# ---------------------------------------------------------------------------

_CHART_COLOURS = px.colors.qualitative.Set2

def _render_chart_from_spec(spec: dict | None, df: pd.DataFrame) -> None:
    if df.empty:
        return
    if spec and spec.get("type") and spec["type"] != "none":
        x, y, ctype = spec.get("x"), spec.get("y"), spec.get("type")
        title = spec.get("title") or ""
        try:
            if x in df.columns and y in df.columns:
                if ctype == "line":
                    fig = px.line(
                        df, x=x, y=y, markers=True, title=title,
                        color_discrete_sequence=["#0f6b8a"],
                        template="plotly_white",
                    )
                    fig.update_traces(line_width=2.5, marker_size=7)
                    fig.update_layout(
                        title_font_size=15, title_font_color="#1e3a5f",
                        plot_bgcolor="white", paper_bgcolor="white",
                        margin=dict(t=50, b=30, l=10, r=10),
                        xaxis=dict(showgrid=False, tickfont_size=11),
                        yaxis=dict(gridcolor="#f3f4f6", tickfont_size=11),
                    )
                    st.plotly_chart(fig, use_container_width=True)
                    return
                elif ctype == "pie":
                    fig = px.pie(
                        df, values=y, names=x, title=title,
                        color_discrete_sequence=_CHART_COLOURS,
                        hole=0.38,
                    )
                    fig.update_traces(textposition="outside", textfont_size=12)
                    fig.update_layout(
                        title_font_size=15, title_font_color="#1e3a5f",
                        paper_bgcolor="white",
                        margin=dict(t=50, b=10, l=10, r=10),
                        legend=dict(orientation="h", yanchor="bottom", y=-0.2),
                    )
                    st.plotly_chart(fig, use_container_width=True)
                    return
                else:  # bar
                    fig = px.bar(
                        df, x=x, y=y, title=title,
                        color=x, color_discrete_sequence=_CHART_COLOURS,
                        template="plotly_white",
                        text_auto=".2s",
                    )
                    fig.update_traces(textposition="outside", textfont_size=11)
                    fig.update_layout(
                        title_font_size=15, title_font_color="#1e3a5f",
                        showlegend=False,
                        plot_bgcolor="white", paper_bgcolor="white",
                        margin=dict(t=50, b=30, l=10, r=10),
                        xaxis=dict(showgrid=False, tickfont_size=11),
                        yaxis=dict(gridcolor="#f3f4f6", tickfont_size=11),
                    )
                    st.plotly_chart(fig, use_container_width=True)
                    return
        except Exception as chart_err:  # noqa: BLE001
            st.caption(f"ℹ️ Auto-generated chart (spec mismatch: {chart_err})")
    _detect_and_render_chart(df)


def _detect_and_render_chart(df: pd.DataFrame) -> None:
    if df.empty:
        return

    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    date_cols = [
        c for c in df.columns
        if any(k in c.lower() for k in ("date", "month", "year", "quarter", "week", "day"))
    ]
    categorical_cols = [c for c in df.columns if c not in numeric_cols]

    if len(df) == 1 and len(numeric_cols) == 1:
        label = str(df[categorical_cols[0]].iloc[0]) if categorical_cols else numeric_cols[0]
        value = df[numeric_cols[0]].iloc[0]
        st.metric(label=label, value=f"{value:,.0f}" if isinstance(value, float) else value)
        return

    if date_cols and numeric_cols:
        fig = px.line(
            df, x=date_cols[0], y=numeric_cols, markers=True,
            color_discrete_sequence=["#0f6b8a", "#0d9488", "#f59e0b"],
            template="plotly_white",
        )
        fig.update_layout(
            plot_bgcolor="white", paper_bgcolor="white",
            margin=dict(t=30, b=30, l=10, r=10),
            xaxis=dict(showgrid=False), yaxis=dict(gridcolor="#f3f4f6"),
        )
        st.plotly_chart(fig, use_container_width=True)
        return

    if categorical_cols and numeric_cols:
        fig = px.bar(
            df, x=categorical_cols[0], y=numeric_cols[0],
            color=categorical_cols[0], color_discrete_sequence=_CHART_COLOURS,
            template="plotly_white", text_auto=".2s",
        )
        fig.update_traces(textposition="outside", textfont_size=11)
        fig.update_layout(
            showlegend=False, plot_bgcolor="white", paper_bgcolor="white",
            margin=dict(t=30, b=30, l=10, r=10),
            xaxis=dict(showgrid=False), yaxis=dict(gridcolor="#f3f4f6"),
        )
        st.plotly_chart(fig, use_container_width=True)
        return

    if numeric_cols and len(numeric_cols) > 1:
        st.dataframe(df.describe(), use_container_width=True)

# ---------------------------------------------------------------------------
# Cached health check (Issue 10 — avoid DB probe on every rerun)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=30)
def _check_health() -> dict:
    """Check API health with a 30-second cache to avoid hammering the DB."""
    try:
        resp = httpx.get(f"{API_URL}/health", timeout=5)
        return resp.json()
    except Exception:  # noqa: BLE001
        return {"database": "disconnected"}

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

def _render_sidebar() -> None:
    with st.sidebar:
        st.markdown(
            """
            <div style="padding:1.2rem 0.5rem 0.8rem; text-align:center;">
                <div style="font-size:2rem;">🤖</div>
                <div style="font-size:1.15rem; font-weight:700; color:#f1f5f9; margin-top:0.3rem;">IADS SQL Agent</div>
                <div style="font-size:0.75rem; color:#94a3b8; margin-top:0.2rem;">AI-powered data querying</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.divider()

        # --- Database status ---
        st.markdown('<div style="font-size:0.7rem;font-weight:700;letter-spacing:1px;color:#94a3b8;text-transform:uppercase;margin-bottom:0.5rem;">Database</div>', unsafe_allow_html=True)

        health = _check_health()
        db_connected = health.get("database") == "connected"

        tables: list[str] = st.session_state.db_tables

        if db_connected:
            st.markdown(
                '<div class="sidebar-status-ok"><span class="pulse-dot"></span>&nbsp;<b>Connected</b>&nbsp;— OCI Autonomous DB</div>',
                unsafe_allow_html=True,
            )
            if tables:
                st.markdown('<div style="margin-top:0.7rem;font-size:0.72rem;font-weight:600;color:#94a3b8;letter-spacing:0.5px;text-transform:uppercase;">Tables</div>', unsafe_allow_html=True)
                for t in tables:
                    st.markdown(f'<div style="font-size:0.82rem;color:#cbd5e1;padding:2px 0;">`{t}`</div>', unsafe_allow_html=True)
        else:
            st.markdown(
                '<div class="sidebar-status-err"><span class="pulse-dot-err"></span>&nbsp;<b>Not connected</b></div>',
                unsafe_allow_html=True,
            )
            st.caption("Waiting for OCI connection…")

        st.divider()

        # --- Upload database ---
        st.markdown('<div style="font-size:0.7rem;font-weight:700;letter-spacing:1px;color:#94a3b8;text-transform:uppercase;margin-bottom:0.5rem;">Upload database</div>', unsafe_allow_html=True)
        uploaded = st.file_uploader(
            "Drop a file to query it",
            type=["db", "sqlite", "csv", "xlsx"],
            label_visibility="collapsed",
            help="Supports SQLite (.db), CSV, and Excel files.",
        )
        if uploaded is not None:
            st.session_state.uploaded_db = uploaded

        if st.session_state.uploaded_db is not None:
            f = st.session_state.uploaded_db
            st.success(f"✅ {f.name}")
            st.caption(f"{f.size / 1024:.1f} KB · ready to query")
            if st.button("✕ Remove file", use_container_width=True):
                st.session_state.uploaded_db = None
                st.rerun()
        else:
            st.caption("No file loaded — using OCI database.")

        st.divider()

        # --- Demo mode ---
        st.markdown('<div style="font-size:0.7rem;font-weight:700;letter-spacing:1px;color:#94a3b8;text-transform:uppercase;margin-bottom:0.3rem;">Demo mode</div>', unsafe_allow_html=True)
        st.caption("Use cached results — safe for presentations.")
        st.session_state.demo_mode = st.toggle(
            COPY["demo_toggle"],
            value=st.session_state.demo_mode,
        )

        st.divider()

        # --- Pipeline legend ---
        st.markdown('<div style="font-size:0.7rem;font-weight:700;letter-spacing:1px;color:#94a3b8;text-transform:uppercase;margin-bottom:0.5rem;">Agent pipeline</div>', unsafe_allow_html=True)
        pipeline_stages = [
            ("📚", "RAG retrieval"),
            ("🧠", "SQL generation"),
            ("✅", "Validation"),
            ("⚡", "Execution"),
            ("💡", "Summarisation"),
        ]
        for i, (icon, label) in enumerate(pipeline_stages):
            connector = '<div style="margin-left:0.6rem;border-left:2px solid rgba(255,255,255,0.08);height:6px;"></div>' if i > 0 else ''
            st.markdown(
                f'{connector}<div style="display:flex;align-items:center;gap:0.5rem;padding:3px 0;font-size:0.8rem;color:#cbd5e1;">{icon}&nbsp;{label}</div>',
                unsafe_allow_html=True,
            )

        st.divider()

        # --- Clear conversation ---
        if st.button(COPY["clear_button"], use_container_width=True):
            st.session_state.history = []
            st.session_state.session_id = None
            st.rerun()

        # --- Version badge ---
        st.markdown(
            """
            <div class="version-badge">
                <div class="vb-name">IADS SQL Agent</div>
                <div class="vb-ver">v1.0.0 · Oracle 23ai</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

# ---------------------------------------------------------------------------
# Data summary helper
# ---------------------------------------------------------------------------

def _generate_data_summary(df: pd.DataFrame) -> str:
    """Generate an HTML data summary card for query results."""
    if df.empty:
        return ""

    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    categorical_cols = [c for c in df.columns if c not in numeric_cols]

    stats_html = ""

    # Row count
    stats_html += f"""
        <div class="ds-stat">
            <div class="ds-val">{len(df):,}</div>
            <div class="ds-lbl">Rows</div>
        </div>
    """

    # For numeric columns (max 3), show the total
    for col in numeric_cols[:3]:
        total = df[col].sum()
        if abs(total) >= 1_000_000:
            formatted = f"{total / 1_000_000:,.1f}M"
        elif abs(total) >= 1_000:
            formatted = f"{total / 1_000:,.1f}K"
        elif total == int(total):
            formatted = f"{int(total):,}"
        else:
            formatted = f"{total:,.2f}"

        # Clean the column name for display
        display_name = col.replace("_", " ").title()
        stats_html += f"""
            <div class="ds-stat">
                <div class="ds-val">{formatted}</div>
                <div class="ds-lbl">Σ {display_name}</div>
            </div>
        """

    # Top category (the row with the highest numeric value)
    if categorical_cols and numeric_cols and len(df) > 1:
        top_cat_col = categorical_cols[0]
        try:
            top_idx = df[numeric_cols[0]].idxmax()
            top_val = str(df.iloc[top_idx][top_cat_col])
            if len(top_val) > 18:
                top_val = top_val[:16] + "…"
            display_cat = top_cat_col.replace("_", " ").title()
            stats_html += f"""
                <div class="ds-stat">
                    <div class="ds-val" style="font-size:0.95rem;">{top_val}</div>
                    <div class="ds-lbl">🏆 Top {display_cat}</div>
                </div>
            """
        except Exception:  # noqa: BLE001
            pass

    # Min/Max range for first numeric column
    if numeric_cols and len(df) > 1:
        col = numeric_cols[0]
        mn, mx = df[col].min(), df[col].max()
        if abs(mx) >= 1_000_000:
            mn_fmt, mx_fmt = f"{mn/1_000_000:.1f}M", f"{mx/1_000_000:.1f}M"
        elif abs(mx) >= 1_000:
            mn_fmt, mx_fmt = f"{mn/1_000:.1f}K", f"{mx/1_000:.1f}K"
        else:
            mn_fmt, mx_fmt = f"{mn:,.0f}", f"{mx:,.0f}"
        stats_html += f"""
            <div class="ds-stat">
                <div class="ds-val" style="font-size:0.95rem;">{mn_fmt} – {mx_fmt}</div>
                <div class="ds-lbl">Range</div>
            </div>
        """

    return f"""
        <div class="data-summary-card">
            <div class="ds-title">📊 Data Summary</div>
            <div class="data-summary-stats">{stats_html}</div>
        </div>
    """

# ---------------------------------------------------------------------------
# Response renderer
# ---------------------------------------------------------------------------

def _confidence_bar(confidence: float) -> str:
    pct = int(confidence * 100)
    fill_class = "conf-bar-fill-high" if confidence >= CONFIDENCE_THRESHOLD else "conf-bar-fill-low"
    colour = "#10b981" if confidence >= CONFIDENCE_THRESHOLD else "#f59e0b"
    label = COPY["confidence_ok"] if confidence >= CONFIDENCE_THRESHOLD else "Low confidence"
    return f"""
    <div class="conf-row">
        <div class="conf-label">{label}</div>
        <div class="conf-bar-bg"><div class="{fill_class}" style="width:{pct}%"></div></div>
        <div class="conf-pct" style="color:{colour};">{pct}%</div>
    </div>
    """


def _pipeline_badges(resp: dict) -> str:
    stages = [
        ("📚", "RAG"),
        ("🧠", "SQL Gen"),
        ("✅", "Validated"),
        ("⚡", "Executed"),
        ("💡", "Summarised"),
    ]
    # Mark everything done if we got a real answer
    all_done = bool(resp.get("answer") and not resp.get("error"))
    html = '<div class="pipeline-row">'
    for i, (icon, label) in enumerate(stages):
        cls = "pipeline-step done" if all_done else "pipeline-step"
        html += f'<div class="{cls}">{icon} {label}</div>'
        if i < len(stages) - 1:
            html += '<span class="pipeline-arrow">›</span>'
    html += "</div>"
    return html


def _render_response(resp: dict, key_suffix: str | None = None) -> None:
    if resp.get("error"):
        st.error(f"❌ {resp['error']}")
        return

    confidence = resp.get("confidence", 1.0)

    # -- Resolved question pill (shows when AI rewrote a follow-up) --
    resolved = resp.get("resolved_question")
    original = resp.get("question", "")
    if resolved and resolved.strip().lower() != original.strip().lower():
        st.markdown(
            f'<div style="display:inline-block;background:linear-gradient(90deg,#eff6ff,#e0f2fe);'
            f'border:1px solid #93c5fd;border-radius:20px;padding:0.3rem 0.9rem;'
            f'font-size:0.82rem;color:#1e40af;margin-bottom:0.6rem;">'
            f'🔄 <b>AI interpreted as:</b> {resolved}</div>',
            unsafe_allow_html=True,
        )

    # -- Approximate match banner --
    if resp.get("approximate_match"):
        st.markdown(
            f'<div class="approx-banner">🔍 {COPY["approx_match"]}</div>',
            unsafe_allow_html=True,
        )

    # -- Clarification box --
    if resp.get("clarification"):
        st.markdown(
            f'<div class="clarify-box">💬 <b>Clarification:</b> {resp["clarification"]}</div>',
            unsafe_allow_html=True,
        )

    # -- Answer card --
    if resp.get("answer"):
        card_class = "answer-card" if confidence >= CONFIDENCE_THRESHOLD else "answer-card-warn"
        st.markdown(
            f"""
            <div class="{card_class}">
                <div class="answer-label">✦ Executive Summary</div>
                <div class="answer-text">{resp['answer']}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # -- Important numbers row --
    important_numbers = resp.get("important_numbers") or []
    if important_numbers:
        st.markdown('<div class="section-title">📌 Important Numbers</div>', unsafe_allow_html=True)
        num_cols = st.columns(min(len(important_numbers), 4))
        for i, num in enumerate(important_numbers[:4]):
            with num_cols[i % len(num_cols)]:
                st.markdown(
                    f'<div class="metric-tile"><div class="mt-val" style="font-size:0.95rem;">{num}</div></div>',
                    unsafe_allow_html=True,
                )

    # -- Trends & Anomalies --
    trends = resp.get("trends_anomalies") or []
    if trends:
        st.markdown('<div class="section-title">📈 Trends & Anomalies</div>', unsafe_allow_html=True)
        trend_chips = "".join(
            f'<div class="insight-chip" style="background:linear-gradient(90deg,#7c3aed,#6d28d9);">{t}</div>'
            for t in trends
        )
        st.markdown(f'<div class="insights-strip">{trend_chips}</div>', unsafe_allow_html=True)

    # -- Final Takeaway card --
    takeaway = resp.get("final_takeaway")
    if takeaway:
        st.markdown(
            f'<div style="background:linear-gradient(135deg,#ecfdf5,#d1fae5);border:1.5px solid #6ee7b7;'
            f'border-radius:14px;padding:1rem 1.3rem;margin:0.6rem 0 1rem;'
            f'box-shadow:0 3px 12px rgba(52,211,153,0.1);animation:fadeIn 0.4s ease-out;">'
            f'<div style="font-size:0.68rem;font-weight:700;color:#059669;text-transform:uppercase;'
            f'letter-spacing:1px;margin-bottom:0.3rem;">💡 Bottom Line</div>'
            f'<div style="font-size:1.05rem;font-weight:600;color:#064e3b;line-height:1.5;">{takeaway}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # -- Confidence bar + latency badge --
    latency = resp.get("latency_ms")
    latency_html = ""
    if latency is not None:
        secs = latency / 1000
        latency_html = (
            f'<span style="font-size:0.72rem;color:#6b7280;margin-left:0.5rem;">'
            f'⚡ {secs:.1f}s</span>'
        )
    st.markdown(_confidence_bar(confidence) + latency_html, unsafe_allow_html=True)

    # -- Pipeline breadcrumb --
    st.markdown(_pipeline_badges(resp), unsafe_allow_html=True)

    # -- Data summary card (auto-generated) --
    rows = resp.get("rows", [])
    if rows:
        df_for_summary = pd.DataFrame(rows)
        summary_html = _generate_data_summary(df_for_summary)
        if summary_html:
            st.markdown(summary_html, unsafe_allow_html=True)

    # -- Insights chips --
    insights = resp.get("insights") or []
    if insights:
        st.markdown('<div class="section-title">Key insights</div>', unsafe_allow_html=True)
        chips = "".join(f'<div class="insight-chip">📊 {ins}</div>' for ins in insights)
        st.markdown(f'<div class="insights-strip">{chips}</div>', unsafe_allow_html=True)

    # -- Data tabs --
    if rows:
        df = pd.DataFrame(rows)
        tab1, tab2, tab3 = st.tabs(["📊 Visualization", "📋 Data", "📥 Export"])

        with tab1:
            _render_chart_from_spec(resp.get("chart"), df)

        with tab2:
            numeric_cols = df.select_dtypes(include="number").columns
            c1, c2, c3 = st.columns(3)
            with c1:
                st.markdown(
                    f'<div class="metric-tile"><div class="mt-val">{len(df):,}</div><div class="mt-lbl">Rows returned</div></div>',
                    unsafe_allow_html=True,
                )
            with c2:
                st.markdown(
                    f'<div class="metric-tile"><div class="mt-val">{len(df.columns)}</div><div class="mt-lbl">Columns</div></div>',
                    unsafe_allow_html=True,
                )
            with c3:
                st.markdown(
                    f'<div class="metric-tile"><div class="mt-val">{len(numeric_cols)}</div><div class="mt-lbl">Numeric cols</div></div>',
                    unsafe_allow_html=True,
                )
            st.markdown("<br>", unsafe_allow_html=True)
            st.dataframe(df, use_container_width=True)

        with tab3:
            csv = df.to_csv(index=False)
            st.download_button(
                label="📥 Download as CSV",
                data=csv,
                file_name="query_results.csv",
                mime="text/csv",
                use_container_width=True,
                key=f"download_{key_suffix}" if key_suffix else "download",
            )
            numeric_cols_list = df.select_dtypes(include="number").columns.tolist()
            if numeric_cols_list:
                st.markdown('<div class="section-title" style="margin-top:1rem;">Summary statistics</div>', unsafe_allow_html=True)
                st.dataframe(df[numeric_cols_list].describe(), use_container_width=True)

    # -- Explainability expander --
    with st.expander(COPY["expander_label"]):
        if resp.get("tables_used"):
            st.markdown(
                f'<div style="font-size:0.85rem;margin-bottom:0.5rem;">🗂 <b>Tables used:</b> '
                + ", ".join(f"`{t}`" for t in resp["tables_used"])
                + "</div>",
                unsafe_allow_html=True,
            )
        if resp.get("explanation"):
            st.markdown('<div class="section-title">How the query was built</div>', unsafe_allow_html=True)
            st.markdown(resp["explanation"])
        if resp.get("sql"):
            st.markdown('<div class="section-title">Generated SQL</div>', unsafe_allow_html=True)
            st.code(resp["sql"], language="sql")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    st.set_page_config(
        page_title=COPY["app_name"],
        page_icon="🤖",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
    _init_state()
    _render_sidebar()

    # Welcome screen — shown only when there is no history yet
    if not st.session_state.history:
        # ─── Animated header ───
        st.markdown(
            """
            <div class="iads-header">
                <h1>🤖 IADS SQL Agent</h1>
                <p>Ask anything about the database — in plain English. No SQL required.</p>
                <span class="iads-badge">Multi-stage Agentic AI · RAG · Oracle 23ai · Select AI</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # ─── Summary stats cards ───
        try:
            health_resp = httpx.get(f"{API_URL}/health", timeout=3)
            health_data = health_resp.json()
            db_ok = health_data.get("database") == "connected"
        except Exception:
            db_ok = False

        db_status = "Connected" if db_ok else "Offline"
        db_dot_class = "pulse-dot" if db_ok else "pulse-dot-err"
        table_count = str(len(st.session_state.db_tables)) if st.session_state.db_tables else "—"

        st.markdown(
            f"""
            <div class="summary-grid">
                <div class="summary-card">
                    <div class="card-icon">🗄️</div>
                    <div class="card-value"><span class="{db_dot_class}"></span>&nbsp;{db_status}</div>
                    <div class="card-label">Database</div>
                </div>
                <div class="summary-card">
                    <div class="card-icon">📊</div>
                    <div class="card-value">{table_count}</div>
                    <div class="card-label">Tables Available</div>
                </div>
                <div class="summary-card">
                    <div class="card-icon">🤖</div>
                    <div class="card-value">5-Stage</div>
                    <div class="card-label">Agentic Pipeline</div>
                </div>
                <div class="summary-card">
                    <div class="card-icon">⚡</div>
                    <div class="card-value">Oracle 23ai</div>
                    <div class="card-label">Query Engine</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # ─── How It Works ───
        st.markdown(
            """
            <div class="how-section">
                <div class="how-section-title">How It Works</div>
                <div class="how-steps">
                    <div class="how-step">
                        <div class="step-num">1</div>
                        <div class="step-title">Ask</div>
                        <div class="step-desc">Type your question in natural language — no SQL knowledge needed</div>
                    </div>
                    <div class="how-step">
                        <div class="step-num">2</div>
                        <div class="step-title">Process</div>
                        <div class="step-desc">AI retrieves context via RAG, generates &amp; validates SQL automatically</div>
                    </div>
                    <div class="how-step">
                        <div class="step-num">3</div>
                        <div class="step-title">Visualize</div>
                        <div class="step-desc">Get answers, interactive charts, and data exports instantly</div>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # ─── Feature highlights ───
        st.markdown(
            """
            <div class="how-section-title" style="margin-top:0.5rem;">Capabilities</div>
            <div class="features-grid">
                <div class="feature-card">
                    <div class="feat-icon">🧠</div>
                    <div>
                        <div class="feat-title">Natural Language to SQL</div>
                        <div class="feat-desc">Ask questions in plain English and get accurate SQL queries generated automatically</div>
                    </div>
                </div>
                <div class="feature-card">
                    <div class="feat-icon">📚</div>
                    <div>
                        <div class="feat-title">RAG-Enhanced Accuracy</div>
                        <div class="feat-desc">Retrieval-augmented generation grounds responses in your actual schema &amp; data</div>
                    </div>
                </div>
                <div class="feature-card">
                    <div class="feat-icon">📊</div>
                    <div>
                        <div class="feat-title">Auto Visualizations</div>
                        <div class="feat-desc">Charts are automatically generated based on query results — bar, line, pie &amp; more</div>
                    </div>
                </div>
                <div class="feature-card">
                    <div class="feat-icon">🔒</div>
                    <div>
                        <div class="feat-title">SQL Validation &amp; Safety</div>
                        <div class="feat-desc">All generated SQL is validated and run as read-only to protect your data</div>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # ─── Gradient divider ───
        st.markdown('<div class="gradient-divider"></div>', unsafe_allow_html=True)

        # ─── Example questions ───
        st.markdown('<div class="section-title" style="margin-bottom:0.6rem;">Try an example question</div>', unsafe_allow_html=True)
        examples = [
            "💰 What is the total revenue by region?",
            "🏆 What are the top 5 products by total revenue?",
            "📈 What is the profit margin percentage by region?",
            "📅 What was the monthly revenue in 2024?",
        ]
        cols = st.columns(2)
        for i, ex in enumerate(examples):
            with cols[i % 2]:
                if st.button(ex, use_container_width=True, key=f"example_{i}"):
                    # strip the emoji prefix before sending
                    question_text = ex[2:].strip()
                    st.session_state._example_question = question_text
                    st.rerun()
    else:
        # Compact header when there is already a conversation
        st.markdown(
            '<div style="display:flex;align-items:center;gap:0.6rem;margin-bottom:1rem;">'
            '<span style="font-size:1.5rem;">🤖</span>'
            '<span style="font-size:1.15rem;font-weight:700;color:#1e3a5f;">IADS SQL Agent</span>'
            '</div>',
            unsafe_allow_html=True,
        )

    # Handle example button click — append to history and rerun (avoid duplicate render)
    if getattr(st.session_state, "_example_question", None):
        eq = st.session_state._example_question
        del st.session_state._example_question
        with st.status("🤖 Thinking...", expanded=True) as status:
            status.update(label="📚 Retrieving context & generating SQL...", state="running")
            resp = call_api(eq, st.session_state.session_id)
            status.update(label="✅ Done!", state="complete", expanded=False)
        if resp.get("session_id"):
            st.session_state.session_id = resp["session_id"]
        st.session_state.history.append({"question": eq, "response": resp})
        st.rerun()

    # Render conversation history as chat bubbles
    for idx, entry in enumerate(st.session_state.history):
        with st.chat_message("user"):
            st.markdown(entry["question"])
        with st.chat_message("assistant"):
            _render_response(entry["response"], key_suffix=f"hist_{idx}")

    # Chat input — Streamlit pins this to the bottom automatically
    question = st.chat_input(COPY["chat_placeholder"])
    if question:
        with st.chat_message("user"):
            st.markdown(question)
        with st.chat_message("assistant"):
            with st.status("🤖 Thinking...", expanded=True) as status:
                status.update(label="📚 Retrieving context & generating SQL...", state="running")
                resp = call_api(question, st.session_state.session_id)
                status.update(label="✅ Done!", state="complete", expanded=False)
            if resp.get("session_id"):
                st.session_state.session_id = resp["session_id"]
            st.session_state.history.append({"question": question, "response": resp})
            _render_response(resp, key_suffix="current")


if __name__ == "__main__":
    main()
