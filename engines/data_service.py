from io import StringIO
from pathlib import Path
import json
import time

import pandas as pd
import requests
import yfinance as yf


FALLBACK_UNIVERSE = [
    "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS",
    "SBIN.NS", "LT.NS", "AXISBANK.NS", "ITC.NS", "BHARTIARTL.NS",
    "MARUTI.NS", "SUNPHARMA.NS", "TITAN.NS", "ULTRACEMCO.NS", "WIPRO.NS"
]
DEFAULT_UNIVERSE = FALLBACK_UNIVERSE
NSE_EQUITY_LIST_URL = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
NSE_FO_LIST_URL = "https://archives.nseindia.com/content/fo/fo_mktlots.csv"
NSE_ETF_LIST_URL = "https://archives.nseindia.com/content/etf/ETF.csv"
BSE_ACTIVE_LIST_URL = "https://api.bseindia.com/BseIndiaAPI/api/ListofScripData/w?Group=&Scripcode=&industry=&segment=Equity&status=Active"
UNIVERSE_CACHE = Path(__file__).resolve().parent.parent / ".quantara" / "universe_cache.json"

SECTOR_OPTIONS = [
    "Banking", "IT", "Pharma", "FMCG", "Energy", "Auto", "PSU", "Defence",
    "Infra", "Realty", "Metals", "Midcap", "Smallcap"
]

SECTOR_KEYWORDS = {
    "Banking": ["BANK", "FIN", "CAPITAL", "CREDIT", "HDFC", "ICICI", "SBIN", "AXIS", "KOTAK", "PNB", "CANBK", "IDFC"],
    "IT": ["TCS", "INFY", "WIPRO", "TECHM", "HCL", "LTIM", "MPHASIS", "COFORGE", "PERSISTENT", "SOFT", "INFO"],
    "Pharma": ["PHARMA", "LAB", "DRREDDY", "SUNPHARMA", "CIPLA", "BIOCON", "AURO", "LUPIN", "GLENMARK", "ALKEM"],
    "FMCG": ["ITC", "HINDUNILVR", "DABUR", "MARICO", "NESTLE", "BRITANNIA", "GODREJCP", "COLPAL", "VBL"],
    "Energy": ["RELIANCE", "ONGC", "IOC", "BPCL", "HPCL", "NTPC", "POWERGRID", "TATAPOWER", "ADANIGREEN", "OIL"],
    "Auto": ["AUTO", "MOTOR", "MARUTI", "TATAMOTORS", "M&M", "EICHER", "BAJAJ-AUTO", "HEROMOTOCO", "TVSMOTOR", "ASHOKLEY"],
    "PSU": ["COALINDIA", "BEL", "BHEL", "HAL", "SAIL", "NMDC", "IRCTC", "IRFC", "RVNL", "BANKINDIA", "UNIONBANK"],
    "Defence": ["HAL", "BEL", "BDL", "COCHINSHIP", "MAZDOCK", "GRSE", "DATAPATTNS", "MTARTECH", "PARAS"],
    "Infra": ["LT", "IRB", "PNCINFRA", "KEC", "KNRCON", "RVNL", "NBCC", "NCC", "GMR", "ADANIPORTS"],
    "Realty": ["DLF", "LODHA", "GODREJPROP", "OBEROIRLTY", "PRESTIGE", "PHOENIXLTD", "BRIGADE", "SOBHA"],
    "Metals": ["TATASTEEL", "JSWSTEEL", "HINDALCO", "VEDL", "JINDAL", "SAIL", "NMDC", "NATIONALUM", "HINDCOPPER"],
    "Midcap": ["MIDCAP", "MID"],
    "Smallcap": ["SMALLCAP", "SMALL"],
    "ETF": ["ETF", "BEES", "NIFTY", "SENSEX"],
}


def get_stock(ticker):
    return yf.Ticker(ticker)


def get_price_history(ticker, period="1y", interval="1d"):
    try:
        df = get_stock(ticker).history(period=period, interval=interval)
    except Exception:
        return pd.DataFrame()
    if df is None or df.empty:
        return pd.DataFrame()

    return df.dropna(subset=["Open", "High", "Low", "Close"])


