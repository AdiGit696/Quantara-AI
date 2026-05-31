import plotly.express as px
import streamlit as st

from ui_components import apply_chart_theme


def generate_auto_dashboard(df):
    st.write("### AI Auto Dashboard")

    numeric_cols = df.select_dtypes(include=["int64", "float64"]).columns
    cat_cols = df.select_dtypes(include=["object"]).columns

    col1, col2 = st.columns(2)

    if len(numeric_cols) >= 1:
        col1.metric("Avg " + numeric_cols[0], f"{df[numeric_cols[0]].mean():.2f}")

    if len(numeric_cols) >= 2:
        col2.metric("Avg " + numeric_cols[1], f"{df[numeric_cols[1]].mean():.2f}")

    if len(numeric_cols) >= 1:
        st.write("### Trend Analysis")
        fig = px.line(df, y=numeric_cols[0])
        apply_chart_theme(fig, title="Trend Analysis")
        st.plotly_chart(fig, use_container_width=True)

    if len(cat_cols) >= 1 and len(numeric_cols) >= 1:
        st.write("### Category Breakdown")
        fig = px.bar(df, x=cat_cols[0], y=numeric_cols[0])
        apply_chart_theme(fig, title="Category Breakdown")
        st.plotly_chart(fig, use_container_width=True)

    if len(numeric_cols) >= 2:
        st.write("### Correlation")
        fig = px.scatter(df, x=numeric_cols[0], y=numeric_cols[1])
        apply_chart_theme(fig, title="Correlation")
        st.plotly_chart(fig, use_container_width=True)
