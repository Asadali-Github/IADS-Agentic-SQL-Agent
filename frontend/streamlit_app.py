"""Streamlit frontend - calls the FastAPI backend.

Owner: Mehdi
Status: implemented.
"""

from __future__ import annotations

import os
import time

import httpx
import pandas as pd
import streamlit as st

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

API_URL = os.getenv("API_URL", "http://localhost:8000")
CONFIDENCE_THRESHOLD = 0.7

# Placeholder tables - replaced by Abdul Qayyum's schema introspector once ready
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
    "demo_caption": "Use cached results instead of live DB - safe for presentations.",
    "demo_toggle": "Use cached data",
    "clear_button": "Clear conversation",
    "chat_placeholder": "Ask a question about your data…",
    "confidence_ok": "High confidence",
    "confidence_warn": "Low confidence - double-check before acting on this.",
    "approx_match": "No exact match found. Showing the closest results instead.",
    "expander_label": "How did the AI calculate this?",
    "insights_label": "Key insights",
    "clarify_label": "I need a quick clarification",
    "tables_used_label": "Tables used",
    "explanation_label": "Plain-English breakdown",
    "sql_label": "Generated SQL",
    "api_unreachable": "Could not reach the API at {url}. Make sure the backend is running.",
}

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

def _init_state() -> None:
    defaults = {
        "session_id": None,
        "history": [],          # list of {"question": str, "response": dict}
        "demo_mode": False,
        "db_tables": _PLACEHOLDER_TABLES,
        "uploaded_db": None,    # UploadedFile | None
        "page": "chat",         # active navigation tab
        "show_description": False,  # show AI answer text + insights
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
        "tables_used": [],
        "confidence": 0.0,
        "approximate_match": False,
        "error": msg,
        "session_id": session_id,
    }


def call_api(question: str, session_id: str | None) -> dict:
    payload = {"question": question, "session_id": session_id}
    try:
        resp = httpx.post(f"{API_URL}/query", json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except httpx.ConnectError:
        return _empty_error_response(COPY["api_unreachable"].format(url=API_URL), session_id)
    except Exception as exc:  # noqa: BLE001
        return _empty_error_response(str(exc), session_id)

# ---------------------------------------------------------------------------
# Chart auto-detection
# ---------------------------------------------------------------------------

def _render_chart_from_spec(spec: dict | None, df: pd.DataFrame) -> None:
    """Render the summariser's recommended chart; fall back to auto-detection."""
    if df.empty:
        return
    if spec and spec.get("type") and spec["type"] != "none":
        x, y, ctype = spec.get("x"), spec.get("y"), spec["type"]
        try:
            if x in df.columns and y in df.columns:
                if ctype == "line":
                    st.line_chart(df.set_index(x)[y]); return
                # Streamlit has no native pie; a bar reads the same comparison.
                st.bar_chart(df.set_index(x)[y]); return
        except Exception:  # noqa: BLE001
            pass
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

    # Single KPI
    if len(df) == 1 and len(numeric_cols) == 1:
        label = str(df[categorical_cols[0]].iloc[0]) if categorical_cols else numeric_cols[0]
        value = df[numeric_cols[0]].iloc[0]
        st.metric(label=label, value=f"{value:,.0f}" if isinstance(value, float) else value)
        return

    # Time series → line chart
    if date_cols and numeric_cols:
        st.line_chart(df.set_index(date_cols[0])[numeric_cols])
        return

    # Categorical + numeric → bar chart
    if categorical_cols and numeric_cols:
        st.bar_chart(df.set_index(categorical_cols[0])[numeric_cols])
        return

# ---------------------------------------------------------------------------
# CSS - Enterprise Light (white / blue)
# ---------------------------------------------------------------------------

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

/* ============================================================
   ALWAYS-ON — structural / layout (no colours)
   ============================================================ */

html, body, [class*="css"] { font-family: 'Inter', sans-serif !important; }
.main .block-container { padding-top: 1.25rem !important; }

/* Sidebar — no scroll */
section[data-testid="stSidebar"] > div:first-child {
    overflow-y: hidden !important;
    height: 100vh;
}

/* Sidebar brand */
.sb-brand-title {
    font-size: 1.05rem; font-weight: 800; line-height: 1.2;
}
.sb-brand-sub {
    font-size: 0.65rem; letter-spacing: 0.5px; text-transform: uppercase;
}
[data-testid="stSidebarContent"] { padding: 0 !important; }
section[data-testid="stSidebar"] .block-container {
    padding: 0.85rem 1rem 0.75rem !important;
}
section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap: 0.25rem !important; }
section[data-testid="stSidebar"] hr { margin: 0.9rem 0 !important; }
section[data-testid="stSidebar"] .stCaption p { font-size: 0.70rem !important; }
section[data-testid="stSidebar"] label { font-size: 0.82rem !important; }

