import numpy as np


def _annualized_volatility(returns):
    if len(returns) < 20:
        return 0.0
    return float(returns.tail(30).std() * np.sqrt(252))


def _rolling_log_slope(prices, window):
    recent = prices.tail(window).dropna()
    if len(recent) < max(10, window // 2):
        return 0.0

    y = np.log(recent.values)
    x = np.arange(len(y))
    slope, _ = np.polyfit(x, y, 1)
    return float(slope)


def _forecast_from_slope(current_price, daily_log_slope, days):
    return float(current_price * np.exp(daily_log_slope * days))


def predict_prices(close_prices):
    """
    Lightweight swing forecast.

    This is intentionally not a high-variance ML model. It blends short and
    medium rolling log-price slopes, damps the forecast when volatility is high,
    and reports confidence separately from direction.
    """
    prices = close_prices.dropna()

    if len(prices) < 40:
        current = float(prices.iloc[-1]) if len(prices) else 0.0
        return {
            "future_15": current,
            "future_30": current,
            "direction": "NEUTRAL",
            "expected_return_pct": 0.0,
            "confidence": 20,
            "daily_slope": 0.0,
            "volatility": 0.0,
            "method": "insufficient history"
        }

    current = float(prices.iloc[-1])
    returns = prices.pct_change().dropna()

    short_slope = _rolling_log_slope(prices, 20)
    medium_slope = _rolling_log_slope(prices, 60)
    long_slope = _rolling_log_slope(prices, min(120, len(prices)))

    raw_slope = (0.50 * short_slope) + (0.35 * medium_slope) + (0.15 * long_slope)

    volatility = _annualized_volatility(returns)
    volatility_damper = max(0.35, 1 - min(volatility, 0.80))
    daily_slope = raw_slope * volatility_damper

    future_15 = _forecast_from_slope(current, daily_slope, 15)
    future_30 = _forecast_from_slope(current, daily_slope, 30)
    expected_return_pct = ((future_30 / current) - 1) * 100 if current else 0.0

    if expected_return_pct > 2.0:
        direction = "UP"
    elif expected_return_pct < -2.0:
        direction = "DOWN"
    else:
        direction = "NEUTRAL"

    slope_agreement = sum([
        short_slope > 0,
        medium_slope > 0,
        long_slope > 0
    ])
    if direction == "DOWN":
        slope_agreement = 3 - slope_agreement

    confidence = 35 + (slope_agreement * 12)
    confidence += min(abs(expected_return_pct) * 2, 20)
    confidence -= min(volatility * 35, 25)
    confidence = int(max(15, min(confidence, 85)))

    return {
        "future_15": future_15,
        "future_30": future_30,
        "direction": direction,
        "expected_return_pct": float(expected_return_pct),
        "confidence": confidence,
        "daily_slope": float(daily_slope),
        "volatility": float(volatility),
        "method": "hybrid rolling trend"
    }
