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


def _model_result(name, score, uncertainty, reasons, factors, edge=0, fit_reason=""):
    probability = int(_bounded(score, 5, 94))
    uncertainty = int(_bounded(uncertainty, 7, 38))
    return {
        "name": name,
        "probability": probability,
        "uncertainty": uncertainty,
        "confidence_level": _confidence_level(probability, uncertainty),
        "edge": round(edge, 2),
        "fit_reason": fit_reason,
        "reasons": reasons[:5],
        "factors": factors[:6],
    }


def _add(factors, name, weight, explanation):
    factors.append({
        "factor": name,
        "weight": round(weight, 2),
        "direction": "Positive" if weight > 0 else "Negative" if weight < 0 else "Neutral",
        "explanation": explanation,
    })
    return weight


def _build_candidate_models(trend, prediction, volume_info, structure, risk_plan, patterns, fundamentals, sentiment):
    expected = float(prediction.get("expected_return_pct", 0) or 0)
    rr = float(risk_plan.get("risk_reward", 0) or 0)
    atr_pct = float(risk_plan.get("atr_pct", 0) or 0)
    fund_score = float((fundamentals or {}).get("score", 50) or 50)
    volume_score = float(volume_info.get("score", 0) or 0)
    volume_ratio = float(volume_info.get("ratio", 1) or 1)
    bullish_patterns = sum(item.get("confidence", 0) for item in patterns or [] if item.get("direction") == "Bullish")
    bearish_patterns = sum(item.get("confidence", 0) for item in patterns or [] if item.get("direction") == "Bearish")
    pattern_edge = (bullish_patterns - bearish_patterns) / 10
    sentiment_score = float((sentiment or {}).get("score", 0) or 0)
    trend_score = 14 if trend == "Uptrend" else -14 if trend == "Downtrend" else 0
    breakout_score = 10 if structure.get("breakout") == "Bullish breakout" else -12 if structure.get("breakout") == "Bearish breakdown" else 0
    structure_score = float(structure.get("strength", 0) or 0) * 7

    models = []

    factors = []
    score = 50
    score += _add(factors, "Prior quality", (fund_score - 50) * 0.20, "Fundamental base rate adjusts the neutral prior")
    score += _add(factors, "Forecast likelihood", max(min(expected * 2.4, 16), -18), "Forecast edge changes posterior odds")
    score += _add(factors, "Trend evidence", trend_score * 0.65, "Trend informs directional prior")
    score += _add(factors, "Risk-reward odds", min(rr, 3) * 5 - 5, "Payoff profile improves or weakens expected value")
    score += _add(factors, "Sentiment evidence", max(min(sentiment_score * 2, 6), -6), "News sentiment is a secondary likelihood factor")
    models.append(_model_result(
        "Bayesian Quality Prior",
        score,
        17 + max(0, 50 - fund_score) / 6 + max(0, atr_pct - 5),
        [item["explanation"] for item in factors],
        factors,
        edge=abs(fund_score - 50) + abs(expected),
        fit_reason="Best when fundamentals and forecast edge are reliable."
    ))

    factors = []
    score = 48
    score += _add(factors, "Trend momentum", trend_score, "Price is rewarded for sustained trend alignment")
    score += _add(factors, "20/30 day upside", max(min(expected * 2.8, 18), -16), "Expected return drives momentum probability")
    score += _add(factors, "Volume participation", max(min(volume_score * 5 + (volume_ratio - 1) * 7, 12), -10), "Volume confirms or rejects the move")
    score += _add(factors, "Breakout state", breakout_score, "Breakouts increase continuation odds")
    score += _add(factors, "Pattern edge", max(min(pattern_edge, 10), -10), "Detected patterns adjust tactical momentum")
    models.append(_model_result(
        "Momentum Weighted Model",
        score,
        16 + (6 if trend == "Sideways" else 0) + max(0, atr_pct - 6),
        [item["explanation"] for item in factors],
        factors,
        edge=abs(trend_score) + max(expected, 0) + abs(volume_score * 3),
        fit_reason="Best when trend, volume, and breakout structure dominate the setup."
    ))

    factors = []
    score = 52
    volatility_penalty = max(0, atr_pct - 3.5) * 3.4
    score += _add(factors, "Risk-reward after volatility", min(rr, 3) * 9 - volatility_penalty, "ATR-adjusted payoff quality is central")
    score += _add(factors, "Forecast after volatility", max(min(expected * 2, 12), -14) - max(0, atr_pct - 7), "Forecast is discounted under high volatility")
    score += _add(factors, "Structure protection", structure_score, "Support/resistance structure improves risk control")
    score += _add(factors, "Fundamental stability", (fund_score - 50) * 0.12, "Higher quality reduces volatility risk")
    models.append(_model_result(
        "Volatility Adjusted Model",
        score,
        14 + max(0, atr_pct - 4) * 1.8,
        [item["explanation"] for item in factors],
        factors,
        edge=rr * 12 + max(0, 8 - atr_pct),
        fit_reason="Best when risk control and ATR conditions are the deciding variables."
    ))

    factors = []
    score = 50
    score += _add(factors, "Trend continuation", trend_score * 1.05, "Continuation assumes existing trend persists")
    score += _add(factors, "Market structure", structure_score, "Higher highs/lows improve persistence")
    score += _add(factors, "Breakout confirmation", breakout_score * 0.80, "Breakout or breakdown modifies continuation")
    score += _add(factors, "Pattern continuation", max(min(pattern_edge, 8), -8), "Pattern context supports or rejects continuation")
    models.append(_model_result(
        "Trend Continuation Model",
        score,
        18 + (7 if trend == "Sideways" else 0),
        [item["explanation"] for item in factors],
        factors,
        edge=abs(trend_score) + abs(structure_score),
        fit_reason="Best when trend persistence and structure clarity are high."
    ))

    factors = []
    score = 50
    score += _add(factors, "Technical confidence", trend_score * 0.70 + breakout_score * 0.55, "Trend and breakout drive technical confidence")
    score += _add(factors, "RS and volume proxy", max(min(volume_ratio * 5, 10), 0), "Relative participation improves confirmation")
    score += _add(factors, "Historical pattern probability", max(min(pattern_edge, 12), -12), "Pattern history changes the setup odds")
    score += _add(factors, "Quality overlay", (fund_score - 50) * 0.10, "Quality is a stabilizing overlay")
    models.append(_model_result(
        "Technical Confidence Model",
        score,
        19 + max(0, atr_pct - 5),
        [item["explanation"] for item in factors],
        factors,
        edge=abs(pattern_edge) + abs(breakout_score) + volume_ratio,
        fit_reason="Best when chart patterns, volume, and technical state are most informative."
    ))

    return models


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
    candidate_models = _build_candidate_models(trend, prediction, volume_info, structure, risk_plan, patterns, fundamentals, sentiment)
    probabilities = [item["probability"] for item in candidate_models]
    agreement = 100 - (max(probabilities) - min(probabilities)) if probabilities else 0
    atr_pct = risk_plan.get("atr_pct", 0)

    def selector(model):
        volatility_fit = 12 if ("Volatility" in model["name"] and atr_pct >= 5) else 0
        momentum_fit = 10 if ("Momentum" in model["name"] and trend == "Uptrend") else 0
        quality_fit = 8 if ("Bayesian" in model["name"] and (fundamentals or {}).get("score", 50) >= 62) else 0
        continuation_fit = 8 if ("Continuation" in model["name"] and trend != "Sideways") else 0
        uncertainty_penalty = model["uncertainty"] * 0.7
        return model["edge"] + volatility_fit + momentum_fit + quality_fit + continuation_fit - uncertainty_penalty

    selected = max(candidate_models, key=selector) if candidate_models else None

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

    legacy_probability = int(_bounded(score, 5, 92))
    probability = int(round((selected["probability"] * 0.72) + (legacy_probability * 0.28))) if selected else legacy_probability
    uncertainty = int(_bounded(uncertainty + max(0, 60 - probability) / 4, 8, 35))
    if selected:
        uncertainty = int(_bounded((selected["uncertainty"] * 0.68) + (uncertainty * 0.32), 7, 36))

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
    model_name = selected["name"] if selected else "Bayesian Momentum Ensemble"
    model_description = (
        "A weighted ensemble that starts from a neutral prior, then adjusts confidence using forecast edge, "
        "trend, volume, market structure, patterns, risk-reward, volatility, fundamentals, and sentiment."
    )
    selected_reason = selected["fit_reason"] if selected else "Selected because the setup combines directional momentum, volatility-adjusted risk, and multi-factor AI scoring."

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
        "model_agreement": round(max(0, min(100, agreement)), 2),
        "models_compared": candidate_models,
        "selected_model_score": round(selector(selected), 2) if selected else 0,
        "factors": sorted(factors, key=lambda item: abs(item["weight"]), reverse=True)[:8]
    }
