from engines.advanced_patterns import detect_advanced_patterns, pattern_summary
from engines.data_service import get_price_history, get_weekly_close
from engines.technical_engine import *
from engines.fundamental_analyzer import analyze_fundamentals
from engines.price_predictor import predict_prices
from engines.risk_engine import calculate_trade_plan
from engines.decision_engine import evaluate_decision
from engines.news_engine import aggregate_news_sentiment, get_news
from engines.probability_engine import score_trade_probability


def analyze_stock(ticker):
    df = get_price_history(ticker, period="1y")
    weekly_close = get_weekly_close(ticker, period="2y")

    if df.empty:
        raise Exception("No data")

    close = df["Close"]
    volume = df["Volume"]

    # TECHNICAL
    rsi_series = calculate_rsi(close)
    rsi = rsi_series.iloc[-1]

    ma = moving_average(close).iloc[-1]
    mom = momentum(close).iloc[-1]

    macd_val, macd_signal = macd(close)

    vwap_val = vwap(df).iloc[-1]

    atr_val = atr(df["High"], df["Low"], close)

    bb_mid, bb_upper, bb_lower = bollinger_bands(close)

    vol_info = volume_strength(close, volume)

    trend = multi_timeframe_trend(close, weekly_close)

    divergence = rsi_divergence(close, rsi_series)

    structure = market_structure(df)
    support = structure["support"]
    resistance = structure["resistance"]
    zone = structure["zone"]

    patterns = detect_advanced_patterns(df)
    pattern_overview = pattern_summary(patterns)
    pattern_text = ", ".join([item["name"] for item in patterns[:5]])

    # FUNDAMENTALS
    fundamentals = analyze_fundamentals(ticker)

    # PREDICTION
    prediction = predict_prices(close)

    risk_plan = calculate_trade_plan(
        current_price=float(close.iloc[-1]),
        atr_value=float(atr_val),
        support=float(support),
        resistance=float(resistance),
        prediction=prediction
    )

    decision_result = evaluate_decision(
        current_price=float(close.iloc[-1]),
        rsi=float(rsi),
        macd_val=float(macd_val),
        macd_signal=float(macd_signal),
        trend=trend,
        prediction=prediction,
        volume_info=vol_info,
        structure=structure,
        risk_plan=risk_plan,
        pattern_text=pattern_text,
        fundamentals=fundamentals
    )

    news_items = get_news(ticker)
    sentiment = aggregate_news_sentiment(news_items)
    probability = score_trade_probability(
        trend=trend,
        prediction=prediction,
        volume_info=vol_info,
        structure=structure,
        risk_plan=risk_plan,
        patterns=patterns,
        fundamentals=fundamentals,
        sentiment=sentiment
    )

    return {
        "price": close.iloc[-1],
        "rsi": rsi,
        "trend": trend,
        "volume": vol_info["label"],
        "volume_ratio": vol_info["ratio"],
        "zone": zone,
        "support": support,
        "resistance": resistance,
        "breakout": structure["breakout"],
        "structure": structure["structure"],
        "consolidation": structure["consolidation"],
        "pattern": pattern_text,
        "patterns": patterns,
        "pattern_overview": pattern_overview,
        "fundamentals": fundamentals,
        "bb_upper": bb_upper,
        "bb_lower": bb_lower,
        "macd": macd_val,
        "macd_signal": macd_signal,
        "vwap": vwap_val,
        "atr": atr_val,
        "divergence": divergence,
        "future_15": prediction["future_15"],
        "future_30": prediction["future_30"],
        "prediction_direction": prediction["direction"],
        "expected_return_pct": prediction["expected_return_pct"],
        "prediction_confidence": prediction["confidence"],
        "prediction_method": prediction["method"],
        "stop_loss": risk_plan["stop_loss"],
        "target": risk_plan["target"],
        "risk_reward": risk_plan["risk_reward"],
        "risk_pct": risk_plan["risk_pct"],
        "atr_pct": risk_plan["atr_pct"],
        "risk_label": risk_plan["risk_label"],
        "confidence": decision_result["confidence"],
        "decision": decision_result["decision"],
        "decision_score": decision_result["score"],
        "decision_reasons": decision_result["reasons"],
        "trade_confidence": probability["trade_confidence"],
        "uncertainty": probability["uncertainty"],
        "risk_level": probability["risk_level"],
        "holding_period": probability["holding_period"],
        "probability_reasons": probability["reasons"],
        "probability_model": probability,
        "news": news_items,
        "sentiment": sentiment,
        "history": df
    }
