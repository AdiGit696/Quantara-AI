from concurrent.futures import ThreadPoolExecutor, as_completed

from engines.basket_engine import build_stock_basket
from engines.data_service import get_market_universe, safe_info
from engines.stock_engine import analyze_stock


def _candidate_score(result):
    return (
        result["trade_confidence"] * 0.45
        + result["fundamentals"].get("score", 0) * 0.28
        + max(0, result["expected_return_pct"]) * 1.6
        + min(result["risk_reward"], 3) * 7
        - result["risk_pct"] * 1.2
    )


def _analyze_holding(row):
    ticker = str(row["Ticker"]).upper().strip()
    qty = float(row["Quantity"])
    buy_price = float(row.get("Buy_Price", 0) or 0)
    result = analyze_stock(ticker)
    info = safe_info(ticker)
    sector = info.get("sector", result.get("fundamentals", {}).get("metrics", {}).get("sector", "Unknown"))
    current_value = result["price"] * qty
    cost_value = buy_price * qty

    return {
        "ticker": ticker,
        "quantity": qty,
        "buy_price": buy_price,
        "sector": sector,
        "current_value": current_value,
        "cost_value": cost_value,
        "pnl_pct": ((result["price"] / buy_price) - 1) * 100 if buy_price else 0,
        **result
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
    holdings = []
    errors = []

    rows = [row for _, row in df.iterrows()]
    with ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(rows) or 1))) as executor:
        future_map = {executor.submit(_analyze_holding, row): row for row in rows}
        for future in as_completed(future_map):
            row = future_map[future]
            ticker = str(row["Ticker"]).upper().strip()
            try:
                holdings.append(future.result())
            except Exception as exc:
                errors.append(f"{ticker}: {exc}")

    total_value = sum(item["current_value"] for item in holdings)
    total_cost = sum(item["cost_value"] for item in holdings)
    sector_values = {}
    rebalance_suggestions = []
    weak_holdings = []

    for item in holdings:
        sector_values[item["sector"]] = sector_values.get(item["sector"], 0) + item["current_value"]
        if item["decision"] == "AVOID" or item["trade_confidence"] < 50:
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

    avg_confidence = sum(item["trade_confidence"] for item in holdings) / len(holdings) if holdings else 0
    avg_fundamental = sum(item["fundamentals"].get("score", 0) for item in holdings) / len(holdings) if holdings else 0
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

    return {
        "holdings": holdings,
        "total_value": total_value,
        "total_cost": total_cost,
        "future_value": projected_value,
        "projected_return_pct": ((projected_value / total_value) - 1) * 100 if total_value else 0,
        "realized_return_pct": ((total_value / total_cost) - 1) * 100 if total_cost else 0,
        "portfolio_score": health_score,
        "aggregate_risk": sum(item["risk_pct"] * item["current_value"] for item in holdings) / total_value if total_value else 0,
        "sector_allocation": sector_allocation,
        "weak_holdings": weak_holdings,
        "rebalance_suggestions": rebalance_suggestions,
        "replacement_suggestions": replacement_suggestions,
        "errors": errors,
        "decision_counts": {
            "BUY": sum(1 for item in holdings if item["decision"] == "BUY"),
            "HOLD": sum(1 for item in holdings if item["decision"] == "HOLD"),
            "AVOID": sum(1 for item in holdings if item["decision"] == "AVOID")
        }
    }
