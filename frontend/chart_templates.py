"""Advanced chart templates for Streamlit app."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


def create_heatmap(df: pd.DataFrame) -> None:
    """Create correlation heatmap for numeric data."""
    numeric_df = df.select_dtypes(include=["number"])
    if len(numeric_df.columns) > 1:
        corr = numeric_df.corr()
        fig = px.imshow(
            corr,
            text_auto=True,
            aspect="auto",
            color_continuous_scale="RdBu_r",
            title="Correlation Heatmap"
        )
        st.plotly_chart(fig, use_container_width=True)


def create_scatter_matrix(df: pd.DataFrame, sample: int = 100) -> None:
    """Create scatter plot matrix for numeric columns."""
    numeric_df = df.select_dtypes(include=["number"])
    if len(numeric_df.columns) > 1:
        # Sample if too large
        plot_df = numeric_df.sample(min(len(numeric_df), sample))
        fig = px.scatter_matrix(
            plot_df,
            title="Scatter Matrix of Numeric Columns",
            labels={col: col for col in numeric_df.columns}
        )
        fig.update_traces(diagonal_visible=False)
        st.plotly_chart(fig, use_container_width=True)


def create_distribution(df: pd.DataFrame) -> None:
    """Create distribution plots for numeric columns."""
    numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
    if not numeric_cols:
        return
    
    selected_col = st.selectbox("Select column to analyze", numeric_cols)
    
    col1, col2 = st.columns(2)
    
    with col1:
        fig = px.histogram(df, x=selected_col, nbins=30, 
                          title=f"Distribution of {selected_col}")
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        fig = px.box(df, y=selected_col, title=f"Box Plot of {selected_col}")
        st.plotly_chart(fig, use_container_width=True)


def create_sunburst(df: pd.DataFrame, hierarchy: list[str], value_col: str) -> None:
    """Create sunburst chart for hierarchical data."""
    if all(col in df.columns for col in hierarchy) and value_col in df.columns:
        fig = px.sunburst(
            df,
            labels=hierarchy + [value_col],
            parents=[None] + hierarchy,
            values=value_col,
            title="Hierarchical View"
        )
        st.plotly_chart(fig, use_container_width=True)


def create_waterfall(df: pd.DataFrame, category_col: str, value_col: str) -> None:
    """Create waterfall chart for cumulative changes."""
    if category_col in df.columns and value_col in df.columns:
        cumulative = df[value_col].cumsum()
        
        fig = go.Figure()
        fig.add_trace(go.Waterfall(
            x=df[category_col],
            y=df[value_col],
            text=df[value_col],
            textposition="outside",
            connector={"line": {"color": "rgba(63, 63, 63, 0.5)"}},
        ))
        fig.update_layout(title="Cumulative Changes", showlegend=True)
        st.plotly_chart(fig, use_container_width=True)


def create_funnel(df: pd.DataFrame, stage_col: str, value_col: str) -> None:
    """Create funnel chart for conversion tracking."""
    if stage_col in df.columns and value_col in df.columns:
        # Sort by value descending
        plot_df = df.sort_values(value_col, ascending=False)
        fig = px.funnel(plot_df, x=value_col, y=stage_col, 
                       title="Conversion Funnel")
        st.plotly_chart(fig, use_container_width=True)


def create_comparison_table(df: pd.DataFrame) -> None:
    """Create styled comparison table."""
    numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
    
    if numeric_cols:
        styled_df = df.style.format(subset=numeric_cols, formatter="{:.2f}") \
                           .highlight_max(subset=numeric_cols, color="lightgreen") \
                           .highlight_min(subset=numeric_cols, color="lightcoral")
        st.dataframe(styled_df, use_container_width=True)
    else:
        st.dataframe(df, use_container_width=True)


def create_metrics_dashboard(df: pd.DataFrame) -> None:
    """Create KPI dashboard from data."""
    numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
    
    if not numeric_cols:
        return
    
    cols = st.columns(len(numeric_cols))
    
    for idx, col in enumerate(numeric_cols):
        with cols[idx]:
            value = df[col].sum() if len(df) > 1 else df[col].iloc[0]
            delta = None
            if len(df) > 1:
                delta = f"{(df[col].iloc[0] - df[col].iloc[-1]):.2f}"
            
            st.metric(label=col, value=f"{value:,.2f}", delta=delta)


def create_comparison_bars(df: pd.DataFrame, group_col: str, value_cols: list[str]) -> None:
    """Create grouped bar chart for comparisons."""
    if group_col in df.columns:
        fig = px.bar(df, x=group_col, y=value_cols, barmode="group",
                    title="Comparison Chart")
        st.plotly_chart(fig, use_container_width=True)
