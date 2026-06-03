"""Streamlit chatbot frontend for the FastAPI SQL agent backend."""

from __future__ import annotations

import hashlib
import json
import os

import altair as alt
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
    "summary_button": "Show summary",
    "summary_hide_button": "Hide summary",
    "summary_label": "Summary",
    "expander_label": "How did the AI calculate this?",
    "insights_label": "Key insights",
    "chart_label": "Chart type",
    "chart_bar": "Bar",
    "chart_line": "Line",
    "chart_pie": "Pie",
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


def _response_key(response: dict, suffix: str, render_key: str = "") -> str:
    payload = {
        "answer": response.get("answer", ""),
        "sql": response.get("sql", ""),
        "rows": response.get("rows", []),
        "render_key": render_key,
    }
    raw = json.dumps(payload, sort_keys=True, default=str)
    digest = hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]
    return f"{suffix}_{digest}"


def _chart_axes(df: pd.DataFrame, spec: dict | None = None) -> tuple[str | None, str | None]:
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    categorical_cols = [column for column in df.columns if column not in numeric_cols]
    date_like_cols = [
        column
        for column in df.columns
        if any(
            token in column.lower()
            for token in ("date", "month", "year", "quarter", "week", "day")
        )
    ]

    if spec:
        x_axis = spec.get("x")
        y_axis = spec.get("y")
        if x_axis in df.columns and y_axis in numeric_cols:
            return x_axis, y_axis

    if date_like_cols and numeric_cols:
        x_axis = date_like_cols[0]
        value_cols = [column for column in numeric_cols if column != x_axis]
        if value_cols:
            return x_axis, value_cols[0]

    if categorical_cols and numeric_cols:
        return categorical_cols[0], numeric_cols[0]

    if len(df.columns) >= 2 and numeric_cols:
        x_axis = next(
            (column for column in df.columns if column not in numeric_cols),
            df.columns[0],
        )
        value_cols = [column for column in numeric_cols if column != x_axis]
        if value_cols:
            return x_axis, value_cols[0]

    return None, numeric_cols[0] if numeric_cols else None


def _default_chart_type(spec: dict | None) -> str:
    if spec and spec.get("type") == "line":
        return COPY["chart_line"]
    return COPY["chart_bar"]


def _render_selected_chart(chart_type: str, df: pd.DataFrame, spec: dict | None = None) -> None:
    if df.empty:
        return

    x_axis, y_axis = _chart_axes(df, spec)
    if not x_axis or not y_axis or x_axis not in df.columns or y_axis not in df.columns:
        st.warning("No chartable category and value columns were found.")
        return

    chart_df = df[[x_axis, y_axis]].dropna()
    if chart_df.empty:
        return

    x_type = "ordinal" if chart_df[x_axis].dtype.kind in "iu" else "nominal"
    if chart_type == COPY["chart_line"]:
        chart = (
            alt.Chart(chart_df)
            .mark_line(point=True)
            .encode(
                x=alt.X(field=x_axis, type=x_type),
                y=alt.Y(field=y_axis, type="quantitative"),
                tooltip=[x_axis, y_axis],
            )
        )
        st.altair_chart(chart, use_container_width=True)
        return
    if chart_type == COPY["chart_pie"]:
        chart = (
            alt.Chart(chart_df)
            .mark_arc()
            .encode(
                theta=alt.Theta(field=y_axis, type="quantitative"),
                color=alt.Color(field=x_axis, type="nominal"),
                tooltip=[x_axis, y_axis],
            )
        )
        st.altair_chart(chart, use_container_width=True)
        return
    chart = (
        alt.Chart(chart_df)
        .mark_bar()
        .encode(
            x=alt.X(field=x_axis, type=x_type),
            y=alt.Y(field=y_axis, type="quantitative"),
            tooltip=[x_axis, y_axis],
        )
    )
    st.altair_chart(chart, use_container_width=True)


def _render_chart_options(spec: dict | None, df: pd.DataFrame, key: str) -> None:
    """Render user-selected chart types using the backend suggestion as the default."""
    if df.empty:
        return

    options = [COPY["chart_bar"], COPY["chart_line"], COPY["chart_pie"]]
    default_option = _default_chart_type(spec)
    chart_type = st.radio(
        COPY["chart_label"],
        options,
        index=options.index(default_option),
        horizontal=True,
        key=key,
    )
    _render_selected_chart(chart_type, df, spec)


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
        date_col = date_cols[0]
        value_cols = [column for column in numeric_cols if column != date_col]
        if value_cols:
            st.line_chart(df.set_index(date_col)[value_cols])
        return

    if categorical_cols and numeric_cols:
        category_col = categorical_cols[0]
        value_cols = [column for column in numeric_cols if column != category_col]
        if value_cols:
            st.bar_chart(df.set_index(category_col)[value_cols])


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


def _render_response(response: dict, render_key: str = "") -> None:
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

    insights = response.get("insights") or []
    has_summary = bool(response.get("answer") or insights)
    if has_summary:
        summary_key = _response_key(response, "summary", render_key)
        visible_key = f"{summary_key}_visible"
        if visible_key not in st.session_state:
            st.session_state[visible_key] = False
        button_label = (
            COPY["summary_hide_button"]
            if st.session_state[visible_key]
            else COPY["summary_button"]
        )
        if st.button(button_label, key=f"{summary_key}_button"):
            st.session_state[visible_key] = not st.session_state[visible_key]
        if st.session_state[visible_key]:
            st.markdown(f"**{COPY['summary_label']}**")
            if response.get("answer"):
                st.markdown(f"### {response['answer']}")
            if insights:
                st.markdown(f"**{COPY['insights_label']}**")
                for insight in insights:
                    st.markdown(f"- {insight}")

    rows = response.get("rows", [])
    if rows:
        dataframe = pd.DataFrame(rows)
        chart_key = _response_key(response, "chart", render_key)
        _render_chart_options(response.get("chart"), dataframe, chart_key)
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
        _render_response(response, f"live_{len(st.session_state.history) - 1}")


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
        st.stop()

    for index, entry in enumerate(st.session_state.history):
        with st.chat_message("user"):
            st.markdown(entry["question"])
        with st.chat_message("assistant"):
            _render_response(entry["response"], f"history_{index}")

    question = st.chat_input(COPY["chat_placeholder"])
    if question:
        _ask_question(question)


if __name__ == "__main__":
    main()
