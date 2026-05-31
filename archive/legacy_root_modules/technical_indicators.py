import pandas as pd
import numpy as np

def calculate_rsi(prices, period=14):
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def moving_average(prices, window=20):
    return prices.rolling(window).mean()


def momentum(prices, period=10):
    return prices.diff(period)


def generate_signal(prices):

    rsi = calculate_rsi(prices).iloc[-1]
    ma = moving_average(prices).iloc[-1]
    current = prices.iloc[-1]
    mom = momentum(prices).iloc[-1]

    if rsi < 30 and current > ma:
        return "BUY 🚀"
    elif rsi > 70 and current < ma:
        return "SELL 🔻"
    else:
        return "HOLD ⚖️"