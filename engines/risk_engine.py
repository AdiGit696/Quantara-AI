def calculate_trade_plan(current_price, atr_value, support, resistance, prediction):
    if not current_price or not atr_value:
        return {
            "entry": current_price,
            "stop_loss": current_price,
            "target": current_price,
            "risk_reward": 0.0,
            "risk_pct": 0.0,
            "risk_label": "Unknown"
        }

    atr_stop = current_price - (1.5 * atr_value)
    support_stop = support * 0.98 if support else atr_stop
    stop_loss = min(atr_stop, support_stop)

    forecast_target = prediction.get("future_30", current_price)
    resistance_target = resistance * 0.99 if resistance else forecast_target
    target = max(forecast_target, resistance_target)

    risk = max(current_price - stop_loss, 0)
    reward = max(target - current_price, 0)
    risk_reward = reward / risk if risk else 0.0
    risk_pct = (risk / current_price) * 100 if current_price else 0.0
    atr_pct = (atr_value / current_price) * 100 if current_price else 0.0

    if atr_pct > 6:
        risk_label = "High volatility"
    elif risk_reward >= 2 and risk_pct <= 8:
        risk_label = "Favorable"
    elif risk_reward >= 1.3:
        risk_label = "Acceptable"
    else:
        risk_label = "Poor"

    return {
        "entry": float(current_price),
        "stop_loss": float(stop_loss),
        "target": float(target),
        "risk_reward": float(risk_reward),
        "risk_pct": float(risk_pct),
        "atr_pct": float(atr_pct),
        "risk_label": risk_label
    }
