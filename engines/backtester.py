import math

import numpy as np
import pandas as pd

from engines.advanced_patterns import detect_advanced_patterns
from engines.data_service import get_price_history
from engines.price_predictor import predict_prices
from engines.probability_engine import score_trade_probability
from engines.risk_engine import calculate_trade_plan
from engines.technical_engine import (
    atr,
    calculate_rsi,
    macd,
    market_structure,
    multi_timeframe_trend,
    volume_strength
)


def _max_drawdown(values):
    if not values:
        return 0
    peak = values[0]
    max_dd = 0
    for value in values:
        peak = max(peak, value)
        if peak:
            max_dd = min(max_dd, (value - peak) / peak)
    return abs(max_dd) * 100


def _sharpe(returns):
    if len(returns) < 2:
        return 0
    std = np.std(returns)
    if std == 0:
        return 0
    return float((np.mean(returns) / std) * math.sqrt(12))


def _profit_factor(trade_returns):
    gains = sum(item for item in trade_returns if item > 0)
    losses = abs(sum(item for item in trade_returns if item < 0))
    if losses == 0:
        return round(gains, 2) if gains else 0
    return round(gains / losses, 2)


def _cagr(initial_capital, ending_capital, start_date, end_date):
    days = max((end_date - start_date).days, 1)
    years = days / 365.25
    if initial_capital <= 0 or ending_capital <= 0 or years <= 0:
        return 0
    return ((ending_capital / initial_capital) ** (1 / years) - 1) * 100


def _monthly_performance(trades):
    months = {}
    for trade in trades:
        month = str(trade.get("exit_date", ""))[:7]
        if not month:
            continue
        months.setdefault(month, []).append(float(trade.get("return_pct", 0) or 0))
    return [
        {
            "month": month,
            "trades": len(values),
            "avg_return_pct": round(sum(values) / len(values), 2),
            "win_rate": round(sum(1 for value in values if value > 0) / len(values) * 100, 2),
        }
        for month, values in sorted(months.items())
    ]


def _strategy_signal(window, risk_level="Balanced", min_confidence=62):
    close = window["Close"]
    weekly = close.resample("W").last().dropna()
    rsi = float(calculate_rsi(close).iloc[-1])
    macd_val, macd_signal = macd(close)
    atr_val = float(atr(window["High"], window["Low"], close))
    structure = market_structure(window)
    prediction = predict_prices(close)
    risk_plan = calculate_trade_plan(
        current_price=float(close.iloc[-1]),
        atr_value=atr_val,
        support=structure["support"],
        resistance=structure["resistance"],
        prediction=prediction
    )
    trend = multi_timeframe_trend(close, weekly)
    volume_info = volume_strength(close, window["Volume"])
    patterns = detect_advanced_patterns(window, lookback=160)

    probability = score_trade_probability(
        trend=trend,
        prediction=prediction,
        volume_info=volume_info,
        structure=structure,
        risk_plan=risk_plan,
        patterns=patterns,
        fundamentals={"score": 50},
        sentiment=None
    )

    strictness = {"Conservative": 66, "Balanced": min_confidence, "Aggressive": 54}.get(risk_level, min_confidence)
    bullish_pattern = any(item["direction"] == "Bullish" and item["confidence"] >= 60 for item in patterns)
    latest_close = float(close.iloc[-1])
    ema_fast = float(close.ewm(span=20, adjust=False).mean().iloc[-1])
    ema_slow = float(close.ewm(span=50, adjust=False).mean().iloc[-1])
    high_20 = float(window["High"].tail(21).iloc[:-1].max())
    pullback_entry = latest_close > ema_fast and ema_fast >= ema_slow and rsi >= 42
    breakout_entry = latest_close >= high_20 * 0.995 and rsi < 76
    tech_confidence = {"Conservative": 55, "Balanced": 45, "Aggressive": 30}.get(risk_level, 45)
    technical_entry = (
        pullback_entry
        and ((latest_close / float(close.iloc[-20])) - 1) > 0
        and rsi < 78
        and probability["trade_confidence"] >= tech_confidence
    )
    positive_setup = (
        probability["trade_confidence"] >= strictness
        and prediction["expected_return_pct"] > 0
        and risk_plan["risk_reward"] >= 1.05
        and trend != "Downtrend"
    )
    model_signal = positive_setup and (macd_val > macd_signal or bullish_pattern or pullback_entry or breakout_entry)
    signal = model_signal or technical_entry

    setup = "Breakout" if breakout_entry else "Trend pullback" if technical_entry else "Probability"
    return signal, risk_plan, probability, patterns, setup