def get_listed_stocks(exchange="NSE", limit=None):
    """
    Return a scalable listed-stock universe for basket scans.

    yfinance can fetch quotes but does not expose a complete exchange listing API.
    For Indian equities we load NSE's public equity master and convert symbols to
    Yahoo Finance tickers. If the exchange source is unavailable, callers still
    receive a small liquid fallback instead of a broken basket screen.
    """
    exchange = exchange.upper()
    if exchange != "NSE":
        return FALLBACK_UNIVERSE[:limit] if limit else FALLBACK_UNIVERSE.copy()

    try:
        response = requests.get(
            NSE_EQUITY_LIST_URL,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "text/csv,*/*"},
            timeout=15
        )
        response.raise_for_status()
        frame = pd.read_csv(StringIO(response.text))
        symbols = (
            frame["SYMBOL"]
            .dropna()
            .astype(str)
            .str.strip()
            .str.upper()
            .drop_duplicates()
            .sort_values()
            .tolist()
        )
        all_tickers = [f"{symbol}.NS" for symbol in symbols if symbol]
        # Put liquid names first for a faster useful first paint, while still
        # keeping the complete listed universe available after the priority set.
        tickers = list(dict.fromkeys(FALLBACK_UNIVERSE + all_tickers))
        return tickers[:limit] if limit else tickers
    except Exception:
        return FALLBACK_UNIVERSE[:limit] if limit else FALLBACK_UNIVERSE.copy()


def _cache_universe(cache_key, payload):
    try:
        UNIVERSE_CACHE.parent.mkdir(exist_ok=True)
        existing = {}
        if UNIVERSE_CACHE.exists():
            existing = json.loads(UNIVERSE_CACHE.read_text(encoding="utf-8"))
        existing[cache_key] = {"created_at": time.time(), "payload": payload}
        UNIVERSE_CACHE.write_text(json.dumps(existing), encoding="utf-8")
    except Exception:
        pass


def _read_universe_cache(cache_key, max_age_hours=24):
    try:
        if not UNIVERSE_CACHE.exists():
            return None
        data = json.loads(UNIVERSE_CACHE.read_text(encoding="utf-8")).get(cache_key, {})
        if time.time() - data.get("created_at", 0) > max_age_hours * 3600:
            return None
        return data.get("payload")
    except Exception:
        return None


def _nse_equities():
    tickers = get_listed_stocks("NSE")
    return [
        {
            "ticker": ticker,
            "symbol": ticker.replace(".NS", ""),
            "exchange": "NSE",
            "segment": "Equity",
            "display_name": ticker.replace(".NS", ""),
            "sector": classify_sector(ticker),
        }
        for ticker in tickers
    ]


def _nse_fo_symbols():
    try:
        response = requests.get(
            NSE_FO_LIST_URL,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "text/csv,*/*"},
            timeout=15,
        )
        response.raise_for_status()
        frame = pd.read_csv(StringIO(response.text))
        symbol_col = "SYMBOL" if "SYMBOL" in frame.columns else frame.columns[1]
        symbols = frame[symbol_col].dropna().astype(str).str.strip().str.upper().drop_duplicates().tolist()
        return {f"{symbol}.NS" for symbol in symbols if symbol and symbol != "SYMBOL"}
    except Exception:
        return set()


def _nse_etfs():
    try:
        response = requests.get(
            NSE_ETF_LIST_URL,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "text/csv,*/*"},
            timeout=15,
        )
        response.raise_for_status()
        frame = pd.read_csv(StringIO(response.text))
        symbol_col = "SYMBOL" if "SYMBOL" in frame.columns else frame.columns[0]
        symbols = frame[symbol_col].dropna().astype(str).str.strip().str.upper().drop_duplicates().tolist()
        return [{"ticker": f"{symbol}.NS", "exchange": "NSE", "segment": "ETF", "sector": "ETF"} for symbol in symbols if symbol and symbol != "SYMBOL"]
    except Exception:
        return []


