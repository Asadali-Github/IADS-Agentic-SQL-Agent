"""Monitoring dashboard for the SQL Agent.

Shows:
- Performance metrics (latency, accuracy, throughput)
- Error tracking
- Query patterns
- Database health
"""

from __future__ import annotations

import os
import json
from pathlib import Path

import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import httpx


# Page config
st.set_page_config(
    page_title="IADS Agent Monitoring",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

API_URL = os.getenv("API_URL", "http://localhost:8000")

# Custom CSS
st.markdown(
    """
    <style>
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 20px;
        border-radius: 10px;
        color: white;
        margin: 10px 0;
    }
    .metric-value {
        font-size: 32px;
        font-weight: bold;
    }
    .metric-label {
        font-size: 14px;
        opacity: 0.8;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def load_metrics() -> pd.DataFrame | None:
    """Load metrics from the metrics.jsonl file."""
    metrics_file = Path("logs/metrics.jsonl")
    if not metrics_file.exists():
        return None
    
    try:
        df = pd.read_json(metrics_file, lines=True)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        return df
    except Exception as e:
        st.error(f"Error loading metrics: {e}")
        return None


def get_api_metrics(hours: int = 24) -> dict:
    """Get metrics from the API."""
    try:
        response = httpx.get(f"{API_URL}/metrics?hours={hours}", timeout=5)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        st.warning(f"Could not fetch metrics from API: {e}")
    return {}


def get_api_errors(limit: int = 20) -> dict:
    """Get recent errors from the API."""
    try:
        response = httpx.get(f"{API_URL}/metrics/errors?limit={limit}", timeout=5)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        st.warning(f"Could not fetch errors from API: {e}")
    return {}


# ============================================================================
# MAIN APP
# ============================================================================

st.title("📊 IADS SQL Agent Monitoring")
st.caption("Real-time performance metrics and health monitoring")

# Tabs
tab1, tab2, tab3, tab4 = st.tabs([
    "📈 Overview",
    "📊 Performance",
    "⚠️  Errors",
    "📋 Logs"
])

# ============================================================================
# TAB 1: Overview
# ============================================================================

with tab1:
    st.subheader("System Health")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        try:
            response = httpx.get(f"{API_URL}/health", timeout=5)
            if response.status_code == 200:
                health = response.json()
                status = "🟢 Healthy" if health.get("status") == "healthy" else "🔴 Unhealthy"
                st.metric("API Status", status)
            else:
                st.metric("API Status", "🔴 Offline")
        except:
            st.metric("API Status", "🔴 Offline")
    
    with col2:
        metrics_data = get_api_metrics(hours=1)
        if metrics_data:
            st.metric(
                "Queries (Last Hour)",
                metrics_data.get("total_queries", 0),
                delta=None
            )
        else:
            st.metric("Queries (Last Hour)", "—")
    
    with col3:
        if metrics_data:
            error_rate = metrics_data.get("error_rate", 0)
            st.metric(
                "Error Rate",
                f"{error_rate}%",
                delta=None,
                delta_color="inverse"
            )
        else:
            st.metric("Error Rate", "—")
    
    st.divider()
    
    # Key metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        if metrics_data and "avg_latency_ms" in metrics_data:
            st.metric(
                "Avg Latency",
                f"{metrics_data['avg_latency_ms']:.0f}ms"
            )
    
    with col2:
        if metrics_data and "p95_latency_ms" in metrics_data:
            st.metric(
                "P95 Latency",
                f"{metrics_data['p95_latency_ms']:.0f}ms"
            )
    
    with col3:
        if metrics_data and "avg_accuracy" in metrics_data:
            st.metric(
                "Avg Accuracy",
                f"{metrics_data['avg_accuracy']:.1%}"
            )
    
    with col4:
        if metrics_data and "total_rows_returned" in metrics_data:
            st.metric(
                "Total Rows",
                f"{metrics_data['total_rows_returned']:,}"
            )


# ============================================================================
# TAB 2: Performance
# ============================================================================

with tab2:
    st.subheader("Performance Analysis")
    
    df = load_metrics()
    
    if df is None or df.empty:
        st.info("No metrics data available yet. Start running queries!")
    else:
        # Filter to query metrics only
        query_df = df[df.get("type") != "db_operation"].copy()
        
        if not query_df.empty:
            # Latency over time
            st.subheader("Query Latency Trend")
            query_df_sorted = query_df.sort_values("timestamp")
            fig = px.line(
                query_df_sorted,
                x="timestamp",
                y="latency_ms",
                title="Query Latency Over Time",
                labels={"latency_ms": "Latency (ms)", "timestamp": "Time"}
            )
            fig.update_layout(hovermode="x unified")
            st.plotly_chart(fig, use_container_width=True)
            
            # Accuracy distribution
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("Accuracy Distribution")
                fig = px.histogram(
                    query_df,
                    x="accuracy",
                    nbins=20,
                    title="Query Accuracy Distribution",
                    labels={"accuracy": "Accuracy", "count": "Count"}
                )
                st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                st.subheader("Latency Distribution")
                fig = px.box(
                    query_df,
                    y="latency_ms",
                    title="Latency Distribution"
                )
                st.plotly_chart(fig, use_container_width=True)
            
            # Percentiles
            st.subheader("Latency Percentiles")
            percentiles = {
                "Min": query_df["latency_ms"].min(),
                "P25": query_df["latency_ms"].quantile(0.25),
                "P50": query_df["latency_ms"].quantile(0.50),
                "P75": query_df["latency_ms"].quantile(0.75),
                "P95": query_df["latency_ms"].quantile(0.95),
                "P99": query_df["latency_ms"].quantile(0.99),
                "Max": query_df["latency_ms"].max(),
            }
            
            perc_df = pd.DataFrame({
                "Percentile": list(percentiles.keys()),
                "Latency (ms)": list(percentiles.values())
            })
            
            fig = px.bar(
                perc_df,
                x="Percentile",
                y="Latency (ms)",
                title="Latency Percentiles"
            )
            st.plotly_chart(fig, use_container_width=True)


# ============================================================================
# TAB 3: Errors
# ============================================================================

with tab3:
    st.subheader("Error Tracking")
    
    error_data = get_api_errors(limit=50)
    errors = error_data.get("recent_errors", [])
    
    if not errors:
        st.success("✅ No errors recorded!")
    else:
        df_errors = pd.DataFrame(errors)
        
        # Error summary
        col1, col2 = st.columns(2)
        
        with col1:
            st.metric("Total Errors", len(errors))
        
        with col2:
            if "timestamp" in df_errors.columns:
                latest = df_errors.iloc[0] if not df_errors.empty else None
                if latest is not None:
                    st.metric("Latest Error", latest.get("timestamp", "—")[:19])
        
        st.divider()
        
        # Error table
        st.subheader("Recent Errors")
        display_cols = [col for col in ["timestamp", "question", "error", "latency_ms"] if col in df_errors.columns]
        st.dataframe(df_errors[display_cols], use_container_width=True)


# ============================================================================
# TAB 4: Logs
# ============================================================================

with tab4:
    st.subheader("System Logs")
    
    log_file = Path("logs/agent.log")
    
    if log_file.exists():
        # Get last N lines
        lines_to_show = st.slider("Show last N lines", 10, 200, 50)
        
        with open(log_file, "r") as f:
            all_lines = f.readlines()
            recent_lines = all_lines[-lines_to_show:]
        
        log_text = "".join(recent_lines)
        st.code(log_text, language="log")
        
        # Log stats
        st.divider()
        st.subheader("Log Statistics")
        
        error_count = sum(1 for line in all_lines if "ERROR" in line)
        warning_count = sum(1 for line in all_lines if "WARNING" in line)
        info_count = sum(1 for line in all_lines if "INFO" in line)
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Errors", error_count)
        with col2:
            st.metric("Warnings", warning_count)
        with col3:
            st.metric("Info", info_count)
    
    else:
        st.info("No logs yet. Logs will appear as queries are processed.")


# Auto-refresh
st.markdown("---")
col1, col2 = st.columns([3, 1])
with col2:
    if st.button("🔄 Refresh"):
        st.rerun()

st.caption("Auto-refresh: Refresh the page manually to see latest metrics")
