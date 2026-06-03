"""Streamlit frontend — calls the FastAPI backend.

Owner: Mehdi
Status: implemented.
"""

from __future__ import annotations

import os

import httpx
import pandas as pd
import streamlit as st

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

API_URL = os.getenv("API_URL", "http://localhost:8000")
API_TIMEOUT_SECONDS = float(os.getenv("API_TIMEOUT_SECONDS", "120"))
HEALTH_TIMEOUT_SECONDS = float(os.getenv("HEALTH_TIMEOUT_SECONDS", "5"))
CONFIDENCE_THRESHOLD = 0.7

# Placeholder tables — replaced by Abdul Qayyum's schema introspector once ready
_PLACEHOLDER_TABLES: list[str] = []

# ---------------------------------------------------------------------------
# Copy strings
# ---------------------------------------------------------------------------

COPY = {
    "app_name": "IADS SQL Agent",
    "app_caption": "AI-powered natural language querying",
    "db_section": "Connection",
    "db_connected": "Backend connected",
    "db_not_connected": "Backend offline",
    "db_waiting": "Waiting for backend connection…",
    "tables_label": "Tables available",
    "demo_section": "Demo mode",
    "demo_caption": "Use cached results instead of live DB — safe for presentations.",
    "demo_toggle": "Use cached data",
    "clear_button": "🗑  Clear conversation",
    "chat_placeholder": "Ask a question about your data…",
    "confidence_ok": "High confidence",
    "confidence_warn": "Low confidence — double-check before acting on this.",
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
        resp = httpx.post(f"{API_URL}/query", json=payload, timeout=API_TIMEOUT_SECONDS)
        resp.raise_for_status()
        return resp.json()
    except httpx.ConnectError:
        return _empty_error_response(COPY["api_unreachable"].format(url=API_URL), session_id)
    except Exception as exc:  # noqa: BLE001
        return _empty_error_response(str(exc), session_id)


def api_is_healthy() -> bool:
    try:
        resp = httpx.get(f"{API_URL}/health", timeout=HEALTH_TIMEOUT_SECONDS)
        resp.raise_for_status()
        return resp.json().get("status") == "ok"
    except Exception:  # noqa: BLE001
        return False

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
# Sidebar
# ---------------------------------------------------------------------------

def _render_sidebar() -> None:
    with st.sidebar:
        st.markdown(f"### 📊 {COPY['app_name']}")
        st.caption(COPY["app_caption"])
        st.divider()

        # --- Database status ---
        st.subheader(COPY["db_section"])

        db_connected = api_is_healthy()
        tables: list[str] = st.session_state.db_tables

        if db_connected:
            st.success(f"🟢 {COPY['db_connected']}")
            st.caption("Live Oracle is used when the database listener accepts connections.")
            if tables:
                st.markdown(f"**{COPY['tables_label']}**")
                for t in tables:
                    st.markdown(f"&nbsp;&nbsp;• `{t}`", unsafe_allow_html=True)
        else:
            st.warning(f"🔴 {COPY['db_not_connected']}")
            st.caption(COPY["db_waiting"])

        st.divider()

        # --- Upload database ---
        st.subheader("📂 Upload database")
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
            st.caption("No file loaded — using the configured backend data source.")

        st.divider()

        # --- Demo mode ---
        # ABDUL QAYYUM: st.session_state.demo_mode is True when this toggle is on.
        # In call_api() (above), check that flag and hit your demo_cache.py
        # endpoint instead of the live /query route when it's enabled.
        st.subheader(COPY["demo_section"])
        st.caption(COPY["demo_caption"])
        st.session_state.demo_mode = st.toggle(
            COPY["demo_toggle"],
            value=st.session_state.demo_mode,
        )

        st.divider()

        # --- Clear conversation ---
        if st.button(COPY["clear_button"], use_container_width=True):
            st.session_state.history = []
            st.session_state.session_id = None
            st.rerun()

# ---------------------------------------------------------------------------
# Response renderer
# ---------------------------------------------------------------------------

def _render_response(resp: dict) -> None:
    if resp.get("error"):
        st.error(resp["error"])
        return

    if resp.get("approximate_match"):
        st.info(COPY["approx_match"])

    confidence = resp.get("confidence", 1.0)
    if confidence >= CONFIDENCE_THRESHOLD:
        st.success(f"✓ {COPY['confidence_ok']} ({confidence:.0%})")
    else:
        st.warning(f"⚠ {COPY['confidence_warn']} ({confidence:.0%})")

    if resp.get("clarification"):
        st.info(f"💡 {resp['clarification']}")

    if resp.get("answer"):
        st.markdown(f"### {resp['answer']}")

    # Business insights (deterministic, from the summariser)
    insights = resp.get("insights") or []
    if insights:
        st.markdown(f"**{COPY['insights_label']}**")
        for ins in insights:
            st.markdown(f"- 📊 {ins}")

    rows = resp.get("rows", [])
    if rows:
        df = pd.DataFrame(rows)
        _render_chart_from_spec(resp.get("chart"), df)
        st.dataframe(df, use_container_width=True)

    with st.expander(COPY["expander_label"]):
        if resp.get("tables_used"):
            st.markdown(f"**{COPY['tables_used_label']}:** {', '.join(resp['tables_used'])}")
        if resp.get("explanation"):
            st.markdown(f"**{COPY['explanation_label']}**")
            st.markdown(resp["explanation"])
        if resp.get("sql"):
            st.markdown(f"**{COPY['sql_label']}**")
            st.code(resp["sql"], language="sql")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    st.set_page_config(
        page_title=COPY["app_name"],
        page_icon="🤖",
        layout="wide",
    )
    _init_state()
    _render_sidebar()

    # Welcome screen — shown only when there is no history yet
    if not st.session_state.history:
        st.markdown(
            """
            <div style="text-align:center; padding: 4rem 1rem 2rem;">
                <h1 style="font-size:2.6rem; font-weight:700; margin-bottom:0.4rem;">
                    IADS SQL Agent
                </h1>
                <p style="font-size:1.1rem; color:grey; margin-bottom:2rem;">
                    Ask anything about the database — in plain English.
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
        cols = st.columns(2)
        for i, ex in enumerate(examples):
            with cols[i % 2]:
                if st.button(ex, use_container_width=True, key=f"example_{i}"):
                    st.session_state._example_question = ex
                    st.rerun()

    # Handle example button click
    if getattr(st.session_state, "_example_question", None):
        eq = st.session_state._example_question
        del st.session_state._example_question
        with st.chat_message("user"):
            st.markdown(eq)
        with st.chat_message("assistant"):
            with st.spinner("Thinking…"):
                resp = call_api(eq, st.session_state.session_id)
            if resp.get("session_id"):
                st.session_state.session_id = resp["session_id"]
            st.session_state.history.append({"question": eq, "response": resp})
            _render_response(resp)

    # Render conversation history as chat bubbles
    for entry in st.session_state.history:
        with st.chat_message("user"):
            st.markdown(entry["question"])
        with st.chat_message("assistant"):
            _render_response(entry["response"])

    # Chat input — Streamlit pins this to the bottom automatically
    question = st.chat_input(COPY["chat_placeholder"])
    if question:
        with st.chat_message("user"):
            st.markdown(question)
        with st.chat_message("assistant"):
            with st.spinner("Thinking…"):
                resp = call_api(question, st.session_state.session_id)
            if resp.get("session_id"):
                st.session_state.session_id = resp["session_id"]
            st.session_state.history.append({"question": question, "response": resp})
            _render_response(resp)


if __name__ == "__main__":
    main()
