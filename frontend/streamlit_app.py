"""Streamlit chatbot frontend for the FastAPI SQL agent backend."""

from __future__ import annotations

import os

import httpx
import pandas as pd
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000")
API_TIMEOUT_SECONDS = float(os.getenv("API_TIMEOUT_SECONDS", "120"))
HEALTH_TIMEOUT_SECONDS = float(os.getenv("HEALTH_TIMEOUT_SECONDS", "5"))
CONFIDENCE_THRESHOLD = 0.7

_PLACEHOLDER_TABLES: list[str] = []

COPY = {
    "app_name": "IADS SQL Agent",
    "app_caption": "AI-powered natural language querying",
    "db_section": "Connection",
    "db_connected": "Backend connected",
    "db_not_connected": "Backend offline",
    "db_waiting": "Waiting for backend connection...",
    "tables_label": "Tables available",
    "demo_section": "Demo mode",
    "demo_caption": "Use cached results instead of live DB; safe for presentations.",
    "demo_toggle": "Use cached data",
    "clear_button": "Clear conversation",
    "chat_placeholder": "Ask a question about your data...",
    "confidence_ok": "High confidence",
    "confidence_warn": "Low confidence; double-check before acting on this.",
    "approx_match": "No exact match found. Showing the closest results instead.",
    "expander_label": "How did the AI calculate this?",
    "insights_label": "Key insights",
    "tables_used_label": "Tables used",
    "explanation_label": "Plain-English breakdown",
    "sql_label": "Generated SQL",
    "api_unreachable": "Could not reach the API at {url}. Make sure the backend is running.",
}


