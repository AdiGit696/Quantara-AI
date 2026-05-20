def final_decision(tech_score, fund_score, pattern):
    score = tech_score + fund_score

    if "Doji" in pattern:
        return "WAIT"

    if score >= 5:
        return "STRONG BUY"
    elif score >= 3:
        return "BUY"
    elif score >= 2:
        return "HOLD"
    return "AVOID"


def evaluate_decision(
    current_price,
    rsi,
    macd_val,
    macd_signal,
    trend,
    prediction,
    volume_info,
    structure,
    risk_plan,
    pattern_text,
    fundamentals=None
):
    """
    Weighted swing decision with explicit contradiction gates.

    A BUY is impossible when the forecast is below current price, when the
    broader trend is down, or when risk-reward is poor.
    """
    reasons = []
    score = 0.0

    expected_return = prediction.get("expected_return_pct", 0.0)
    predicted_price = prediction.get("future_30", current_price)

    if predicted_price < current_price or expected_return <= 0:
        reasons.append("Forecast is not positive")
        forecast_gate = False
    else:
        forecast_gate = True
        score += min(expected_return / 2.0, 2.0)
        reasons.append(f"30d forecast upside {expected_return:.1f}%")

    if trend == "Uptrend":
        score += 2.0
        reasons.append("Daily and weekly trend align upward")
    elif trend == "Sideways":
        score += 0.5
        reasons.append("Trend is sideways")
    else:
        score -= 2.0
        reasons.append("Trend is down")

    if 45 <= rsi <= 65:
        score += 1.0
        reasons.append("RSI is in a constructive swing zone")
    elif rsi < 35:
        score += 0.5
        reasons.append("RSI is oversold; wait for confirmation")
    elif rsi > 72:
        score -= 1.5
        reasons.append("RSI is overheated")

    if macd_val > macd_signal:
        score += 1.0
        reasons.append("MACD is bullish")
    else:
        score -= 0.75
        reasons.append("MACD is not bullish")

    score += volume_info.get("score", 0.0)
    reasons.append(volume_info.get("label", "Volume unavailable"))

    structure_strength = structure.get("strength", 0)
    if structure_strength > 0:
        score += 1.0
        reasons.append(structure.get("structure", "Positive structure"))
    elif structure_strength < 0:
        score -= 1.0
        reasons.append(structure.get("structure", "Weak structure"))

    if structure.get("breakout") == "Bullish breakout":
        score += 1.25
        reasons.append("Bullish breakout confirmed")
    elif structure.get("breakout") == "Bearish breakdown":
        score -= 1.5
        reasons.append("Bearish breakdown detected")

    if "Bearish" in pattern_text or "Breakdown" in pattern_text or "Distribution" in pattern_text:
        score -= 1.0
        reasons.append("Pattern risk is bearish")
    elif "Bullish" in pattern_text or "Breakout" in pattern_text or "Ascending" in pattern_text:
        score += 0.75
        reasons.append("Pattern supports upside")

    if fundamentals:
        score += min(fundamentals.get("score", 0), 4) * 0.25

    if risk_plan.get("risk_reward", 0) >= 2:
        score += 1.25
        reasons.append("Risk-reward is at least 1:2")
    elif risk_plan.get("risk_reward", 0) >= 1.3:
        score += 0.25
        reasons.append("Risk-reward is acceptable but not ideal")
    else:
        score -= 2.0
        reasons.append("Risk-reward is poor")

    if risk_plan.get("atr_pct", 0) > 6 and structure.get("breakout") != "Bullish breakout":
        score -= 1.5
        reasons.append("Volatility is high without breakout confirmation")

    risk_gate = risk_plan.get("risk_reward", 0) >= 1.3 and risk_plan.get("atr_pct", 0) <= 8
    trend_gate = trend != "Downtrend"

    if not forecast_gate or not trend_gate or not risk_gate:
        decision = "AVOID" if score < 3 else "HOLD"
    elif score >= 6.5:
        decision = "BUY"
    elif score >= 4.0:
        decision = "HOLD"
    else:
        decision = "AVOID"

    confidence = int(max(5, min(95, 45 + (score * 6))))

    return {
        "decision": decision,
        "confidence": confidence,
        "score": round(score, 2),
        "reasons": reasons[:8]
    }
