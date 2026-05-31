import config
from engines.advanced_patterns import detect_advanced_patterns, pattern_summary
from engines.data_service import get_price_history, get_weekly_close, safe_info
from engines.formatting import detect_market
from engines.technical_engine import *
from engines.fundamental_analyzer import analyze_fundamentals
from engines.price_predictor import predict_prices
from engines.risk_engine import calculate_trade_plan
from engines.decision_engine import evaluate_decision
from engines.news_engine import aggregate_news_sentiment, get_news
from engines.probability_engine import score_trade_probability
from engines.scoring_engine import build_scorecard, recommendation_from_scores
from models.evaluation import record_prediction
from utils.numbers import latest_float, numeric_series
from utils.observability import log_symbol_failure, timed_operation


def _technical_summary(result):
    action = result.get("decision", "HOLD")
    invalidation = (
        f"A close below {result['stop_loss']:.2f} invalidates the swing setup."
        if isinstance(result.get("stop_loss"), (int, float))
        else "A breakdown below support invalidates the setup."
    )
    risk_statement = result.get("risk_label", "Risk unavailable")
    if result.get("risk_rejection"):
        risk_statement = f"{risk_statement}: {result['risk_rejection']}"
    return [
        f"Trend: {result['trend']} with price currently in the {result['zone'].lower()} area.",
        f"Momentum: RSI {float(result['rsi']):.1f}, MACD {'bullish' if result['macd'] > result['macd_signal'] else 'not bullish'}, expected 30d return {float(result['expected_return_pct']):.2f}%.",
        f"Support/resistance: support near {float(result['support']):.2f}, resistance near {float(result['resistance']):.2f}.",
        f"Pattern interpretation: {result.get('pattern_overview') or result.get('pattern') or 'No dominant pattern detected.'}",
        f"Volume strength: {result.get('volume', 'Unknown')} at {float(result.get('volume_ratio', 1)):.2f}x normal volume.",
        f"Risk statement: {risk_statement}; ATR volatility is {float(result.get('atr_pct', 0)):.2f}% and R:R is {float(result.get('risk_reward', 0)):.2f}.",
        f"Suggested action: {action} because {', '.join(result.get('decision_reasons', [])[:2]) or 'the multi-factor score is balanced.'}",
        f"Thesis invalidation: {invalidation}",
    ]


def analyze_stock(ticker):
    with timed_operation("stock_analysis", count=1):
        df = get_price_history(ticker, period="1y")
        weekly_close = get_weekly_close(ticker, period="2y")
        info = safe_info(ticker)

        if df.empty:
            log_symbol_failure("scan", ticker, "No price history available", category="stock_analysis_no_data")
            raise Exception("No price history available")

        close = numeric_series(df["Close"])
        high = numeric_series(df["High"]).reindex(close.index).dropna()
        low = numeric_series(df["Low"]).reindex(close.index).dropna()
        volume = numeric_series(df["Volume"]).reindex(close.index).fillna(0) if "Volume" in df else close * 0

        # TECHNICAL
        rsi_series = calculate_rsi(close)
        rsi = latest_float(rsi_series, 50.0)

        ma = latest_float(moving_average(close), latest_float(close, 0.0))
        mom = latest_float(momentum(close), 0.0)

        macd_val, macd_signal = macd(close)
        macd_val = float(macd_val)
        macd_signal = float(macd_signal)

        vwap_val = latest_float(vwap(df), latest_float(close, 0.0))

        atr_val = float(atr(high, low, close) or 0)

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

        news_items = get_news(ticker) if config.ENABLE_NEWS else []
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
        components = decision_result.get("score_components", {})
        scorecard = build_scorecard(
        probability=probability["trade_confidence"],
        uncertainty=probability["uncertainty"],
        risk_pct=risk_plan["risk_pct"],
        atr_pct=risk_plan["atr_pct"],
        risk_reward=risk_plan["risk_reward"],
        fundamental_score=fundamentals.get("score", 50),
        expected_return_pct=prediction["expected_return_pct"],
        trend=trend,
        momentum_score=components.get("momentum"),
        sentiment_score=50 + (sentiment.get("score", 0) * 8),
        )
        calibrated_decision = recommendation_from_scores(
        scorecard,
        expected_return_pct=prediction["expected_return_pct"],
        risk_reward=risk_plan["risk_reward"],
        trend=trend,
        fundamentals=fundamentals,
        )
        if not risk_plan.get("is_tradeable", True):
            severe_reasons = {"ATR unavailable", "Volatility is too high for the expected return"}
            calibrated_decision = "AVOID" if risk_plan.get("rejection_reason") in severe_reasons else "WATCH"
        prev_close = float(close.iloc[-2]) if len(close) > 1 else float(close.iloc[-1])
        day_change_pct = ((float(close.iloc[-1]) / prev_close) - 1) * 100 if prev_close else 0
        market = detect_market(ticker, info.get("exchange"), info.get("currency"))

        result = {
        "ticker": ticker,
        "company_name": info.get("longName") or info.get("shortName") or ticker.replace(".NS", "").replace(".BO", ""),
        "exchange": info.get("exchange") or ("NSE" if ticker.upper().endswith(".NS") else "BSE" if ticker.upper().endswith(".BO") else ""),
        "currency": market["currency"],
        "currency_symbol": market["symbol"],
        "metadata": info,
        "day_change_pct": day_change_pct,
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
        "risk_rejection": risk_plan.get("rejection_reason", ""),
        "is_tradeable": risk_plan.get("is_tradeable", True),
        "confidence": decision_result["confidence"],
        "decision": calibrated_decision,
        "legacy_decision": decision_result["decision"],
        "quantara_score": scorecard["quantara_score"],
        "decision_score": scorecard["decision_score"],
        "master_score": scorecard.get("master_score"),
        "technical_score": scorecard.get("technical_score"),
        "fundamental_score": scorecard.get("fundamental_score"),
        "momentum_score": scorecard.get("momentum_score"),
        "sentiment_score": scorecard.get("sentiment_score"),
        "ai_score": scorecard["ai_score"],
        "confidence_score": scorecard["confidence_score"],
        "risk_score": scorecard["risk_score"],
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
        result["technical_summary"] = _technical_summary(result)
        result["trust_explanation"] = [
            f"Why buy: {', '.join(result['decision_reasons'][:3]) if result['decision'] in {'BUY', 'STRONG BUY'} else 'Buy conditions are not fully aligned yet.'}",
            f"Why avoid: {result.get('risk_rejection') or 'Avoid only when trend, forecast, and risk quality deteriorate materially.'}",
            f"Confidence: master score {result.get('master_score', result.get('quantara_score')):.0f}/100 combines technicals, fundamentals, momentum, risk, and sentiment.",
            f"Risk: stop loss uses ATR x {risk_plan.get('atr_multiplier', 0):.2f}, limiting initial risk to {risk_plan.get('risk_pct', 0):.2f}%.",
        ]
        record_prediction(
            ticker=ticker,
            decision=result["decision"],
            entry=result["price"],
            target=result["target"],
            stop_loss=result["stop_loss"],
            score=result.get("master_score", result.get("quantara_score")),
        )
        return result
