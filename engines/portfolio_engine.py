from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

from engines.basket_engine import build_stock_basket
from engines.data_service import get_market_universe, get_portfolio_current_price, get_price_history, resolve_ticker
from engines.scoring_engine import build_scorecard, recommendation_from_scores
from utils.numbers import numeric_series
from utils.observability import log_performance, log_symbol_failure


def _candidate_score(result):
    return (
        result["trade_confidence"] * 0.45
        + result["fundamentals"].get("score", 0) * 0.28
        + max(0, result["expected_return_pct"]) * 1.6
        + min(result["risk_reward"], 3) * 7
        - result["risk_pct"] * 1.2
    )


def _analyze_holding(row, universe=None):
    raw_ticker = str(row["Ticker"]).upper().strip()
    if raw_ticker.endswith((".NS", ".BO")) or raw_ticker.startswith("^"):
        resolved = next((item for item in (universe or []) if item.get("ticker") == raw_ticker), None)
        resolved = resolved or {"ticker": raw_ticker, "display_name": raw_ticker}
    else:
        resolved = resolve_ticker(raw_ticker, universe=universe)
    if not resolved or not resolved.get("ticker"):
        raise ValueError(f"Could not resolve stock name: {row['Ticker']}")
    ticker = resolved["ticker"]
    qty = float(row["Quantity"])
    buy_price = float(row.get("Buy_Price", 0) or 0)
    result = _fast_holding_analysis(ticker, buy_price)
    sector = resolved.get("sector") or result.get("fundamentals", {}).get("metrics", {}).get("sector", "Unknown")
    current_value = result["price"] * qty
    cost_value = buy_price * qty

    return {
        "ticker": ticker,
        "display_name": resolved.get("display_name") or result.get("company_name") or ticker,
        "portfolio_action": "HOLD" if result.get("decision") in {"STRONG BUY", "BUY", "HOLD"} else "REVIEW / REDUCE",
        "quantity": qty,
        "buy_price": buy_price,
        "sector": sector,
        "current_value": current_value,
        "cost_value": cost_value,
        "pnl_pct": ((result["price"] / buy_price) - 1) * 100 if buy_price else 0,
        **result
    }


def _fast_holding_analysis(ticker, buy_price):
    history = get_price_history(ticker, period="1y")
    if history.empty:
        raise ValueError("No price history available")
    close = numeric_series(history["Close"])
    if close.empty:
        raise ValueError("No valid close prices available")
    price = get_portfolio_current_price(ticker)
    ret_30 = ((price / float(close.iloc[-22])) - 1) * 100 if len(close) > 22 and close.iloc[-22] else 0
    ret_90 = ((price / float(close.iloc[-64])) - 1) * 100 if len(close) > 64 and close.iloc[-64] else ret_30
    volatility = float(close.pct_change().dropna().std() * (252 ** 0.5) * 100) if len(close) > 2 else 20
    drawdown = abs(float(((close / close.cummax()) - 1).min() * 100)) if len(close) > 2 else volatility
    sma50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else price
    trend = "Uptrend" if price >= sma50 else "Downtrend" if ret_90 < -8 else "Sideways"
    risk_reward = max(0.6, min(3.0, max(ret_30, 0.5) / max(volatility / 8, 1)))
    scorecard = build_scorecard(
        probability=max(30, min(82, 54 + ret_30 * 0.7 + ret_90 * 0.25)),
        uncertainty=min(36, max(14, volatility / 2.2)),
        risk_pct=max(1, drawdown / 4),
        atr_pct=max(1, volatility / 8),
        risk_reward=risk_reward,
        fundamental_score=52,
        expected_return_pct=ret_30,
        trend=trend,
    )
    decision = recommendation_from_scores(
        scorecard,
        expected_return_pct=ret_30,
        risk_reward=risk_reward,
        trend=trend,
        fundamentals={"score": 52},
        owned=True,
    )
    return {
        "price": price,
        "future_30": price * (1 + ret_30 / 100),
        "expected_return_pct": ret_30,
        "risk_reward": risk_reward,
        "risk_pct": max(1, drawdown / 4),
        "atr_pct": max(1, volatility / 8),
        "risk_level": "Low" if volatility < 18 else "Medium" if volatility < 30 else "High",
        "decision": decision,
        "trade_confidence": scorecard["confidence_score"],
        "quantara_score": scorecard["quantara_score"],
        "ai_score": scorecard["ai_score"],
        "risk_score": scorecard["risk_score"],
        "decision_score": scorecard["decision_score"],
        "confidence_score": scorecard["confidence_score"],
        "probability_reasons": [
            f"Portfolio fast path used cached price trend: {trend}.",
            f"30-session return {ret_30:.2f}% with annualized volatility {volatility:.2f}%.",
        ],
        "fundamentals": {"score": 52, "metrics": {"sector": "Unknown"}},
        "history": history,
        "trend": trend,
    }