/* Nav button — structure only */
.nav-btn .stButton > button,
.nav-btn-active .stButton > button {
    border-left: 3px solid transparent !important;
    border-radius: 0 8px 8px 0 !important;
    border-top: none !important;
    border-right: none !important;
    border-bottom: none !important;
    text-align: left !important;
    padding: 0.42rem 0.75rem !important;
    font-size: 0.875rem !important;
    font-weight: 500 !important;
    transition: all 0.14s !important;
    width: 100% !important;
    min-height: 0 !important;
    box-shadow: none !important;
}
.nav-btn-active .stButton > button {
    border-left-color: #2563EB !important;
    font-weight: 600 !important;
}

/* Sidebar util buttons */
section[data-testid="stSidebar"] .stButton > button {
    border-radius: 8px !important;
    font-size: 0.82rem !important;
    min-height: 0 !important;
    padding: 0.38rem 0.7rem !important;
}

/* Example chips — structure */
.example-chips .stButton > button {
    border-radius: 12px !important;
    font-size: 0.875rem !important;
    text-align: left !important;
    padding: 0.7rem 1rem !important;
    transition: all 0.18s ease !important;
    min-height: 58px !important;
}
.example-chips .stButton > button:hover {
    transform: translateY(-1px) !important;
}

/* Chat — user RIGHT bubble, assistant LEFT */
.user-bubble {
    background: #2563EB;
    color: #FFFFFF !important;
    border-radius: 18px 4px 18px 18px;
    padding: 0.65rem 1rem;
    display: inline-block;
    max-width: 100%;
    word-wrap: break-word;
    box-shadow: 0 2px 8px rgba(37,99,235,0.3);
    font-size: 0.97rem;
}
.user-bubble p, .user-bubble span { color: #FFFFFF !important; }
.user-row {
    display: flex;
    justify-content: flex-end;
    padding: 0.2rem 0;
}
.ai-row {
    padding: 0.2rem 0;
}

/* Badges — structure */
.badge-ok, .badge-warn {
    display: inline-flex; align-items: center; gap: 5px;
    border-radius: 20px; padding: 3px 12px;
    font-size: 0.77rem; font-weight: 600; margin-bottom: 0.5rem;
}

/* DB status pills — structure */
.db-pill {
    display: inline-block;
    border-radius: 20px; padding: 4px 12px;
    font-size: 0.72rem; font-weight: 600;
    margin-bottom: 0.25rem;
}

/* Answer card / insight row — structure */
.answer-card {
    border-left: 4px solid #2563EB;
    border-radius: 0 12px 12px 0;
    padding: 0.9rem 1.15rem; margin: 0.4rem 0;
    font-size: 1.02rem; font-weight: 500;
    box-shadow: 0 1px 4px rgba(0,0,0,0.05);
}
.insight-row {
    border-left: 3px solid #EAB308;
    border-radius: 0 8px 8px 0;
    padding: 0.35rem 0.85rem; margin: 0.2rem 0;
    font-size: 0.87rem;
}

/* Expander / dataframe */
details summary { font-weight: 600 !important; font-size: 0.875rem !important; }
details { border-radius: 10px !important; }
[data-testid="stDataFrame"] { border-radius: 10px; overflow: hidden; }

/* Metrics */
[data-testid="metric-container"] {
    border-radius: 10px; padding: 0.75rem 1rem !important;
}

/* Chat input */
[data-testid="stChatInput"] > div {
    border-radius: 14px !important;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06) !important;
}
[data-testid="stChatInput"] > div:focus-within {
    border-color: #2563EB !important;
    box-shadow: 0 0 0 3px rgba(37,99,235,0.12) !important;
}
/* Send button — always blue, borderless */
[data-testid="stChatInputSubmitButton"] button {
    background: #2563EB !important;
    color: #FFFFFF !important;
    border-radius: 10px !important;
    border: none !important;
    outline: none !important;
    box-shadow: none !important;
}
[data-testid="stChatInputSubmitButton"] button:hover {
    background: #1D4ED8 !important;
    box-shadow: none !important;
}
[data-testid="stChatInputSubmitButton"] button:focus {
    outline: none !important;
    box-shadow: none !important;
}

