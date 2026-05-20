import pandas as pd
import plotly.express as px
import streamlit as st

from ui_components import apply_chart_theme


def generate_dashboard(df):

    numeric = df.select_dtypes(include=['int64','float64']).columns
    categorical = df.select_dtypes(include=['object']).columns

    if len(numeric) >= 2:
        fig = px.scatter(df, x=numeric[0], y=numeric[1],
                         title=f"{numeric[0]} vs {numeric[1]}")
        apply_chart_theme(fig, title=f"{numeric[0]} vs {numeric[1]}")
        st.plotly_chart(fig, use_container_width=True)

    if len(categorical) > 0 and len(numeric) > 0:
        fig = px.bar(df, x=categorical[0], y=numeric[0],
                     title=f"{numeric[0]} by {categorical[0]}")
        apply_chart_theme(fig, title=f"{numeric[0]} by {categorical[0]}")
        st.plotly_chart(fig, use_container_width=True)

    if len(numeric) >= 2:
        corr = df[numeric].corr()
        fig = px.imshow(corr, text_auto=True, title="Correlation Heatmap")
        apply_chart_theme(fig, title="Correlation Heatmap")
        st.plotly_chart(fig, use_container_width=True)
