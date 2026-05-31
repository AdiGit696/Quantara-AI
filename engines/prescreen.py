
import pandas as pd


def score_candidates(symbol_data):
    rows = []
    for ticker, df in symbol_data.items():
        if df is None or df.empty or len(df) < 30 or "Close" not in df or "Volume" not in df:
            continue
        close = pd.to_numeric(df["Close"], errors="coerce").dropna()
        volume = pd.to_numeric(df["Volume"], errors="coerce").dropna()
        if len(close) < 30 or volume.empty:
            continue
        momentum = ((float(close.iloc[-1]) / float(close.iloc[-20])) - 1) * 100 if close.iloc[-20] else 0
        avg_vol = float(volume.tail(20).mean())
        vol_spike = float(volume.iloc[-1]) / max(avg_vol, 1)
        rows.append((ticker, momentum * 0.5 + vol_spike * 20))
    return rows


def prescreen_candidates(symbol_data, keep_ratio=0.10, max_candidates=None):
    """
    symbol_data = {
      ticker: dataframe_with_OHLCV
    }
    Returns top candidates only.
    """
    rows = score_candidates(symbol_data)
    ranked = sorted(rows, key=lambda x: x[1], reverse=True)
    keep = max(10, int(len(ranked) * keep_ratio))
    if max_candidates is not None:
        keep = min(keep, max_candidates)
    return [x[0] for x in ranked[:keep]]