def _fallback_analysis(ticker, buy_price, exc):
    history = get_price_history(ticker, period="1y")
    if history.empty:
        raise exc
    close = numeric_series(history["Close"])
    if close.empty:
        raise exc
    price = get_portfolio_current_price(ticker)
    prev = float(close.iloc[-2]) if len(close) > 1 else price
    ret_30 = ((price / float(close.iloc[-22])) - 1) * 100 if len(close) > 22 else ((price / buy_price) - 1) * 100 if buy_price else 0
    volatility = float(close.pct_change().dropna().std() * (252 ** 0.5) * 100) if len(close) > 2 else 20
    trend = "Uptrend" if len(close) > 50 and price > float(close.rolling(50).mean().iloc[-1]) else "Sideways"
    scorecard = build_scorecard(
        probability=max(35, min(75, 52 + ret_30)),
        uncertainty=min(35, max(15, volatility / 2)),
        risk_pct=max(1, volatility / 5),
        atr_pct=max(1, volatility / 8),
        risk_reward=max(0.8, ret_30 / max(volatility / 6, 1)),
        fundamental_score=50,
        expected_return_pct=ret_30,
        trend=trend,
    )
    decision = recommendation_from_scores(scorecard, expected_return_pct=ret_30, risk_reward=max(0.8, ret_30 / max(volatility / 6, 1)), trend=trend, fundamentals={"score": 50})
    return {
        "price": price,
        "future_30": price * (1 + ret_30 / 100),
        "expected_return_pct": ret_30,
        "risk_reward": max(0.8, ret_30 / max(volatility / 6, 1)),
        "risk_pct": max(1, volatility / 5),
        "atr_pct": max(1, volatility / 8),
        "risk_level": "Medium" if volatility < 28 else "High",
        "decision": decision,
        "trade_confidence": scorecard["confidence_score"],
        "quantara_score": scorecard["quantara_score"],
        "ai_score": scorecard["ai_score"],
        "risk_score": scorecard["risk_score"],
        "decision_score": scorecard["decision_score"],
        "confidence_score": scorecard["confidence_score"],
        "probability_reasons": ["Fallback cached price analysis used because full provider data was unavailable."],
        "fundamentals": {"score": 50, "metrics": {"sector": "Unknown"}},
        "history": history,
        "trend": trend,
    }


def _replacement_candidates(holdings, overexposed, capital):
    owned = {item["ticker"] for item in holdings}
    weak = [item for item in holdings if item["decision"] == "AVOID" or item["trade_confidence"] < 50]
    if not weak:
        return []

    universe = [
        row for row in get_market_universe(include_nse=True, include_bse=True, include_etfs=False, include_fo=False)
        if row.get("ticker") not in owned and row.get("sector") not in overexposed
    ][:360]
    if not universe:
        return []

    basket = build_stock_basket(
        capital=max(capital, 100000),
        candidates=universe,
        max_positions=min(8, max(3, len(weak) * 2)),
        risk_per_trade_pct=1.5,
        scan_limit=len(universe),
        max_workers=3,
        chunk_size=90,
    )
    ideas = []
    ranked = sorted(basket.get("positions", []), key=lambda item: item.get("confidence", 0), reverse=True)
    for index, holding in enumerate(weak):
        for candidate in ranked[index * 2:index * 2 + 2]:
            ideas.append({
                "replace": holding["ticker"],
                "suggested_stock": candidate.get("display_name") or candidate.get("symbol") or candidate["ticker"],
                "ticker": candidate["ticker"],
                "sector": candidate.get("sector", "Unknown"),
                "ai_score": candidate.get("confidence"),
                "confidence": candidate.get("confidence"),
                "expected_return_pct": candidate.get("expected_return_pct"),
                "risk_level": candidate.get("risk_level"),
                "risk_comparison": f"{candidate.get('atr_pct', 0):.2f}% ATR vs {holding['atr_pct']:.2f}% current",
                "expected_improvement": f"{candidate.get('expected_return_pct', 0) - holding['expected_return_pct']:.2f}% return delta; {candidate.get('confidence', 0) - holding['trade_confidence']:.0f} confidence delta",
                "why": candidate.get("reason", "Fast replacement scan found stronger technical quality.")
            })
    return ideas[:8]


