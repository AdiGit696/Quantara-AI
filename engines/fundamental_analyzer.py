import math

import numpy as np
import pandas as pd

from engines.data_service import get_financial_frames, safe_info
from utils.numbers import numeric_series


def _first_available(frame, labels):
    if frame is None or frame.empty:
        return pd.Series(dtype=float)

    normalized = {str(idx).lower(): idx for idx in frame.index}
    for label in labels:
        match = normalized.get(label.lower())
        if match is not None:
            value = frame.loc[match]
            if isinstance(value, pd.DataFrame):
                value = value.iloc[0]
            return numeric_series(value)

    return pd.Series(dtype=float)


def _latest(series):
    if series is None or len(series) == 0:
        return None
    values = numeric_series(series)
    if values.empty:
        return None
    value = values.iloc[0]
    return float(value) if pd.notna(value) else None


def _safe_number(value, multiplier=1):
    try:
        if value is None or pd.isna(value):
            return None
        value = float(value) * multiplier
        return value if math.isfinite(value) else None
    except Exception:
        return None


def _growth(series):
    values = series.dropna().astype(float).head(3)
    if len(values) < 2:
        return None

    current = values.iloc[0]
    previous = values.iloc[-1]
    if previous == 0:
        return None

    return ((current / abs(previous)) - 1) * 100


def _trend(series):
    values = series.dropna().astype(float).head(3)
    if len(values) < 3:
        return "Insufficient data"

    if values.iloc[0] > values.iloc[1] > values.iloc[2]:
        return "Improving"
    if values.iloc[0] < values.iloc[1] < values.iloc[2]:
        return "Weakening"
    return "Mixed"


def _fmt_pct(value):
    if value is None or not math.isfinite(value):
        return None
    return round(float(value), 2)


def _score_metric(name, value, good_threshold=None, weak_threshold=None, inverse=False):
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return 0, f"{name} data unavailable"

    if inverse:
        if value <= good_threshold:
            return 2, f"{name} is healthy"
        if value <= weak_threshold:
            return 1, f"{name} is acceptable"
        return -1, f"{name} is stretched"

    if value >= good_threshold:
        return 2, f"{name} is strong"
    if value >= weak_threshold:
        return 1, f"{name} is acceptable"
    return -1, f"{name} is weak"


