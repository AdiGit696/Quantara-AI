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
    reasons = []
    expected_return = prediction.get("expected_return_pct", 0.0)
    predicted_price = prediction.get("future_30", current_price)

    technical = 50.0
    if trend == "Uptrend":
        technical += 18
        reasons.append("Daily and weekly trend align upward")
    elif trend == "Sideways":
        technical += 4
        reasons.append("Trend is sideways but not broken")
    else:
        technical -= 16
        reasons.append("Trend is down")

    if 45 <= rsi <= 68:
        technical += 8
        reasons.append("RSI is in a constructive swing zone")
    elif rsi < 35:
        technical += 3
        reasons.append("RSI is oversold; confirmation still matters")
    elif rsi > 74:
        technical -= 8
        reasons.append("RSI is overheated")

    if macd_val > macd_signal:
        technical += 7
        reasons.append("MACD is bullish")
    else:
        technical -= 4
        reasons.append("MACD is not bullish")

    technical += float(volume_info.get("score", 0.0) or 0) * 6
    reasons.append(volume_info.get("label", "Volume unavailable"))

    structure_strength = float(structure.get("strength", 0) or 0)
    technical += structure_strength * 7
    if structure.get("breakout") == "Bullish breakout":
        technical += 10
        reasons.append("Bullish breakout confirmed")
    elif structure.get("breakout") == "Bearish breakdown":
        technical -= 12
        reasons.append("Bearish breakdown detected")

    if "Bearish" in pattern_text or "Breakdown" in pattern_text or "Distribution" in pattern_text:
        technical -= 6
        reasons.append("Pattern risk is bearish")
    elif "Bullish" in pattern_text or "Breakout" in pattern_text or "Ascending" in pattern_text:
        technical += 5
        reasons.append("Pattern supports upside")

    fund_score = float((fundamentals or {}).get("score", 50) or 50)
    momentum = 50.0
    if predicted_price >= current_price and expected_return > 0:
        momentum += min(expected_return * 4.5, 30)
        reasons.append(f"30d forecast upside {expected_return:.1f}%")
    else:
        momentum -= 12
        reasons.append("Forecast is not positive")
    momentum += 8 if trend == "Uptrend" else -8 if trend == "Downtrend" else 0
    momentum += min(max((volume_info.get("ratio", 1) - 1) * 10, -8), 10)

    risk = 55.0
    if risk_plan.get("risk_reward", 0) >= 2:
        risk += 18
        reasons.append("Risk-reward is at least 1:2")
    elif risk_plan.get("risk_reward", 0) >= 1.8:
        risk += 10
        reasons.append("Risk-reward meets the minimum 1:1.8 rule")
    else:
        risk -= 22
        reasons.append("Risk-reward is below the minimum rule")

    risk -= min(float(risk_plan.get("risk_pct", 0) or 0), 12) * 1.8
    if risk_plan.get("atr_pct", 0) > 6:
        risk -= 8
        reasons.append("Volatility is elevated")
    if not risk_plan.get("is_tradeable", True):
        risk -= 18
        reasons.append(risk_plan.get("rejection_reason") or "Risk setup is not tradeable")

    sentiment = 50.0
    master_score = (
        max(0, min(100, technical)) * 0.30
        + max(0, min(100, fund_score)) * 0.25
        + max(0, min(100, momentum)) * 0.20
        + max(0, min(100, risk)) * 0.15
        + sentiment * 0.10
    )

    if expected_return >= 8 and trend != "Downtrend" and risk_plan.get("risk_reward", 0) >= 1.8:
        master_score = max(master_score, 66)
        reasons.append("Strong expected return lifts the setup above neutral bias")

    severe_risk = risk_plan.get("risk_reward", 0) < 1.2 or (trend == "Downtrend" and risk_plan.get("atr_pct", 0) > 7)
    if severe_risk or not risk_plan.get("is_tradeable", True):
        decision = "AVOID"
    elif master_score >= 80:
        decision = "STRONG BUY"
    elif master_score >= 65:
        decision = "BUY"
    elif master_score >= 50:
        decision = "HOLD"
    else:
        decision = "AVOID"

    confidence = int(max(5, min(95, master_score)))

    return {
        "decision": decision,
        "confidence": confidence,
        "score": round(master_score, 2),
        "master_score": round(master_score, 2),
        "score_components": {
            "technical": round(max(0, min(100, technical)), 2),
            "fundamentals": round(max(0, min(100, fund_score)), 2),
            "momentum": round(max(0, min(100, momentum)), 2),
            "risk": round(max(0, min(100, risk)), 2),
            "sentiment": round(sentiment, 2),
        },
        "reasons": reasons[:8]
    }