def run_backtest(
    ticker,
    period="2y",
    initial_capital=10000,
    holding_days=20,
    risk_level="Balanced",
    min_confidence=62
):
    try:
        df = get_price_history(ticker, period=period)
    except Exception as exc:
        return _empty_backtest(ticker, initial_capital, f"Historical data could not be loaded: {exc}")

    if df.empty or len(df) < 140:
        return _empty_backtest(ticker, initial_capital, "Not enough historical candles to run this strategy.")

    capital = float(initial_capital)
    equity_curve = [{"date": df.index[120].date().isoformat(), "capital": capital}]
    trades = []
    trade_returns = []
    i = 120

    while i < len(df) - holding_days:
        window = df.iloc[:i].copy()
        try:
            signal, risk_plan, probability, patterns, setup = _strategy_signal(window, risk_level, min_confidence)
        except Exception:
            i += 1
            continue

        if not signal:
            i += 1
            continue

        entry_price = float(df["Close"].iloc[i])
        stop_loss = risk_plan["stop_loss"]
        target = risk_plan["target"]
        atr_buffer = float(atr(window["High"], window["Low"], window["Close"]))
        if stop_loss >= entry_price:
            stop_loss = entry_price - max(atr_buffer, entry_price * 0.025)
        if target <= entry_price:
            target = entry_price + max(atr_buffer * 1.7, entry_price * 0.035)
        exit_price = float(df["Close"].iloc[i + holding_days])
        exit_date = df.index[i + holding_days]
        exit_reason = "time exit"

        forward = df.iloc[i + 1:i + holding_days + 1]
        for index, row in forward.iterrows():
            if row["Low"] <= stop_loss:
                exit_price = float(stop_loss)
                exit_date = index
                exit_reason = "stop loss"
                break
            if row["High"] >= target:
                exit_price = float(target)
                exit_date = index
                exit_reason = "target"
                break

        trade_return = ((exit_price / entry_price) - 1) * 100
        capital *= 1 + (trade_return / 100)
        trade_returns.append(trade_return)
        equity_curve.append({"date": exit_date.date().isoformat(), "capital": round(capital, 2)})

        trades.append({
            "entry_date": df.index[i].date().isoformat(),
            "exit_date": exit_date.date().isoformat(),
            "entry": round(entry_price, 2),
            "exit": round(exit_price, 2),
            "exit_reason": exit_reason,
            "return_pct": round(trade_return, 2),
            "confidence": probability["trade_confidence"],
            "setup": setup,
            "top_pattern": patterns[0]["name"] if patterns else "None"
        })

        i += max(holding_days // 2, 5)

    wins = [trade for trade in trades if trade["return_pct"] > 0]
    avg_return = sum(trade["return_pct"] for trade in trades) / len(trades) if trades else 0
    win_rate = (len(wins) / len(trades)) * 100 if trades else 0
    roi = ((capital / initial_capital) - 1) * 100 if initial_capital else 0
    best_trade = max(trades, key=lambda item: item["return_pct"]) if trades else None
    worst_trade = min(trades, key=lambda item: item["return_pct"]) if trades else None
    cagr = _cagr(initial_capital, capital, df.index[120].date(), df.index[-1].date())
    strategy_confidence = max(0, min(100, (win_rate * 0.45) + (max(0, roi) * 0.35) + (max(0, _profit_factor(trade_returns)) * 8) - (_max_drawdown([item["capital"] for item in equity_curve]) * 0.5)))

    status = "ok" if trades else "no_trades"
    message = "Backtest completed." if trades else "No valid entries matched the selected risk settings in this period."

    return {
        "status": status,
        "message": message,
        "trades": trades,
        "equity_curve": equity_curve,
        "summary": {
            "ticker": ticker,
            "total_trades": len(trades),
            "win_rate": round(win_rate, 2),
            "roi": round(roi, 2),
            "total_return": round(roi, 2),
            "cagr": round(cagr, 2),
            "avg_return": round(avg_return, 2),
            "max_drawdown": round(_max_drawdown([item["capital"] for item in equity_curve]), 2),
            "sharpe": round(_sharpe(trade_returns), 2),
            "profit_factor": _profit_factor(trade_returns),
            "ending_capital": round(capital, 2),
            "best_trade": best_trade,
            "worst_trade": worst_trade,
            "strategy_confidence": round(strategy_confidence, 2),
        },
        "monthly_performance": _monthly_performance(trades),
    }


def _empty_backtest(ticker, initial_capital, message):
    return {
        "status": "no_data",
        "message": message,
        "trades": [],
        "equity_curve": [{"date": pd.Timestamp.today().date().isoformat(), "capital": float(initial_capital)}],
        "summary": {
            "ticker": ticker,
            "total_trades": 0,
            "win_rate": 0,
            "roi": 0,
            "total_return": 0,
            "cagr": 0,
            "avg_return": 0,
            "max_drawdown": 0,
            "sharpe": 0,
            "profit_factor": 0,
            "ending_capital": float(initial_capital),
            "best_trade": None,
            "worst_trade": None,
            "strategy_confidence": 0,
        },
        "monthly_performance": [],
    }


def compare_strategies(ticker, initial_capital=10000):
    rows = []
    for risk_level in ["Conservative", "Balanced", "Aggressive"]:
        result = run_backtest(ticker, initial_capital=initial_capital, risk_level=risk_level)
        rows.append({"strategy": risk_level, **result["summary"]})
    return pd.DataFrame(rows)


def monte_carlo_projection(trade_returns, simulations=250, initial_capital=10000):
    if not trade_returns:
        return {"p05": initial_capital, "p50": initial_capital, "p95": initial_capital}

    outcomes = []
    returns = np.array(trade_returns) / 100
    for _ in range(simulations):
        sampled = np.random.choice(returns, size=len(returns), replace=True)
        capital = initial_capital * float(np.prod(1 + sampled))
        outcomes.append(capital)

    return {
        "p05": round(float(np.percentile(outcomes, 5)), 2),
        "p50": round(float(np.percentile(outcomes, 50)), 2),
        "p95": round(float(np.percentile(outcomes, 95)), 2)
    }


def backtest_ticker(ticker, period="2y", initial_capital=10000, holding_days=20):
    return run_backtest(ticker, period=period, initial_capital=initial_capital, holding_days=holding_days)
