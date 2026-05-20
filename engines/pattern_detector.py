import pandas as pd


def is_doji(row):
    body = abs(row["Open"] - row["Close"])
    range_ = row["High"] - row["Low"]
    return body / range_ < 0.1 if range_ != 0 else False


def is_hammer(row):
    body = abs(row["Open"] - row["Close"])
    lower_shadow = row["Open"] - row["Low"] if row["Open"] > row["Close"] else row["Close"] - row["Low"]
    upper_shadow = row["High"] - max(row["Open"], row["Close"])

    return lower_shadow > 2 * body and upper_shadow < body


def is_shooting_star(row):
    body = abs(row["Open"] - row["Close"])
    upper_shadow = row["High"] - max(row["Open"], row["Close"])
    lower_shadow = min(row["Open"], row["Close"]) - row["Low"]

    return upper_shadow > 2 * body and lower_shadow < body


def is_bullish_engulfing(prev, curr):
    return (
        prev["Close"] < prev["Open"] and
        curr["Close"] > curr["Open"] and
        curr["Close"] > prev["Open"] and
        curr["Open"] < prev["Close"]
    )


def is_bearish_engulfing(prev, curr):
    return (
        prev["Close"] > prev["Open"] and
        curr["Close"] < curr["Open"] and
        curr["Open"] > prev["Close"] and
        curr["Close"] < prev["Open"]
    )


def detect_trend(prices):

    if prices.iloc[-1] > prices.mean():
        return "Uptrend"
    elif prices.iloc[-1] < prices.mean():
        return "Downtrend"
    else:
        return "Sideways"


def detect_patterns(df):

    patterns = []

    if len(df) < 2:
        return ["Not enough data"]

    last = df.iloc[-1]
    prev = df.iloc[-2]

    if is_doji(last):
        patterns.append("Doji (Indecision)")

    if is_hammer(last):
        patterns.append("Hammer (Bullish Reversal)")

    if is_shooting_star(last):
        patterns.append("Shooting Star (Bearish Reversal)")

    if is_bullish_engulfing(prev, last):
        patterns.append("Bullish Engulfing")

    if is_bearish_engulfing(prev, last):
        patterns.append("Bearish Engulfing")

    recent = df.tail(30)
    close = recent["Close"]
    high = recent["High"]
    low = recent["Low"]

    if len(recent) >= 20:
        recent_high = high.iloc[:-1].tail(20).max()
        recent_low = low.iloc[:-1].tail(20).min()
        range_pct = (recent_high - recent_low) / close.iloc[-1] if close.iloc[-1] else 0

        if range_pct < 0.08:
            patterns.append("Consolidation Base")

        if close.iloc[-1] > recent_high * 1.01:
            patterns.append("Range Breakout")

        if close.iloc[-1] < recent_low * 0.99:
            patterns.append("Range Breakdown")

        higher_lows = low.tail(5).min() > low.tail(15).head(10).min()
        near_resistance = close.iloc[-1] >= recent_high * 0.97
        if higher_lows and near_resistance:
            patterns.append("Ascending Pressure")

        lower_highs = high.tail(5).max() < high.tail(15).head(10).max()
        near_support = close.iloc[-1] <= recent_low * 1.03
        if lower_highs and near_support:
            patterns.append("Distribution Pressure")

    if not patterns:
        patterns.append("No strong pattern")

    return patterns