def _bse_equities():
    try:
        response = requests.get(
            BSE_ACTIVE_LIST_URL,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json,text/plain,*/*",
                "Referer": "https://www.bseindia.com/",
            },
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        rows = payload if isinstance(payload, list) else payload.get("Table", [])
        items = []
        for row in rows:
            code = row.get("SCRIP_CD") or row.get("SCRIPCODE") or row.get("Security Code")
            name = row.get("Scrip_Name") or row.get("SCRIP_NAME") or row.get("Security Name") or ""
            scrip_id = row.get("scrip_id") or row.get("SCRIP_ID") or row.get("SYMBOL") or ""
            if code:
                ticker = f"{str(code).strip()}.BO"
                clean_symbol = str(scrip_id).upper().strip() or str(code).strip()
                display_name = f"{str(name).strip()} ({clean_symbol})" if name else clean_symbol
                items.append({
                    "ticker": ticker,
                    "symbol": clean_symbol,
                    "exchange": "BSE",
                    "segment": "Equity",
                    "name": str(name).strip(),
                    "display_name": display_name,
                    "sector": classify_sector(f"{clean_symbol} {name}")
                })
        return items
    except Exception:
        return []


def classify_sector(text):
    clean = str(text or "").upper().replace(".NS", "").replace(".BO", "")
    for sector, keywords in SECTOR_KEYWORDS.items():
        if any(keyword in clean for keyword in keywords):
            return sector
    return "Other"


def get_market_universe(include_nse=True, include_bse=True, include_etfs=False, include_fo=False, limit=None):
    cache_key = f"v2|nse={include_nse}|bse={include_bse}|etf={include_etfs}|fo={include_fo}"
    cached = _read_universe_cache(cache_key)
    if cached is None:
        rows = _nse_equities() if include_nse else []
        if include_fo:
            fo = list(_nse_fo_symbols())
            fo_set = set(fo)
            existing = {row["ticker"] for row in rows}
            for row in rows:
                if row["ticker"] in fo_set:
                    row["segment"] = "F&O"
            for ticker in fo:
                if ticker not in existing:
                    rows.append({"ticker": ticker, "exchange": "NSE", "segment": "F&O", "sector": "F&O"})
        if include_etfs and include_nse:
            rows.extend(_nse_etfs())
        if include_bse:
            rows.extend(_bse_equities())
        _cache_universe(cache_key, rows)
    else:
        rows = cached

    filtered = []
    for row in rows:
        if row.get("exchange") == "NSE" and not include_nse:
            continue
        if row.get("exchange") == "BSE" and not include_bse:
            continue
        if row.get("sector") == "ETF" and not include_etfs:
            continue
        if row.get("segment") == "F&O" and not include_fo:
            continue
        filtered.append(row)

    seen = set()
    unique = []
    for row in filtered:
        ticker = row.get("ticker")
        if ticker and ticker not in seen:
            seen.add(ticker)
            unique.append(row)

    return unique[:limit] if limit else unique


def display_symbol(row_or_ticker):
    if isinstance(row_or_ticker, dict):
        if row_or_ticker.get("display_name"):
            return row_or_ticker["display_name"]
        ticker = row_or_ticker.get("ticker", "")
        symbol = row_or_ticker.get("symbol")
    else:
        ticker = str(row_or_ticker)
        symbol = None
    clean = str(symbol or ticker).upper().replace(".NS", "").replace(".BO", "")
    return clean


def get_weekly_close(ticker, period="2y"):
    weekly = get_stock(ticker).history(period=period, interval="1wk")
    if weekly is None or weekly.empty:
        return pd.Series(dtype=float)

    return weekly["Close"].dropna()


def safe_info(ticker):
    try:
        return get_stock(ticker).info or {}
    except Exception:
        return {}


def get_financial_frames(ticker):
    stock = get_stock(ticker)

    def read_frame(attr):
        try:
            value = getattr(stock, attr)
            return value if value is not None else pd.DataFrame()
        except Exception:
            return pd.DataFrame()

    return {
        "financials": read_frame("financials"),
        "quarterly_financials": read_frame("quarterly_financials"),
        "balance_sheet": read_frame("balance_sheet"),
        "quarterly_balance_sheet": read_frame("quarterly_balance_sheet"),
        "cashflow": read_frame("cashflow"),
        "quarterly_cashflow": read_frame("quarterly_cashflow")
    }
