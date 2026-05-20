import plotly.express as px
import streamlit as st

from ui_components import apply_chart_theme


def build_chart(df, spec):

    if not spec:
        st.warning("AI could not interpret the query.")
        return

    try:

        chart = spec.get("chart")
        x = spec.get("x")
        y = spec.get("y")

        if chart == "scatter":
            fig = px.scatter(df, x=x, y=y)

        elif chart == "line":
            fig = px.line(df, x=x, y=y)

        elif chart == "bar":
            fig = px.bar(df, x=x, y=y)

        else:
            st.warning("Unsupported chart type.")
            return

        apply_chart_theme(fig, title=spec.get("title"))
        st.plotly_chart(fig, use_container_width=True)

    except Exception as e:

        st.error(f"Chart generation failed: {e}")