def _init_state() -> None:
    defaults = {
        "session_id": None,
        "history": [],
        "demo_mode": False,
        "db_tables": _PLACEHOLDER_TABLES,
        "uploaded_db": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _empty_error_response(message: str, session_id: str | None) -> dict:
    return {
        "answer": "",
        "rows": [],
        "sql": "",
        "explanation": "",
        "tables_used": [],
        "confidence": 0.0,
        "approximate_match": False,
        "error": message,
        "session_id": session_id,
    }


def call_api(question: str, session_id: str | None) -> dict:
    payload = {
        "question": question,
        "session_id": session_id,
        "demo_mode": st.session_state.demo_mode,
    }
    try:
        response = httpx.post(f"{API_URL}/query", json=payload, timeout=API_TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.json()
    except httpx.ConnectError:
        return _empty_error_response(COPY["api_unreachable"].format(url=API_URL), session_id)
    except Exception as exc:
        return _empty_error_response(str(exc), session_id)


def api_is_healthy() -> bool:
    try:
        response = httpx.get(f"{API_URL}/health", timeout=HEALTH_TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.json().get("status") == "ok"
    except Exception:
        return False


def _render_chart_from_spec(spec: dict | None, df: pd.DataFrame) -> None:
    """Render the backend's recommended chart, or fall back to simple detection."""
    if df.empty:
        return

    if spec and spec.get("type") and spec["type"] != "none":
        x_axis = spec.get("x")
        y_axis = spec.get("y")
        chart_type = spec["type"]
        try:
            if x_axis in df.columns and y_axis in df.columns:
                if chart_type == "line":
                    st.line_chart(df.set_index(x_axis)[y_axis])
                    return
                st.bar_chart(df.set_index(x_axis)[y_axis])
                return
        except Exception:
            pass

    _detect_and_render_chart(df)


def _detect_and_render_chart(df: pd.DataFrame) -> None:
    if df.empty:
        return

    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    date_cols = [
        column
        for column in df.columns
        if any(
            token in column.lower()
            for token in ("date", "month", "year", "quarter", "week", "day")
        )
    ]
    categorical_cols = [column for column in df.columns if column not in numeric_cols]

    if len(df) == 1 and len(numeric_cols) == 1:
        label = str(df[categorical_cols[0]].iloc[0]) if categorical_cols else numeric_cols[0]
        value = df[numeric_cols[0]].iloc[0]
        st.metric(label=label, value=f"{value:,.0f}" if isinstance(value, float) else value)
        return

    if date_cols and numeric_cols:
        st.line_chart(df.set_index(date_cols[0])[numeric_cols])
        return

    if categorical_cols and numeric_cols:
        st.bar_chart(df.set_index(categorical_cols[0])[numeric_cols])


def _render_sidebar() -> None:
    with st.sidebar:
        st.markdown(f"### {COPY['app_name']}")
        st.caption(COPY["app_caption"])
        st.divider()

        st.subheader(COPY["db_section"])
        db_connected = api_is_healthy()
        tables: list[str] = st.session_state.db_tables

        if db_connected:
            st.success(COPY["db_connected"])
            st.caption("Live Oracle is used when the database listener accepts connections.")
            if tables:
                st.markdown(f"**{COPY['tables_label']}**")
                for table in tables:
                    st.markdown(f"&nbsp;&nbsp;- `{table}`", unsafe_allow_html=True)
        else:
            st.warning(COPY["db_not_connected"])
            st.caption(COPY["db_waiting"])

        st.divider()

        st.subheader("Upload database")
        uploaded = st.file_uploader(
            "Drop a file to query it",
            type=["db", "sqlite", "csv", "xlsx"],
            label_visibility="collapsed",
            help="Supports SQLite (.db), CSV, and Excel files.",
        )
        if uploaded is not None:
            st.session_state.uploaded_db = uploaded

        if st.session_state.uploaded_db is not None:
            uploaded_file = st.session_state.uploaded_db
            st.success(uploaded_file.name)
            st.caption(f"{uploaded_file.size / 1024:.1f} KB ready to query")
            if st.button("Remove file", use_container_width=True):
                st.session_state.uploaded_db = None
                st.rerun()
        else:
            st.caption("No file loaded; using the configured backend data source.")

        st.divider()

        st.subheader(COPY["demo_section"])
        st.caption(COPY["demo_caption"])
        st.session_state.demo_mode = st.toggle(
            COPY["demo_toggle"],
            value=st.session_state.demo_mode,
        )

        st.divider()

        if st.button(COPY["clear_button"], use_container_width=True):
            st.session_state.history = []
            st.session_state.session_id = None
            st.rerun()


def _render_response(response: dict) -> None:
    if response.get("error"):
        st.error(response["error"])
        return

    if response.get("approximate_match"):
        st.info(COPY["approx_match"])

    confidence = response.get("confidence", 1.0)
    if confidence >= CONFIDENCE_THRESHOLD:
        st.success(f"{COPY['confidence_ok']} ({confidence:.0%})")
    else:
        st.warning(f"{COPY['confidence_warn']} ({confidence:.0%})")

    if response.get("clarification"):
        st.info(response["clarification"])

    if response.get("answer"):
        st.markdown(f"### {response['answer']}")

    insights = response.get("insights") or []
    if insights:
        st.markdown(f"**{COPY['insights_label']}**")
        for insight in insights:
            st.markdown(f"- {insight}")

    rows = response.get("rows", [])
    if rows:
        dataframe = pd.DataFrame(rows)
        _render_chart_from_spec(response.get("chart"), dataframe)
        st.dataframe(dataframe, use_container_width=True)

    with st.expander(COPY["expander_label"]):
        if response.get("tables_used"):
            st.markdown(f"**{COPY['tables_used_label']}:** {', '.join(response['tables_used'])}")
        if response.get("explanation"):
            st.markdown(f"**{COPY['explanation_label']}**")
            st.markdown(response["explanation"])
        if response.get("sql"):
            st.markdown(f"**{COPY['sql_label']}**")
            st.code(response["sql"], language="sql")


def _render_welcome() -> None:
    st.markdown(
        """
        <div style="text-align:center; padding: 4rem 1rem 2rem;">
            <h1 style="font-size:2.6rem; font-weight:700; margin-bottom:0.4rem;">
                IADS SQL Agent
            </h1>
            <p style="font-size:1.1rem; color:grey; margin-bottom:2rem;">
                Ask anything about the database in plain English.
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
    columns = st.columns(2)
    for index, example in enumerate(examples):
        with columns[index % 2]:
            if st.button(example, use_container_width=True, key=f"example_{index}"):
                st.session_state._example_question = example
                st.rerun()


def _ask_question(question: str) -> None:
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            response = call_api(question, st.session_state.session_id)
        if response.get("session_id"):
            st.session_state.session_id = response["session_id"]
        st.session_state.history.append({"question": question, "response": response})
        _render_response(response)


def main() -> None:
    st.set_page_config(
        page_title=COPY["app_name"],
        page_icon=":material/database:",
        layout="wide",
    )
    _init_state()
    _render_sidebar()

    if not st.session_state.history:
        _render_welcome()

    if getattr(st.session_state, "_example_question", None):
        example_question = st.session_state._example_question
        del st.session_state._example_question
        _ask_question(example_question)

    for entry in st.session_state.history:
        with st.chat_message("user"):
            st.markdown(entry["question"])
        with st.chat_message("assistant"):
            _render_response(entry["response"])

    question = st.chat_input(COPY["chat_placeholder"])
    if question:
        _ask_question(question)


if __name__ == "__main__":
    main()
