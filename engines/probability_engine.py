def _bounded(value, low=0, high=100):
    return max(low, min(high, value))


def _confidence_level(probability, uncertainty):
    if probability >= 75 and uncertainty <= 22:
        return "High"
    if probability >= 60 and uncertainty <= 28:
        return "Moderate"
    if probability >= 48:
        return "Speculative"
    return "Low"


def score_trade_probability(
    trend,
    prediction,
    volume_info,
    structure,
    risk_plan,
    patterns,
    fundamentals,
    sentiment=None
):
    score = 50
    reasons = []
    factors = []
    uncertainty = 18

    def add_factor(name, weight, explanation):
        nonlocal score
        score += weight
        factors.append({
            "factor": name,
            "weight": round(weight, 2),
            "direction": "Positive" if weight > 0 else "Negative" if weight < 0 else "Neutral",
            "explanation": explanation
        })
        if explanation:
            reasons.append(explanation)

    expected_return = prediction.get("expected_return_pct", 0)
    if expected_return > 6:
        add_factor("Forecast upside", 12, "Forecast upside is strong")
    elif expected_return > 2:
        add_factor("Forecast direction", 7, "Forecast direction is positive")
    elif expected_return < 0:
        add_factor("Forecast direction", -16, "Forecast is negative")
    else:
        add_factor("Forecast edge", -4, "Forecast edge is small")

    if trend == "Uptrend":
        add_factor("Multi-timeframe trend", 12, "Multi-timeframe trend is aligned")
    elif trend == "Downtrend":
        add_factor("Multi-timeframe trend", -14, "Multi-timeframe trend is unfavorable")
    else:
        add_factor("Multi-timeframe trend", -2, "Trend is sideways")
        uncertainty += 4

    if volume_info.get("score", 0) > 0:
        add_factor("Volume confirmation", 8, "Volume confirms accumulation")
    elif volume_info.get("score", 0) < 0:
        add_factor("Volume confirmation", -8, "Volume suggests distribution")

    if structure.get("breakout") == "Bullish breakout":
        add_factor("Breakout state", 10, "Breakout improves probability")
    elif structure.get("breakout") == "Bearish breakdown":
        add_factor("Breakout state", -12, "Breakdown weakens probability")

    if structure.get("strength", 0) > 0:
        add_factor("Price structure", 6, "Price structure has higher highs/higher lows")
    elif structure.get("strength", 0) < 0:
        add_factor("Price structure", -6, "Price structure is deteriorating")

    pattern_bias = "Neutral"
    if patterns:
        bullish = sum(item["confidence"] for item in patterns if item["direction"] == "Bullish")
        bearish = sum(item["confidence"] for item in patterns if item["direction"] == "Bearish")
        if bullish > bearish:
            pattern_bias = "Bullish"
            add_factor("Pattern context", min((bullish - bearish) / 12, 10), "Pattern context is bullish")
        elif bearish > bullish:
            pattern_bias = "Bearish"
            add_factor("Pattern context", -min((bearish - bullish) / 12, 10), "Pattern context is bearish")

    rr = risk_plan.get("risk_reward", 0)
    if rr >= 2:
        add_factor("Risk-reward", 10, "Risk-reward is favorable")
    elif rr >= 1.3:
        add_factor("Risk-reward", 3, "Risk-reward is acceptable")
    else:
        add_factor("Risk-reward", -16, "Risk-reward is not attractive")

    atr_pct = risk_plan.get("atr_pct", 0)
    if atr_pct > 7:
        add_factor("Volatility adjustment", -8, "Volatility is high")
        uncertainty += 8
    elif atr_pct < 4:
        add_factor("Volatility adjustment", 3, "Volatility is manageable")

    fundamental_score = fundamentals.get("score", 50) if fundamentals else 50
    if fundamental_score >= 70:
        add_factor("Fundamental quality", 8, "Fundamentals support the trade")
    elif fundamental_score < 40:
        add_factor("Fundamental quality", -8, "Fundamentals add risk")
    elif fundamental_score == 0:
        uncertainty += 6

    if sentiment:
        if sentiment.get("score", 0) > 1:
            add_factor("News sentiment", 4, "News sentiment is positive")
        elif sentiment.get("score", 0) < -1:
            add_factor("News sentiment", -4, "News sentiment is negative")

    probability = int(_bounded(score, 5, 92))
    uncertainty = int(_bounded(uncertainty + max(0, 60 - probability) / 4, 8, 35))

    if probability >= 75 and uncertainty <= 22:
        risk_level = "Low-Medium"
    elif probability >= 62:
        risk_level = "Medium"
    elif probability >= 48:
        risk_level = "Medium-High"
    else:
        risk_level = "High"

    if risk_plan.get("atr_pct", 0) <= 4 and trend == "Uptrend":
        holding_period = "2-4 weeks"
    elif risk_plan.get("atr_pct", 0) <= 6:
        holding_period = "1-3 weeks"
    else:
        holding_period = "3-10 trading days"

    positive_weight = round(sum(item["weight"] for item in factors if item["weight"] > 0), 2)
    negative_weight = round(abs(sum(item["weight"] for item in factors if item["weight"] < 0)), 2)
    model_name = "Bayesian Momentum Ensemble"
    model_description = (
        "A weighted ensemble that starts from a neutral prior, then adjusts confidence using forecast edge, "
        "trend, volume, market structure, patterns, risk-reward, volatility, fundamentals, and sentiment."
    )
    selected_reason = "Selected because the setup combines directional momentum, volatility-adjusted risk, and multi-factor AI scoring."

    return {
        "trade_confidence": probability,
        "uncertainty": uncertainty,
        "risk_level": risk_level,
        "holding_period": holding_period,
        "pattern_bias": pattern_bias,
        "reasons": reasons[:9],
        "model_name": model_name,
        "model_description": model_description,
        "selected_reason": selected_reason,
        "confidence_level": _confidence_level(probability, uncertainty),
        "positive_weight": positive_weight,
        "negative_weight": negative_weight,
        "risk_confidence": max(0, min(100, 100 - uncertainty - max(0, risk_plan.get("atr_pct", 0) * 2))),
        "factors": sorted(factors, key=lambda item: abs(item["weight"]), reverse=True)[:8]
    }
