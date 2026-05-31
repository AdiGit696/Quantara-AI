def calculate_trade_plan(current_price, atr_value, support=None, resistance=None, prediction=None, multiplier=1.5, min_rr=1.8, max_risk_pct=8.0):
    prediction = prediction or {}
    if not current_price or not atr_value or atr_value <= 0:
        return {
            "entry": current_price,
            "stop_loss": current_price,
            "target": current_price,
            "risk_reward": 0.0,
            "risk_pct": 0.0,
            "atr_pct": 0.0,
            "risk_label": "Unknown",
            "is_tradeable": False,
            "rejection_reason": "ATR unavailable"
        }

    entry = float(current_price)
    atr_value = float(atr_value)
    atr_pct = (atr_value / entry) * 100 if entry else 0.0

    effective_multiplier = float(multiplier)
    max_risk_amount = entry * (max_risk_pct / 100)
    if atr_value * effective_multiplier > max_risk_amount and atr_value > 0:
        effective_multiplier = max(0.85, max_risk_amount / atr_value)

    stop_loss = entry - (atr_value * effective_multiplier)
    risk = max(entry - stop_loss, 0)
    target = entry + (risk * min_rr)
    reward = max(target - entry, 0)
    risk_reward = reward / risk if risk else 0.0
    risk_pct = (risk / entry) * 100 if entry else 0.0

    forecast_target = float(prediction.get("future_30", entry) or entry)
    expected_return = float(prediction.get("expected_return_pct", ((forecast_target / entry) - 1) * 100 if entry else 0) or 0)
    forecast_reward = max(forecast_target - entry, 0)
    forecast_rr = forecast_reward / risk if risk else 0.0
    resistance_rr = (max(float(resistance or 0) - entry, 0) / risk) if risk and resistance else 0.0
    setup_rr = max(forecast_rr, resistance_rr, risk_reward if expected_return >= ((target / entry) - 1) * 100 else 0)

    rejection_reason = ""
    if risk_reward < min_rr:
        rejection_reason = "Risk-reward below minimum"
    elif risk_pct > max_risk_pct:
        rejection_reason = "Stop loss exceeds maximum ATR risk"
    elif atr_pct > 8.5 and expected_return < 4:
        rejection_reason = "Volatility is too high for the expected return"
    elif setup_rr < min_rr and expected_return < ((target / entry) - 1) * 100:
        rejection_reason = "Forecast upside does not justify ATR risk"

    if atr_pct > 6:
        risk_label = "High volatility"
    elif risk_reward >= 2 and risk_pct <= max_risk_pct:
        risk_label = "Favorable"
    elif risk_reward >= min_rr:
        risk_label = "Acceptable"
    else:
        risk_label = "Poor"

    return {
        "entry": float(entry),
        "stop_loss": float(stop_loss),
        "target": float(target),
        "risk_reward": float(risk_reward),
        "risk_pct": float(risk_pct),
        "atr_pct": float(atr_pct),
        "atr_multiplier": float(effective_multiplier),
        "forecast_rr": float(forecast_rr),
        "resistance_rr": float(resistance_rr),
        "risk_label": risk_label,
        "is_tradeable": not bool(rejection_reason),
        "rejection_reason": rejection_reason
    }