def analyze_portfolio(df, generate_replacements=True, max_workers=4):
    import time
    start = time.perf_counter()
    holdings = []
    errors = []
    try:
        universe = get_market_universe(include_nse=True, include_bse=True, include_etfs=False, include_fo=False)
    except Exception:
        universe = None

    normalized = df.copy()
    normalized["Ticker"] = normalized["Ticker"].astype(str).str.upper().str.strip()
    normalized["Quantity"] = pd.to_numeric(normalized["Quantity"], errors="coerce")
    normalized["Buy_Price"] = pd.to_numeric(normalized["Buy_Price"], errors="coerce")
    normalized = normalized.dropna(subset=["Ticker", "Quantity", "Buy_Price"])
    normalized = normalized[(normalized["Ticker"] != "") & (normalized["Quantity"] > 0) & (normalized["Buy_Price"] >= 0)]
    normalized["Cost_Value"] = normalized["Quantity"] * normalized["Buy_Price"]
    grouped = normalized.groupby("Ticker", as_index=False).agg({"Quantity": "sum", "Cost_Value": "sum"})
    grouped["Buy_Price"] = grouped["Cost_Value"] / grouped["Quantity"]
    rows = [row for _, row in grouped[["Ticker", "Quantity", "Buy_Price"]].iterrows()]
    with ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(rows) or 1))) as executor:
        future_map = {executor.submit(_analyze_holding, row, universe): row for row in rows}
        for future in as_completed(future_map):
            row = future_map[future]
            ticker = str(row["Ticker"]).upper().strip()
            try:
                holdings.append(future.result())
            except Exception as exc:
                log_symbol_failure("portfolio", ticker, exc)
                errors.append(f"{ticker}: {exc}")

    total_value = sum(item["current_value"] for item in holdings)
    total_cost = sum(item["cost_value"] for item in holdings)
    for item in holdings:
        item["allocation_pct"] = round((item["current_value"] / total_value) * 100, 2) if total_value else 0
    sector_values = {}
    rebalance_suggestions = []
    weak_holdings = []

    for item in holdings:
        sector_values[item["sector"]] = sector_values.get(item["sector"], 0) + item["current_value"]
        weak = (
            item["decision"] == "AVOID"
            and item.get("risk_score", 50) < 45
            and item.get("fundamentals", {}).get("score", 50) < 45
            and item["trade_confidence"] < 55
        ) or item["trade_confidence"] < 42
        if weak:
            weak_holdings.append(item["ticker"])
            rebalance_suggestions.append({
                "ticker": item["ticker"],
                "action": "Review / Reduce",
                "reason": "; ".join(item["probability_reasons"][:3]),
                "expected_improvement": "Consider replacement if another stock offers better confidence, lower volatility, and cleaner momentum.",
                "risk_comparison": f"Current risk: {item['risk_pct']:.2f}% | Risk level: {item['risk_level']}",
                "return_potential": f"Expected 30d: {item['expected_return_pct']:.2f}%"
            })

    sector_allocation = {
        sector: round((value / total_value) * 100, 2)
        for sector, value in sector_values.items()
    } if total_value else {}
    overexposed = [sector for sector, pct in sector_allocation.items() if pct > 35 and sector != "Unknown"]

    avg_confidence = sum(item["trade_confidence"] * item["current_value"] for item in holdings) / total_value if total_value else 0
    avg_fundamental = sum(item["fundamentals"].get("score", 0) * item["current_value"] for item in holdings) / total_value if total_value else 0
    risk_penalty = len(weak_holdings) * 6 + len(overexposed) * 8
    health_score = max(0, min(100, (avg_confidence * 0.6) + (avg_fundamental * 0.4) - risk_penalty))
    projected_value = sum(item["future_30"] * item["quantity"] for item in holdings)

    if overexposed:
        rebalance_suggestions.append({
            "ticker": "Portfolio",
            "action": "Diversify",
            "reason": f"Overexposure detected in: {', '.join(overexposed)}",
            "expected_improvement": "Reduce concentration drag and improve sector balance.",
            "risk_comparison": "Concentration risk is elevated versus a sector-balanced book.",
            "return_potential": "Improves risk-adjusted return potential more than raw return."
        })

    replacement_suggestions = _replacement_candidates(holdings, overexposed, total_value) if generate_replacements else []

    result = {
        "holdings": holdings,
        "total_value": total_value,
        "total_cost": total_cost,
        "future_value": projected_value,
        "projected_return_pct": ((projected_value / total_value) - 1) * 100 if total_value else 0,
        "realized_return_pct": ((total_value / total_cost) - 1) * 100 if total_cost else 0,
        "portfolio_score": health_score,
        "portfolio_health": health_score,
        "aggregate_risk": sum(item["risk_pct"] * item["current_value"] for item in holdings) / total_value if total_value else 0,
        "sector_allocation": sector_allocation,
        "weak_holdings": weak_holdings,
        "rebalance_suggestions": rebalance_suggestions,
        "replacement_suggestions": replacement_suggestions,
        "errors": errors,
        "decision_counts": {
            "BUY": sum(1 for item in holdings if item["decision"] == "BUY"),
            "HOLD": sum(1 for item in holdings if item["decision"] == "HOLD"),
            "WATCH": sum(1 for item in holdings if item["decision"] == "WATCH"),
            "AVOID": sum(1 for item in holdings if item["decision"] == "AVOID")
        }
    }
    log_performance("portfolio_analysis", time.perf_counter() - start, count=len(rows), status="partial" if errors else "ok")
    return result