/* Animation keyframes */
@keyframes thinking-pulse {
    0%, 100% { opacity: 0.3; transform: scale(0.8); }
    50%       { opacity: 1;   transform: scale(1.1); }
}
@keyframes shimmer-bar {
    0%   { background-position: -300% 0; }
    100% { background-position:  300% 0; }
}

/* Scrollbar */
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-thumb { border-radius: 4px; }

/* ============================================================
   LIGHT MODE
   ============================================================ */
@media (prefers-color-scheme: light) {
    .main { background: #F8FAFC !important; }

    section[data-testid="stSidebar"] {
        background: #FFFFFF !important;
        border-right: 1.5px solid #E2E8F0;
        box-shadow: 2px 0 8px rgba(0,0,0,0.03);
    }
    section[data-testid="stSidebar"] hr { border-color: #E2E8F0 !important; }
    section[data-testid="stSidebar"] * { color: #0F172A !important; }
    section[data-testid="stSidebar"] .stCaption p {
        color: #94A3B8 !important; opacity: 1 !important;
    }

    /* Brand */
    .sb-brand-sub { opacity: 0.5; }

    /* Nav buttons */
    .nav-btn .stButton > button {
        background: transparent !important; color: #475569 !important;
    }
    .nav-btn .stButton > button:hover {
        background: #EFF6FF !important; color: #1D4ED8 !important;
        border-left-color: #93C5FD !important;
    }
    .nav-btn-active .stButton > button {
        background: #EFF6FF !important; color: #1D4ED8 !important;
    }

    /* Example chips */
    .example-chips .stButton > button {
        background: #FFFFFF !important; border: 1.5px solid #E2E8F0 !important;
        color: #1D4ED8 !important; box-shadow: 0 1px 4px rgba(0,0,0,0.05) !important;
    }
    .example-chips .stButton > button:hover {
        border-color: #93C5FD !important; background: #EFF6FF !important;
        box-shadow: 0 4px 14px rgba(37,99,235,0.12) !important;
    }

    /* AI bubble */
    [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"])
        [data-testid="stChatMessageContent"] {
        background: #FFFFFF !important; border: 1px solid #E2E8F0 !important;
        box-shadow: 0 1px 4px rgba(0,0,0,0.06) !important;
    }

    /* Badges */
    .badge-ok  { background: #DCFCE7; color: #166534; border: 1px solid #86EFAC; }
    .badge-warn{ background: #FEF9C3; color: #854D0E; border: 1px solid #FDE047; }

    /* DB status pills */
    .db-pill-ok  { background: #DCFCE7; color: #166534; border: 1px solid #86EFAC; }
    .db-pill-err { background: #FEF2F2; color: #991B1B; border: 1px solid #FECACA; }

    /* Answer card / insight */
    .answer-card { background: #F0F9FF; color: #0F172A; }
    .insight-row { background: #FEFCE8; color: #713F12; }

    /* Thinking animation */
    .thinking-box {
        background: #EFF6FF;
        border: 1px solid #BFDBFE;
    }
    .thinking-text { color: #3B82F6; }
    .shimmer-bar {
        background: linear-gradient(90deg,#BFDBFE 25%,#93C5FD 50%,#BFDBFE 75%);
    }

    /* Expander */
    details summary { color: #2563EB !important; }
    details { border: 1px solid #E2E8F0 !important; }

    /* Metrics */
    [data-testid="metric-container"] {
        background: #EFF6FF; border: 1px solid #BFDBFE;
    }

    /* Chat input */
    [data-testid="stChatInput"] > div {
        border: 2px solid #E2E8F0 !important; background: #FFFFFF !important;
    }

    /* Scrollbar */
    ::-webkit-scrollbar-track { background: #F8FAFC; }
    ::-webkit-scrollbar-thumb { background: #CBD5E1; }
    ::-webkit-scrollbar-thumb:hover { background: #94A3B8; }
}

/* ============================================================
   DARK MODE  — only override our custom elements; let Streamlit
   handle the rest natively.
   ============================================================ */
@media (prefers-color-scheme: dark) {
    /* Nav buttons */
    .nav-btn .stButton > button { background: transparent !important; }
    .nav-btn .stButton > button:hover {
        background: rgba(37,99,235,0.18) !important;
        color: #93C5FD !important;
        border-left-color: #3B82F6 !important;
    }
    .nav-btn-active .stButton > button {
        background: rgba(37,99,235,0.22) !important;
        color: #60A5FA !important;
    }

    /* Brand */
    .sb-brand-sub { opacity: 0.5; }

    /* Example chips */
    .example-chips .stButton > button {
        border: 1.5px solid rgba(255,255,255,0.12) !important;
        color: #60A5FA !important;
    }
    .example-chips .stButton > button:hover {
        background: rgba(37,99,235,0.2) !important;
        border-color: #3B82F6 !important;
    }

    /* AI bubble */
    [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"])
        [data-testid="stChatMessageContent"] {
        border: 1px solid rgba(255,255,255,0.1) !important;
    }

    /* Badges */
    .badge-ok  { background: rgba(22,163,74,0.2);  color: #86EFAC; border: 1px solid rgba(134,239,172,0.3); }
    .badge-warn{ background: rgba(234,179,8,0.2);   color: #FDE047; border: 1px solid rgba(253,224,71,0.3); }

    /* DB status pills */
    .db-pill-ok  { background: rgba(22,163,74,0.2);  color: #86EFAC; border: 1px solid rgba(134,239,172,0.3); }
    .db-pill-err { background: rgba(239,68,68,0.2);  color: #FCA5A5; border: 1px solid rgba(252,165,165,0.3); }

    /* Answer card / insight */
    .answer-card { background: rgba(37,99,235,0.12); color: #E2E8F0; border-left-color: #3B82F6; }
    .insight-row { background: rgba(234,179,8,0.12); color: #FEF08A; border-left-color: #EAB308; }

    /* Thinking animation */
    .thinking-box {
        background: rgba(37,99,235,0.15);
        border: 1px solid rgba(59,130,246,0.35);
    }
    .thinking-text { color: #93C5FD; }
    .shimmer-bar {
        background: linear-gradient(90deg,rgba(59,130,246,0.3) 25%,rgba(96,165,250,0.5) 50%,rgba(59,130,246,0.3) 75%);
    }

    /* Expander */
    details summary { color: #60A5FA !important; }
    details { border: 1px solid rgba(255,255,255,0.1) !important; }

    /* Metrics */
    [data-testid="metric-container"] {
        background: rgba(37,99,235,0.15); border: 1px solid rgba(37,99,235,0.35);
    }

    /* Chat input */
    [data-testid="stChatInput"] > div {
        border: 2px solid rgba(255,255,255,0.15) !important;
    }

    /* Scrollbar */
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.2); }
    ::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.35); }
}
</style>
"""

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

def _nav_btn(label: str, page_key: str) -> None:
    """Render a sidebar navigation button that sets the active page."""
    css = "nav-btn-active" if st.session_state.get("page") == page_key else "nav-btn"
    st.markdown(f'<div class="{css}">', unsafe_allow_html=True)
    if st.button(label, use_container_width=True, key=f"nav_{page_key}"):
        st.session_state.page = page_key
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)


@st.cache_data(ttl=10)
def _check_api_health() -> bool:
    """Return True if the FastAPI backend is reachable. Cached for 10 s."""
    try:
        r = httpx.get(f"{API_URL}/health", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def _render_sidebar() -> None:
    with st.sidebar:
        # -- Brand ---------------------------------------------------------
        st.markdown(
            """
            <div style="display:flex;align-items:center;gap:0.6rem;
                        padding:0.5rem 0 0.3rem;">
              <svg width="34" height="34" viewBox="0 0 34 34" fill="none">
                <rect width="34" height="34" rx="9" fill="#2563EB"/>
                <ellipse cx="17" cy="11" rx="8" ry="3" fill="white" fill-opacity="0.95"/>
                <rect x="9" y="11" width="16" height="10" fill="white" fill-opacity="0.7"/>
                <ellipse cx="17" cy="21" rx="8" ry="3" fill="white" fill-opacity="0.95"/>
                <path d="M22 4 L18 13 L21 13 L16 28 L26 15 L23 15 Z" fill="#FCD34D"/>
              </svg>
              <div>
                <div class="sb-brand-title">IADS SQL Agent</div>
                <div class="sb-brand-sub">AI &middot; SQL &middot; Analytics</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.divider()

        # -- Navigation ----------------------------------------------------
        _nav_btn("💬  Chat", "chat")
        _nav_btn("📊  Schema Browser", "schema")
        _nav_btn("📜  History", "history")
        _nav_btn("⚙️  Settings", "settings")

        st.markdown("<div style='margin-top:1.5rem;'></div>", unsafe_allow_html=True)
        st.divider()

        # -- Database status -----------------------------------------------
        db_connected = _check_api_health()
        if db_connected:
            st.markdown('<span class="db-pill db-pill-ok">Connected</span>', unsafe_allow_html=True)
            st.caption("OCI Autonomous DB")
        else:
            st.markdown('<span class="db-pill db-pill-err">Not connected</span>', unsafe_allow_html=True)
            st.caption(COPY["db_waiting"])

        st.divider()

        # -- Demo mode toggle ----------------------------------------------
        st.session_state.demo_mode = st.toggle(
            "🎬  Demo mode",
            value=st.session_state.demo_mode,
            help=COPY["demo_caption"],
        )

        st.divider()

        # -- Clear chat ----------------------------------------------------
        if st.button("🗑  " + COPY["clear_button"], use_container_width=True):
            st.session_state.history = []
            st.session_state.session_id = None
            st.rerun()

        # -- Footer --------------------------------------------------------
        st.markdown(
            '<div style="text-align:center;margin-top:0.5rem;">'
            '<p style="font-size:0.62rem;color:#CBD5E1;margin:0;">'
            "IADS · Hackathon 2025 · v0.1"
            "</p></div>",
            unsafe_allow_html=True,
        )

# ---------------------------------------------------------------------------
# Thinking animation
# ---------------------------------------------------------------------------

def _show_thinking():
    """Animated placeholder while the backend processes the request."""
    slot = st.empty()
    timer_id = f"tk{int(time.time() * 1000) % 1_000_000}"
    slot.markdown(
        f"""
        <div class="thinking-box" style="border-radius:12px;padding:0.9rem 1.1rem;margin:0.2rem 0;">
          <div style="display:flex;gap:5px;align-items:center;margin-bottom:8px;">
            <span style="width:8px;height:8px;background:#2563EB;border-radius:50%;
                         display:inline-block;
                         animation:thinking-pulse 1s infinite;"></span>
            <span style="width:8px;height:8px;background:#2563EB;border-radius:50%;
                         display:inline-block;
                         animation:thinking-pulse 1s 0.2s infinite;"></span>
            <span style="width:8px;height:8px;background:#2563EB;border-radius:50%;
                         display:inline-block;
                         animation:thinking-pulse 1s 0.4s infinite;"></span>
            <span class="thinking-text" style="font-size:0.77rem;margin-left:6px;font-weight:500;">
              Analysing your question… <span id="{timer_id}">0.0s</span>
            </span>
          </div>
          <div class="shimmer-bar" style="height:9px;width:72%;
                      background-size:300% 100%;animation:shimmer-bar 1.6s infinite;
                      border-radius:5px;margin-bottom:5px;"></div>
          <div class="shimmer-bar" style="height:9px;width:48%;
                      background-size:300% 100%;animation:shimmer-bar 1.6s 0.4s infinite;
                      border-radius:5px;"></div>
        </div>
        <script>
          (function(){{
            var s=Date.now();
            var el=document.getElementById('{timer_id}');
            var iv=setInterval(function(){{
              if(!el||!document.contains(el)){{clearInterval(iv);return;}}
              el.textContent=((Date.now()-s)/1000).toFixed(1)+'s';
            }},100);
          }})();
        </script>
        """,
        unsafe_allow_html=True,
    )
    return slot

# ---------------------------------------------------------------------------
# Response renderer
# ---------------------------------------------------------------------------

def _render_response(resp: dict) -> None:
    if resp.get("error"):
        st.error(resp["error"])
        return

    if resp.get("approximate_match"):
        st.info(COPY['approx_match'])

    confidence = resp.get("confidence", 1.0)
    if confidence >= CONFIDENCE_THRESHOLD:
        st.markdown(
            f'<span class="badge-ok">{COPY["confidence_ok"]} &nbsp;{confidence:.0%}</span>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<span class="badge-warn">{COPY["confidence_warn"]} &nbsp;{confidence:.0%}</span>',
            unsafe_allow_html=True,
        )

    if resp.get("clarification"):
        st.info(resp['clarification'])

    if st.session_state.get("show_description"):
        if resp.get("answer"):
            st.markdown(
                f'<div class="answer-card">{resp["answer"]}</div>',
                unsafe_allow_html=True,
            )
        if resp.get("explanation"):
            for line in resp["explanation"].splitlines():
                line = line.strip()
                if line:
                    st.markdown(f'<div class="insight-row">{line}</div>', unsafe_allow_html=True)

    rows = resp.get("rows", [])
    if rows:
        df = pd.DataFrame(rows)
        _render_chart_from_spec(resp.get("chart"), df)
        st.dataframe(df, use_container_width=True)

    with st.expander(COPY["expander_label"]):
        if resp.get("tables_used"):
            st.markdown(
                f"**{COPY['tables_used_label']}:** `{'`, `'.join(resp['tables_used'])}`"
            )
        if resp.get("explanation"):
            st.markdown(f"**{COPY['explanation_label']}**")
            st.markdown(resp["explanation"])
        if resp.get("sql"):
            st.markdown(f"**{COPY['sql_label']}**")
            st.code(resp["sql"], language="sql")

# ---------------------------------------------------------------------------
# Extra pages
# ---------------------------------------------------------------------------

def _render_schema_page() -> None:
    st.markdown("## 📊 Database Schema")
    st.caption("Live schema introspection - connect to OCI Autonomous DB to populate.")
    tables = st.session_state.db_tables
    if not tables:
        st.info(
            "🔌 No database connected. Schema will appear here once the OCI connection is live."
        )
        return
    for table in tables:
        with st.expander(f"📋  `{table}`"):
            st.caption("Column details available once the schema retriever is wired up.")


def _render_history_page() -> None:
    st.markdown("## 📜 Query History")
    history = st.session_state.history
    if not history:
        st.info("No queries yet. Go to **Chat** and ask a question to see history here.")
        return
    for i, entry in enumerate(reversed(history), 1):
        q = entry["question"]
        label = f"**{i}.** {q[:70]}{'…' if len(q) > 70 else ''}"
        with st.expander(label):
            st.markdown(f"**Question:** {q}")
            resp = entry["response"]
            if resp.get("answer"):
                st.markdown(f"**Answer:** {resp['answer']}")
            if resp.get("sql"):
                st.code(resp["sql"], language="sql")
    if st.button("🗑  Clear all history", type="secondary"):
        st.session_state.history = []
        st.session_state.session_id = None
        st.rerun()


def _render_settings_page() -> None:
    st.markdown("## ⚙️ Settings")

    with st.expander("Response Display", expanded=True):
        toggled = st.toggle(
            "Show answer description",
            value=st.session_state.get("show_description", False),
            help="When enabled, the AI's written explanation and key insights appear above the table and chart. Off by default — only the table and chart are shown.",
        )
        st.session_state["show_description"] = toggled
        if toggled:
            st.info("Answer descriptions are visible in the chat.")
        else:
            st.caption("Only the table and chart are shown in the chat.")

    with st.expander("�🔗 API Connection", expanded=True):
        st.text_input(
            "Backend URL", value=API_URL, disabled=True,
            help="Set via the API_URL environment variable. Restart the app after changing it.",
        )

    with st.expander("🎬 Demo Mode", expanded=False):
        st.session_state.demo_mode = st.toggle(
            "Use cached responses",
            value=st.session_state.demo_mode,
            help=COPY["demo_caption"],
        )
        if st.session_state.demo_mode:
            st.success("Demo mode active - live DB queries are bypassed.")

    with st.expander("📂 Upload a Database", expanded=False):
        uploaded = st.file_uploader(
            "Drop a SQLite / CSV / Excel file to query locally",
            type=["db", "sqlite", "csv", "xlsx"],
            label_visibility="collapsed",
        )
        if uploaded:
            st.session_state.uploaded_db = uploaded
            st.success(f"✅ {uploaded.name}  ({uploaded.size / 1024:.1f} KB)")
        elif st.session_state.uploaded_db:
            f = st.session_state.uploaded_db
            st.success(f"✅ {f.name}")
            if st.button("✕ Remove file"):
                st.session_state.uploaded_db = None
                st.rerun()
        else:
            st.caption("No file loaded - using the OCI Autonomous Database.")

    with st.expander("🎛️ Agent Behaviour", expanded=False):
        st.slider(
            "Confidence threshold", 0.0, 1.0, CONFIDENCE_THRESHOLD, 0.05,
            disabled=True,
            help="Modify CONFIDENCE_THRESHOLD in the source to change this.",
        )
        st.number_input("Max retries", value=3, disabled=True)
        st.number_input("Query timeout (s)", value=15, disabled=True)

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    st.set_page_config(
        page_title=COPY["app_name"],
        page_icon=None,
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _init_state()
    st.markdown(_CSS, unsafe_allow_html=True)
    _render_sidebar()

    page = st.session_state.get("page", "chat")

    if page == "schema":
        _render_schema_page()
        return
    if page == "history":
        _render_history_page()
        return
    if page == "settings":
        _render_settings_page()
        return

    # -- Chat page ---------------------------------------------------------
    # Snapshot history BEFORE handling any new input so the loop below
    # never renders an entry that is also rendered inline this same run.
    history_snapshot = list(st.session_state.history)

    if not history_snapshot and not getattr(st.session_state, "_example_question", None):
        st.markdown(
            """
            <div style="text-align:center;padding:3.5rem 1rem 2.5rem;">
              <h1 style="font-size:2.2rem;font-weight:800;
                         background:linear-gradient(135deg,#1D4ED8,#7C3AED);
                         -webkit-background-clip:text;-webkit-text-fill-color:transparent;
                         background-clip:text;margin-bottom:0.5rem;">
                IADS SQL Agent
              </h1>
              <p style="font-size:1.05rem;color:#64748B;max-width:480px;margin:0 auto 2.5rem;">
                Ask anything about your database in plain English.
              </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        examples = [
            "What is the total revenue by region?",
            "What are the top 5 products by total revenue?",
            "What is the profit margin percentage by region?",
            "What was the monthly revenue in 2024?",
        ]
        st.markdown('<div class="example-chips">', unsafe_allow_html=True)
        cols = st.columns(2)
        for i, ex in enumerate(examples):
            with cols[i % 2]:
                if st.button(ex, use_container_width=True, key=f"example_{i}"):
                    st.session_state._example_question = ex
                    st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    # Render previous conversation history (snapshot only — excludes anything added this run)
    for entry in history_snapshot:
        st.markdown(f'<div class="user-row"><div class="user-bubble">{entry["question"]}</div></div>', unsafe_allow_html=True)
        with st.container():
            _render_response(entry["response"])

    # Handle example button click (renders inline once, then adds to history)
    if getattr(st.session_state, "_example_question", None):
        eq = st.session_state._example_question
        del st.session_state._example_question
        st.markdown(f'<div class="user-row"><div class="user-bubble">{eq}</div></div>', unsafe_allow_html=True)
        with st.container():
            slot = _show_thinking()
            t0 = time.time()
            resp = call_api(eq, st.session_state.session_id)
            elapsed = time.time() - t0
            slot.empty()
            if resp.get("session_id"):
                st.session_state.session_id = resp["session_id"]
            st.session_state.history.append({"question": eq, "response": resp})
            st.caption(f"Answered in {elapsed:.1f}s")
            _render_response(resp)

    # Chat input - Streamlit pins this to the bottom automatically
    question = st.chat_input(COPY["chat_placeholder"])
    if question:
        st.markdown(f'<div class="user-row"><div class="user-bubble">{question}</div></div>', unsafe_allow_html=True)
        with st.container():
            slot = _show_thinking()
            t0 = time.time()
            resp = call_api(question, st.session_state.session_id)
            elapsed = time.time() - t0
            slot.empty()
            if resp.get("session_id"):
                st.session_state.session_id = resp["session_id"]
            st.session_state.history.append({"question": question, "response": resp})
            st.caption(f"Answered in {elapsed:.1f}s")
            _render_response(resp)


if __name__ == "__main__":
    main()
