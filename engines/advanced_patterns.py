import numpy as np

from engines.technical_engine import market_structure, volume_strength


def _body(row):
    return abs(row["Close"] - row["Open"])


def _range(row):
    return max(row["High"] - row["Low"], 1e-9)


def _trend_slope(close, window=20):
    recent = close.tail(window)
    if len(recent) < 8:
        return 0.0
    x = np.arange(len(recent))
    slope, _ = np.polyfit(x, recent.values, 1)
    return float(slope / recent.iloc[-1])


def _confidence(base, volume_ratio=1.0, near_key_zone=False, trend_aligned=True):
    score = base
    score += min(max(volume_ratio - 1, 0), 1) * 10
    score += 8 if near_key_zone else 0
    score += 6 if trend_aligned else -6
    return int(max(35, min(92, score)))


def _add(patterns, name, direction, confidence, explanation, start_index=None, end_index=None):
    patterns.append({
        "name": name,
        "direction": direction,
        "confidence": confidence,
        "explanation": explanation,
        "start_index": start_index,
        "end_index": end_index
    })


def detect_advanced_patterns(df, lookback=260):
    data = df.dropna().tail(lookback)
    patterns = []

    if len(data) < 5:
        return patterns

    close = data["Close"]
    high = data["High"]
    low = data["Low"]
    volume_info = volume_strength(close, data["Volume"])
    structure = market_structure(data)
    last = data.iloc[-1]
    prev = data.iloc[-2]
    third = data.iloc[-3]
    trend = _trend_slope(close)

    near_support = structure["zone"] == "Near Support"
    near_resistance = structure["zone"] == "Near Resistance"
    volume_ratio = volume_info["ratio"]

    if _body(last) / _range(last) < 0.12:
        _add(patterns, "Doji", "Neutral", _confidence(48, volume_ratio, near_support or near_resistance, False), "Indecision candle near current price zone.")

    lower_shadow = min(last["Open"], last["Close"]) - last["Low"]
    upper_shadow = last["High"] - max(last["Open"], last["Close"])

    if lower_shadow > 2 * _body(last) and upper_shadow < _body(last) * 1.2:
        _add(patterns, "Hammer", "Bullish", _confidence(58, volume_ratio, near_support, trend <= 0), "Hammer suggests rejection of lower prices, stronger near support.")

    if upper_shadow > 2 * _body(last) and lower_shadow < _body(last) * 1.2:
        _add(patterns, "Shooting Star", "Bearish", _confidence(58, volume_ratio, near_resistance, trend >= 0), "Shooting star suggests supply near higher levels.")

    if prev["Close"] < prev["Open"] and last["Close"] > last["Open"] and last["Close"] > prev["Open"] and last["Open"] < prev["Close"]:
        _add(patterns, "Bullish Engulfing", "Bullish", _confidence(66, volume_ratio, near_support, trend <= 0), "Bullish engulfing with contextual support/volume confirmation.")

    if prev["Close"] > prev["Open"] and last["Close"] < last["Open"] and last["Open"] > prev["Close"] and last["Close"] < prev["Open"]:
        _add(patterns, "Bearish Engulfing", "Bearish", _confidence(66, volume_ratio, near_resistance, trend >= 0), "Bearish engulfing warns of reversal pressure.")

    if prev["Close"] < prev["Open"] and abs(third["Close"] - third["Open"]) / _range(third) < 0.35 and last["Close"] > last["Open"] and last["Close"] > (prev["Open"] + prev["Close"]) / 2:
        _add(patterns, "Morning Star", "Bullish", _confidence(70, volume_ratio, near_support, True), "Three-candle bullish reversal structure after weakness.")

    if prev["Close"] > prev["Open"] and abs(third["Close"] - third["Open"]) / _range(third) < 0.35 and last["Close"] < last["Open"] and last["Close"] < (prev["Open"] + prev["Close"]) / 2:
        _add(patterns, "Evening Star", "Bearish", _confidence(70, volume_ratio, near_resistance, True), "Three-candle bearish reversal structure after strength.")

    if last["Close"] > last["Open"] and prev["Close"] < prev["Open"] and last["Open"] > prev["Close"] and last["Close"] < prev["Open"]:
        _add(patterns, "Bullish Harami", "Bullish", _confidence(54, volume_ratio, near_support, trend <= 0), "Smaller bullish candle inside prior bearish body.")

    if last["Close"] < last["Open"] and prev["Close"] > prev["Open"] and last["Open"] < prev["Close"] and last["Close"] > prev["Open"]:
        _add(patterns, "Bearish Harami", "Bearish", _confidence(54, volume_ratio, near_resistance, trend >= 0), "Smaller bearish candle inside prior bullish body.")

    last_three = data.tail(3)
    if all(last_three["Close"] > last_three["Open"]) and last_three["Close"].is_monotonic_increasing:
        _add(patterns, "Three White Soldiers", "Bullish", _confidence(72, volume_ratio, False, trend >= 0), "Three consecutive strong bullish candles indicate momentum continuation.")

    if all(last_three["Close"] < last_three["Open"]) and last_three["Close"].is_monotonic_decreasing:
        _add(patterns, "Three Black Crows", "Bearish", _confidence(72, volume_ratio, False, trend <= 0), "Three consecutive bearish candles indicate downside momentum.")

    recent_high = high.iloc[:-1].tail(40).max()
    recent_low = low.iloc[:-1].tail(40).min()
    if close.iloc[-1] > recent_high * 1.01:
        _add(patterns, "Breakout", "Bullish", _confidence(74, volume_ratio, False, True), "Price closed above recent resistance with breakout characteristics.")
    if close.iloc[-1] < recent_low * 0.99:
        _add(patterns, "Breakdown", "Bearish", _confidence(74, volume_ratio, False, True), "Price closed below recent support.")

    range_pct = (recent_high - recent_low) / close.iloc[-1] if close.iloc[-1] else 0
    if range_pct < 0.08:
        _add(patterns, "Flag / Pennant Consolidation", "Neutral", _confidence(57, volume_ratio, False, True), "Tight consolidation may precede a directional move.")

    first_half = data.tail(80).head(40)
    second_half = data.tail(80).tail(40)
    if len(first_half) >= 20 and len(second_half) >= 20:
        left_high = first_half["High"].max()
        right_high = second_half["High"].max()
        middle_low = data.tail(80)["Low"].iloc[20:60].min()
        if abs(left_high - right_high) / close.iloc[-1] < 0.04 and close.iloc[-1] < min(left_high, right_high) * 0.96:
            _add(patterns, "Double Top", "Bearish", 68, "Two failed attempts near resistance suggest distribution risk.")
        if abs(first_half["Low"].min() - second_half["Low"].min()) / close.iloc[-1] < 0.04 and close.iloc[-1] > middle_low * 1.04:
            _add(patterns, "Double Bottom", "Bullish", 68, "Two support holds suggest accumulation potential.")

    if len(data) >= 90:
        segment = close.tail(90)
        cup_low = segment.iloc[20:65].min()
        left = segment.iloc[:20].max()
        right = segment.iloc[-20:].max()
        handle_drop = (right - segment.iloc[-10:].min()) / right if right else 0
        if abs(left - right) / segment.iloc[-1] < 0.08 and cup_low < left * 0.85 and handle_drop < 0.12:
            _add(patterns, "Cup and Handle", "Bullish", 65, "Rounded recovery with shallow handle; watch for resistance breakout.")

    if not patterns:
        _add(patterns, "No High-Quality Pattern", "Neutral", 45, "No major candle or price-structure pattern has enough confirmation.")

    return sorted(patterns, key=lambda item: item["confidence"], reverse=True)


def pattern_summary(patterns):
    top = patterns[0] if patterns else {"name": "No pattern", "direction": "Neutral", "confidence": 0}
    bullish = sum(1 for item in patterns if item["direction"] == "Bullish")
    bearish = sum(1 for item in patterns if item["direction"] == "Bearish")

    if bullish > bearish:
        bias = "Bullish"
    elif bearish > bullish:
        bias = "Bearish"
    else:
        bias = "Neutral"

    return {
        "top_pattern": top["name"],
        "bias": bias,
        "confidence": top["confidence"],
        "explanation": top.get("explanation", "")
    }
