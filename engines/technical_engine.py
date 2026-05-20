import pandas as pd
import numpy as np

# RSI
def calculate_rsi(prices, period=14):
    delta = prices.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


# Moving Average
def moving_average(prices, window=20):
    return prices.rolling(window).mean()


# Momentum
def momentum(prices, period=10):
    return prices.diff(period)


# Volatility (ATR-like simplified)
def atr(high, low, close, period=14):
    tr = pd.concat([
        high - low,
        abs(high - close.shift()),
        abs(low - close.shift())
    ], axis=1).max(axis=1)

    return tr.rolling(period).mean().iloc[-1]


# Bollinger Bands
def bollinger_bands(prices, window=20):
    ma = prices.rolling(window).mean()
    std = prices.rolling(window).std()
    return ma.iloc[-1], (ma + 2*std).iloc[-1], (ma - 2*std).iloc[-1]


# MACD
def macd(prices):
    exp1 = prices.ewm(span=12, adjust=False).mean()
    exp2 = prices.ewm(span=26, adjust=False).mean()
    macd_line = exp1 - exp2
    signal = macd_line.ewm(span=9, adjust=False).mean()
    return macd_line.iloc[-1], signal.iloc[-1]


# VWAP
def vwap(df):
    return (df["Close"] * df["Volume"]).cumsum() / df["Volume"].cumsum()


# RSI Divergence (simple)
def rsi_divergence(prices, rsi):
    if prices.iloc[-1] < prices.iloc[-5] and rsi.iloc[-1] > rsi.iloc[-5]:
        return "Bullish Divergence"
    elif prices.iloc[-1] > prices.iloc[-5] and rsi.iloc[-1] < rsi.iloc[-5]:
        return "Bearish Divergence"
    return "No divergence"


# Volume Analysis
def volume_analysis(close, volume):
    if close.iloc[-1] > close.iloc[-2] and volume.iloc[-1] > volume.iloc[-2]:
        return "Strong bullish"
    elif close.iloc[-1] < close.iloc[-2] and volume.iloc[-1] > volume.iloc[-2]:
        return "Strong bearish"
    return "Weak trend"


# Support Resistance
def support_resistance(prices, lookback=90):
    recent = prices.dropna().tail(lookback)
    support = recent.quantile(0.15)
    resistance = recent.quantile(0.85)
    current = prices.iloc[-1]

    if current <= support * 1.03:
        zone = "Near Support"
    elif current >= resistance * 0.97:
        zone = "Near Resistance"
    else:
        zone = "Mid Zone"

    return support, resistance, zone


# Multi timeframe
def multi_timeframe_trend(daily, weekly):
    daily = daily.dropna()
    weekly = weekly.dropna()

    if len(daily) < 50 or len(weekly) < 20:
        return "Sideways"

    daily_fast = daily.ewm(span=20, adjust=False).mean().iloc[-1]
    daily_slow = daily.ewm(span=50, adjust=False).mean().iloc[-1]
    weekly_fast = weekly.ewm(span=10, adjust=False).mean().iloc[-1]
    weekly_slow = weekly.ewm(span=30, adjust=False).mean().iloc[-1]

    if daily.iloc[-1] > daily_fast > daily_slow and weekly_fast > weekly_slow:
        return "Uptrend"
    elif daily.iloc[-1] < daily_fast < daily_slow:
        return "Downtrend"
    return "Sideways"


def volume_strength(close, volume, window=20):
    avg_volume = volume.rolling(window).mean().iloc[-1]
    latest_volume = volume.iloc[-1]
    price_change = close.pct_change().iloc[-1]

    if pd.isna(avg_volume) or avg_volume == 0:
        return {"label": "Unknown", "ratio": 1.0, "score": 0}

    ratio = float(latest_volume / avg_volume)

    if price_change > 0 and ratio >= 1.3:
        label, score = "Bullish accumulation", 1.0
    elif price_change < 0 and ratio >= 1.3:
        label, score = "Bearish distribution", -1.0
    elif ratio < 0.7:
        label, score = "Low participation", -0.25
    else:
        label, score = "Normal volume", 0.0

    return {"label": label, "ratio": ratio, "score": score}


def market_structure(df, lookback=60):
    recent = df.dropna().tail(lookback).copy()
    close = recent["Close"]
    high = recent["High"]
    low = recent["Low"]

    if len(recent) < 25:
        return {
            "support": float(close.iloc[-1]),
            "resistance": float(close.iloc[-1]),
            "zone": "Unknown",
            "breakout": "No breakout",
            "consolidation": False,
            "structure": "Insufficient data",
            "strength": 0
        }

    support = float(low.rolling(5).min().tail(20).quantile(0.25))
    resistance = float(high.rolling(5).max().tail(20).quantile(0.75))
    current = float(close.iloc[-1])
    prev_resistance = float(high.iloc[:-1].tail(20).max())
    prev_support = float(low.iloc[:-1].tail(20).min())

    range_pct = (resistance - support) / current if current else 0
    consolidation = range_pct < 0.08

    if current > prev_resistance * 1.01:
        breakout = "Bullish breakout"
    elif current < prev_support * 0.99:
        breakout = "Bearish breakdown"
    else:
        breakout = "No breakout"

    highs = high.rolling(5).max().dropna().tail(3)
    lows = low.rolling(5).min().dropna().tail(3)
    if len(highs) >= 3 and highs.iloc[-1] > highs.iloc[0] and lows.iloc[-1] > lows.iloc[0]:
        structure = "Higher highs / higher lows"
        strength = 1
    elif len(highs) >= 3 and highs.iloc[-1] < highs.iloc[0] and lows.iloc[-1] < lows.iloc[0]:
        structure = "Lower highs / lower lows"
        strength = -1
    else:
        structure = "Range-bound"
        strength = 0

    if current <= support * 1.03:
        zone = "Near Support"
    elif current >= resistance * 0.97:
        zone = "Near Resistance"
    else:
        zone = "Mid Zone"

    return {
        "support": support,
        "resistance": resistance,
        "zone": zone,
        "breakout": breakout,
        "consolidation": consolidation,
        "structure": structure,
        "strength": strength,
        "range_pct": float(range_pct)
    }
