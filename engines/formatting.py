import math
import re


def detect_market(ticker="", exchange=None, currency=None):
    clean = str(ticker or "").upper().strip()
    exchange_text = str(exchange or "").upper().strip()
    currency_text = str(currency or "").upper().strip()
    if clean.endswith((".NS", ".BO")) or exchange_text in {"NSE", "BSE"} or currency_text in {"INR", "RS", "₹"}:
        return {"market": "India", "currency": "INR", "symbol": "₹"}
    if currency_text == "USD":
        return {"market": "US", "currency": "USD", "symbol": "$"}
    return {"market": "US", "currency": currency_text or "USD", "symbol": "$"}


def compact_number(value, currency_symbol=None, indian=True):
    if value is None:
        return "N/A"
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not math.isfinite(amount):
        return "N/A"

    sign = "-" if amount < 0 else ""
    amount = abs(amount)
    prefix = currency_symbol or ""
    if not indian:
        if amount >= 1_000_000_000_000:
            body = f"{amount / 1_000_000_000_000:.2f}T"
        elif amount >= 1_000_000_000:
            body = f"{amount / 1_000_000_000:.2f}B"
        elif amount >= 1_000_000:
            body = f"{amount / 1_000_000:.2f}M"
        elif amount >= 1_000:
            body = f"{amount / 1_000:.2f}K"
        else:
            body = f"{amount:,.2f}"
    elif amount >= 1_000_000_000_000:
        body = f"{amount / 1_000_000_000_000:.2f} Lakh Cr"
    elif amount >= 10_000_000:
        body = f"{amount / 10_000_000:.2f} Cr"
    elif amount >= 100_000:
        body = f"{amount / 100_000:.2f} L"
    else:
        body = f"{amount:,.2f}"
    body = re.sub(r"\.00(?=\s|$)", "", body)
    body = re.sub(r"(\.\d)0(?=\s|$)", r"\1", body)
    return f"{sign}{prefix}{body}"


def format_currency(value, ticker="", exchange=None, currency=None, compact=False):
    market = detect_market(ticker=ticker, exchange=exchange, currency=currency)
    if compact:
        return compact_number(value, market["symbol"], indian=market["market"] == "India")
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return "N/A"
    if not math.isfinite(amount):
        return "N/A"
    return f"{market['symbol']}{amount:,.2f}"


def format_percent(value, digits=2):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "N/A"
    if not math.isfinite(number):
        return "N/A"
    return f"{number:.{digits}f}%"


def format_metric_value(key, value, ticker="", exchange=None, currency=None):
    name = str(key or "").lower()
    if value is None:
        return "N/A"
    if any(token in name for token in ["debt_to_equity", "current_ratio", "quick_ratio"]):
        try:
            return f"{float(value):.2f}"
        except (TypeError, ValueError):
            return str(value)
    if any(token in name for token in ["roe", "roce", "growth", "margin", "holding"]):
        return format_percent(value)
    if any(token in name for token in ["market_cap", "revenue", "cash", "debt", "asset", "liabilit", "income", "profit", "flow"]):
        return format_currency(value, ticker=ticker, exchange=exchange, currency=currency, compact=True)
    if any(token in name for token in ["pe_ratio", "pb_ratio", "eps"]):
        try:
            return f"{float(value):.2f}"
        except (TypeError, ValueError):
            return str(value)
    return str(value)