def analyze_fundamentals(ticker):
    info = safe_info(ticker) or {}
    try:
        frames = get_financial_frames(ticker) or {}
    except Exception:
        frames = {}
    annual = frames.get("financials", pd.DataFrame())
    quarterly = frames.get("quarterly_financials", pd.DataFrame())
    balance = frames.get("balance_sheet", pd.DataFrame())
    cashflow = frames.get("cashflow", pd.DataFrame())

    revenue = _first_available(annual, ["Total Revenue", "Operating Revenue"])
    net_income = _first_available(annual, ["Net Income", "Net Income Common Stockholders"])
    eps = _first_available(annual, ["Basic EPS", "Diluted EPS"])
    operating_income = _first_available(annual, ["Operating Income", "EBIT"])
    total_debt = _first_available(balance, ["Total Debt", "Long Term Debt"])
    cash = _first_available(balance, ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"])
    equity = _first_available(balance, ["Stockholders Equity", "Total Equity Gross Minority Interest"])
    current_assets = _first_available(balance, ["Current Assets", "Total Current Assets"])
    current_liabilities = _first_available(balance, ["Current Liabilities", "Total Current Liabilities"])
    total_assets = _first_available(balance, ["Total Assets"])
    total_liabilities = _first_available(balance, ["Total Liabilities Net Minority Interest", "Total Liabilities"])
    free_cash_flow = _first_available(cashflow, ["Free Cash Flow"])
    operating_cash_flow = _first_available(cashflow, ["Operating Cash Flow", "Total Cash From Operating Activities"])
    capex = _first_available(cashflow, ["Capital Expenditure", "Capital Expenditures"])

    if free_cash_flow.empty and not operating_cash_flow.empty and not capex.empty:
        free_cash_flow = operating_cash_flow + capex

    latest_revenue = _latest(revenue)
    latest_operating_income = _latest(operating_income)
    latest_debt = _latest(total_debt)
    latest_equity = _latest(equity)
    latest_current_assets = _latest(current_assets)
    latest_current_liabilities = _latest(current_liabilities)
    latest_total_assets = _latest(total_assets)
    latest_total_liabilities = _latest(total_liabilities)

    debt_to_equity = _safe_number(info.get("debtToEquity"))
    if debt_to_equity is not None:
        debt_to_equity /= 100
    if debt_to_equity is None and latest_debt and latest_equity:
        debt_to_equity = latest_debt / latest_equity

    operating_margin = _safe_number(info.get("operatingMargins"))
    if operating_margin is None and latest_revenue and latest_operating_income:
        operating_margin = latest_operating_income / latest_revenue

    current_ratio = _safe_number(info.get("currentRatio"))
    if current_ratio is None and latest_current_assets and latest_current_liabilities:
        current_ratio = latest_current_assets / latest_current_liabilities

    metrics = {
        "sector": info.get("sector", "Unknown"),
        "industry": info.get("industry", "Unknown"),
        "market_cap": info.get("marketCap"),
        "revenue_growth": _fmt_pct(_growth(revenue)),
        "net_profit_growth": _fmt_pct(_growth(net_income)),
        "eps_growth": _fmt_pct(_growth(eps)),
        "debt_to_equity": _fmt_pct(debt_to_equity),
        "roe": _fmt_pct(_safe_number(info.get("returnOnEquity"), 100)),
        "roce": None,
        "promoter_holding": None,
        "free_cash_flow": _latest(free_cash_flow),
        "operating_margin": _fmt_pct((operating_margin or 0) * 100) if operating_margin else None,
        "pe_ratio": _fmt_pct(_safe_number(info.get("trailingPE") or info.get("forwardPE"))),
        "pb_ratio": _fmt_pct(_safe_number(info.get("priceToBook"))),
        "current_ratio": _fmt_pct(current_ratio),
        "quick_ratio": _fmt_pct(_safe_number(info.get("quickRatio"))),
        "eps": _fmt_pct(_safe_number(info.get("trailingEps") or info.get("forwardEps"))),
        "quarterly_revenue_growth": _fmt_pct(_safe_number(info.get("revenueGrowth"), 100)) if info.get("revenueGrowth") else _fmt_pct(_growth(_first_available(quarterly, ["Total Revenue"]))),
        "institutional_holding": _fmt_pct(_safe_number(info.get("heldPercentInstitutions"), 100)),
        "cash_reserves": _latest(cash),
        "debt_trend": _trend(total_debt),
        "revenue_trend": _trend(revenue),
        "profit_trend": _trend(net_income),
        "cashflow_trend": _trend(free_cash_flow)
    }

    score = 0
    insights = []

    checks = [
        _score_metric("Revenue growth", metrics["revenue_growth"], 12, 4),
        _score_metric("Net profit growth", metrics["net_profit_growth"], 10, 2),
        _score_metric("ROE", metrics["roe"], 15, 10),
        _score_metric("Operating margin", metrics["operating_margin"], 18, 10),
        _score_metric("Debt to equity", metrics["debt_to_equity"], 0.6, 1.2, inverse=True),
        _score_metric("Current ratio", metrics["current_ratio"], 1.5, 1.0),
        _score_metric("PE ratio", metrics["pe_ratio"], 28, 45, inverse=True),
        _score_metric("PB ratio", metrics["pb_ratio"], 4, 8, inverse=True)
    ]

    for delta, reason in checks:
        score += delta
        insights.append(reason)

    if metrics["debt_trend"] == "Weakening":
        score += 1
        insights.append("Debt reduced over recent annual periods")
    elif metrics["debt_trend"] == "Improving":
        score -= 1
        insights.append("Debt increased over recent annual periods")

    if metrics["cashflow_trend"] == "Improving":
        score += 1
        insights.append("Free cash flow is improving")
    elif metrics["cashflow_trend"] == "Weakening":
        score -= 1
        insights.append("Cash flow is weakening")

    available_metrics = sum(1 for value in metrics.values() if value not in (None, "", "Unknown"))
    baseline = 50 if available_metrics >= 5 else 46
    normalized_score = int(max(0, min(100, baseline + score * 5)))

    if normalized_score >= 78:
        rating = "Strong Bullish"
    elif normalized_score >= 64:
        rating = "Bullish"
    elif normalized_score >= 48:
        rating = "Neutral"
    elif normalized_score >= 35:
        rating = "Weak"
    else:
        rating = "Risky"

    trend_data = {
        "revenue": revenue.head(3).sort_index().to_dict() if not revenue.empty else {},
        "net_income": net_income.head(3).sort_index().to_dict() if not net_income.empty else {},
        "debt": total_debt.head(3).sort_index().to_dict() if not total_debt.empty else {},
        "free_cash_flow": free_cash_flow.head(3).sort_index().to_dict() if not free_cash_flow.empty else {}
    }

    return {
        "score": normalized_score,
        "raw_score": score,
        "rating": rating,
        "metrics": metrics,
        "insights": insights[:10],
        "trend_data": trend_data,
        "balance_sheet_summary": {
            "total_debt": latest_debt,
            "cash_reserves": _latest(cash),
            "shareholder_equity": latest_equity,
            "total_assets": latest_total_assets,
            "total_liabilities": latest_total_liabilities,
            "current_assets": latest_current_assets,
            "current_liabilities": latest_current_liabilities,
        },
        "data_quality": "Good" if annual is not None and not annual.empty else "Partial" if available_metrics >= 4 else "Limited"
    }
