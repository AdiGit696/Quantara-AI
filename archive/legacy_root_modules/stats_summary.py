def summarize_dataframe(df):

    numeric = df.select_dtypes(include=['int64','float64'])

    summary = {}

    summary["columns"] = list(df.columns)
    summary["rows"] = len(df)

    if not numeric.empty:

        summary["mean"] = numeric.mean().to_dict()
        summary["min"] = numeric.min().to_dict()
        summary["max"] = numeric.max().to_dict()

        # only first 3 correlations (important)
        corr = numeric.corr()

        limited_corr = {}
        for col in corr.columns[:3]:
            limited_corr[col] = corr[col].to_dict()

        summary["correlation"] = limited_corr

    return summary