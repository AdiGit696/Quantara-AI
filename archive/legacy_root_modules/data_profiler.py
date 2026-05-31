import pandas as pd
import streamlit as st

def profile_data(df):

    st.write("### Data Profiling")

    # Missing values
    missing = df.isnull().sum()
    st.write("Missing Values")
    st.dataframe(missing)

    # Basic stats
    st.write("Statistical Summary")
    st.dataframe(df.describe())

    # Skewness
    numeric = df.select_dtypes(include=['int64','float64'])
    if not numeric.empty:
        skew = numeric.skew()
        st.write("Skewness")
        st.dataframe(skew)