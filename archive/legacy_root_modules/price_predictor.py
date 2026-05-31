import numpy as np

def predict_future(prices):

    prices = prices.dropna().values

    if len(prices) < 10:
        return float(prices[-1]), "HOLD"

    short_ma = np.mean(prices[-5:])
    long_ma = np.mean(prices[-20:])

    current_price = prices[-1]

    trend = short_ma - long_ma

    predicted_price = current_price + trend

    if predicted_price > current_price * 1.02:
        signal = "BUY"
    elif predicted_price < current_price * 0.98:
        signal = "SELL"
    else:
        signal = "HOLD"

    return float(predicted_price), signal