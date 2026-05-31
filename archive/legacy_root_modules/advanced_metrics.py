import numpy as np
import pandas as pd


def calculate_sharpe_ratio(returns, risk_free_rate=0.02):

    mean_return = returns.mean()
    std_dev = returns.std()

    sharpe = (mean_return - risk_free_rate / 252) / std_dev

    return sharpe.mean()


def calculate_max_drawdown(prices):

    cumulative_max = prices.cummax()
    drawdown = (prices - cumulative_max) / cumulative_max

    return drawdown.min().min()


def calculate_diversification_score(returns):

    correlation = returns.corr().abs()

    # ignore diagonal
    avg_corr = (correlation.values.sum() - len(correlation)) / (len(correlation)**2 - len(correlation))

    score = 1 - avg_corr

    return score


def calculate_risk_score(volatility):

    avg_vol = volatility.mean()

    if avg_vol < 0.15:
        return "Low Risk 🟢"
    elif avg_vol < 0.25:
        return "Moderate Risk 🟡"
    else:
        return "High Risk 🔴"