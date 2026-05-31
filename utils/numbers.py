import math

import pandas as pd


def numeric_series(value):
    if value is None:
        return pd.Series(dtype=float)
    if isinstance(value, pd.DataFrame):
        if value.empty:
            return pd.Series(dtype=float)
        value = value.iloc[:, 0]
    if isinstance(value, pd.Series):
        series = pd.to_numeric(value, errors="coerce")
    else:
        series = pd.to_numeric(pd.Series(value), errors="coerce")
    return series.dropna().astype(float)


def latest_float(value, default=None):
    try:
        series = numeric_series(value)
        if series.empty:
            return default
        result = float(series.iloc[-1])
        return result if math.isfinite(result) else default
    except Exception:
        return default


def first_float(value, default=None):
    try:
        series = numeric_series(value)
        if series.empty:
            return default
        result = float(series.iloc[0])
        return result if math.isfinite(result) else default
    except Exception:
        return default


def clean_ohlcv_frame(frame):
    if frame is None or frame.empty:
        return pd.DataFrame()
    out = frame.copy()
    if isinstance(out.columns, pd.MultiIndex):
        out.columns = out.columns.get_level_values(0)
    for col in ["Open", "High", "Low", "Close", "Volume"]:
        if col in out:
            series = numeric_series(out[col])
            out[col] = series.reindex(out.index)
    required = [col for col in ["Open", "High", "Low", "Close"] if col in out]
    if required:
        out = out.dropna(subset=required)
    return out

