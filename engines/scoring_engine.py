def clamp(value, low=0, high=100):
    return max(low, min(high, float(value or 0)))


def risk_score_from_metrics(risk_pct=0, atr_pct=0, risk_reward=0, fundamental_score=50):
    score = 78
    score -= clamp(risk_pct, 0, 20) * 1.6
    score -= clamp(atr_pct, 0, 15) * 2.4
    score += min(float(risk_reward or 0), 3) * 6
    score += (float(fundamental_score or 50) - 50) * 0.18
    return round(clamp(score), 2)


def decision_score_from_metrics(confidence=0, risk_score=50, fundamental_score=50, expected_return_pct=0, risk_reward=0, trend="Sideways"):
    trend_bonus = 8 if trend == "Uptrend" else -10 if trend == "Downtrend" else 0
    score = (
        clamp(confidence) * 0.36
        + clamp(risk_score) * 0.22
        + clamp(fundamental_score) * 0.20
        + clamp(max(float(expected_return_pct or 0), 0) * 8, 0, 100) * 0.12
        + clamp(float(risk_reward or 0) * 35, 0, 100) * 0.10
        + trend_bonus
    )
    return round(clamp(score), 2)


def build_scorecard(
    probability=50,
    uncertainty=25,
    risk_pct=0,
    atr_pct=0,
    risk_reward=0,
    fundamental_score=50,
    expected_return_pct=0,
    trend="Sideways",
    momentum_score=None,
    sentiment_score=50,
):
    confidence = round(clamp(probability - max(0, uncertainty - 18) * 0.55), 2)
    risk = risk_score_from_metrics(risk_pct, atr_pct, risk_reward, fundamental_score)
    technical = decision_score_from_metrics(confidence, risk, fundamental_score, expected_return_pct, risk_reward, trend)
    expected_boost = clamp(max(float(expected_return_pct or 0), 0) * 9, 0, 100)
    trend_bias = 10 if trend == "Uptrend" else -8 if trend == "Downtrend" else 0
    momentum = clamp(momentum_score if momentum_score is not None else (confidence * 0.50 + expected_boost * 0.35 + 50 * 0.15 + trend_bias))
    sentiment = clamp(sentiment_score)
    master = round(clamp(
        technical * 0.30
        + clamp(fundamental_score or 50) * 0.25
        + momentum * 0.20
        + risk * 0.15
        + sentiment * 0.10
    ), 2)
    return {
        "quantara_score": master,
        "ai_score": master,
        "confidence_score": confidence,
        "risk_score": risk,
        "decision_score": master,
        "technical_score": round(technical, 2),
        "fundamental_score": round(clamp(fundamental_score or 50), 2),
        "momentum_score": round(momentum, 2),
        "sentiment_score": round(sentiment, 2),
        "master_score": master,
    }


def recommendation_from_scores(scorecard, expected_return_pct=0, risk_reward=0, trend="Sideways", fundamentals=None, owned=False):
    fundamentals = fundamentals or {}
    fund_score = float(fundamentals.get("score", 50) or 50)
    confidence = scorecard["confidence_score"]
    risk_score = scorecard["risk_score"]
    master_score = scorecard.get("master_score", scorecard.get("quantara_score", scorecard.get("decision_score", 0)))
    expected = float(expected_return_pct or 0)
    rr = float(risk_reward or 0)

    severe_risk = risk_score < 30 or (fund_score < 32 and trend == "Downtrend")
    broken_setup = expected < -4 or rr < 1.0

    if owned and not (severe_risk and broken_setup):
        return "HOLD"
    if severe_risk and broken_setup:
        return "AVOID"
    if master_score >= 80 and confidence >= 58 and risk_score >= 42 and trend != "Downtrend" and rr >= 1.4:
        return "STRONG BUY"
    if master_score >= 70 and expected >= 0 and risk_score >= 38 and trend != "Downtrend" and rr >= 1.2:
        return "BUY"
    if master_score >= 55 and not severe_risk:
        return "HOLD"
    if master_score >= 40 and not severe_risk:
        return "WATCH"
    return "AVOID"
