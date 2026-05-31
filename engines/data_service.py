from io import StringIO
from pathlib import Path
from difflib import SequenceMatcher
import hashlib
import json
import time

import pandas as pd
import requests
import yfinance as yf

import config
from providers.manager import provider_manager
from utils.numbers import clean_ohlcv_frame
from utils.observability import log_data_quality, log_provider_failure


FALLBACK_UNIVERSE = [
    "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS",
    "SBIN.NS", "LT.NS", "AXISBANK.NS", "ITC.NS", "BHARTIARTL.NS",
    "MARUTI.NS", "SUNPHARMA.NS", "TITAN.NS", "ULTRACEMCO.NS", "WIPRO.NS"
]
DEFAULT_UNIVERSE = FALLBACK_UNIVERSE
KNOWN_COMPANIES = [
    {"ticker": "RELIANCE.NS", "symbol": "RELIANCE", "name": "Reliance Industries", "display_name": "Reliance Industries", "exchange": "NSE", "sector": "Energy"},
    {"ticker": "TCS.NS", "symbol": "TCS", "name": "Tata Consultancy Services", "display_name": "Tata Consultancy Services", "exchange": "NSE", "sector": "IT"},
    {"ticker": "INFY.NS", "symbol": "INFY", "name": "Infosys", "display_name": "Infosys", "exchange": "NSE", "sector": "IT"},
    {"ticker": "HDFCBANK.NS", "symbol": "HDFCBANK", "name": "HDFC Bank", "display_name": "HDFC Bank", "exchange": "NSE", "sector": "Banking"},
    {"ticker": "ICICIBANK.NS", "symbol": "ICICIBANK", "name": "ICICI Bank", "display_name": "ICICI Bank", "exchange": "NSE", "sector": "Banking"},
    {"ticker": "ASIANPAINT.NS", "symbol": "ASIANPAINT", "name": "Asian Paints", "display_name": "Asian Paints", "exchange": "NSE", "sector": "FMCG"},
    {"ticker": "TITAN.NS", "symbol": "TITAN", "name": "Titan Company", "display_name": "Titan Company", "exchange": "NSE", "sector": "FMCG"},
    {"ticker": "BAJFINANCE.NS", "symbol": "BAJFINANCE", "name": "Bajaj Finance", "display_name": "Bajaj Finance", "exchange": "NSE", "sector": "Banking"},
    {"ticker": "HINDUNILVR.NS", "symbol": "HINDUNILVR", "name": "Hindustan Unilever", "display_name": "Hindustan Unilever", "exchange": "NSE", "sector": "FMCG"},
    {"ticker": "KOTAKBANK.NS", "symbol": "KOTAKBANK", "name": "Kotak Mahindra Bank", "display_name": "Kotak Mahindra Bank", "exchange": "NSE", "sector": "Banking"},
    {"ticker": "LT.NS", "symbol": "LT", "name": "Larsen & Toubro", "display_name": "Larsen & Toubro", "exchange": "NSE", "sector": "Infra"},
    {"ticker": "MARUTI.NS", "symbol": "MARUTI", "name": "Maruti Suzuki", "display_name": "Maruti Suzuki", "exchange": "NSE", "sector": "Auto"},
    {"ticker": "TATAMOTORS.NS", "symbol": "TATAMOTORS", "name": "Tata Motors", "display_name": "Tata Motors", "exchange": "NSE", "sector": "Auto"},
]
KNOWN_LOOKUP = {
    key: row
    for row in KNOWN_COMPANIES
    for key in {row["ticker"].upper(), row["symbol"].upper(), row["name"].upper(), row["display_name"].upper()}
}
NSE_EQUITY_LIST_URL = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
NSE_FO_LIST_URL = "https://archives.nseindia.com/content/fo/fo_mktlots.csv"
NSE_ETF_LIST_URL = "https://archives.nseindia.com/content/etf/ETF.csv"
BSE_ACTIVE_LIST_URL = "https://api.bseindia.com/BseIndiaAPI/api/ListofScripData/w?Group=&Scripcode=&industry=&segment=Equity&status=Active"
UNIVERSE_CACHE = Path(__file__).resolve().parent.parent / ".quantara" / "universe_cache.json"
RESOLVED_SYMBOL_CACHE = Path(__file__).resolve().parent.parent / ".quantara" / "resolved_symbols.json"
DATA_CACHE_DIR = Path(__file__).resolve().parent.parent / ".quantara" / "market_cache"
DATA_CACHE_DIR.mkdir(parents=True, exist_ok=True)
_LAST_PROVIDER_CALL = 0.0
_FAILED_HISTORY_UNTIL = {}

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


def normalize_market_ticker(ticker):
    clean = str(ticker or "").upper().strip()
    if not clean or clean.startswith("^") or clean.endswith((".NS", ".BO")):
        return clean
    return f"{clean}.NS" if "." not in clean else clean


def get_portfolio_current_price(ticker):
    ticker = normalize_market_ticker(ticker)
    if not ticker:
        raise ValueError("Ticker is required")
    return float(provider_manager.get_current_price(ticker))


def _cache_key(*parts):
    text = "|".join(str(part) for part in parts)
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _frame_cache_path(kind, *parts):
    return DATA_CACHE_DIR / f"{kind}_{_cache_key(*parts)}.pkl"


def _json_cache_path(kind, *parts):
    return DATA_CACHE_DIR / f"{kind}_{_cache_key(*parts)}.json"


def _is_fresh(path, ttl_seconds):
    return path.exists() and time.time() - path.stat().st_mtime <= ttl_seconds


def _provider_pause(min_interval=0.35):
    global _LAST_PROVIDER_CALL
    elapsed = time.time() - _LAST_PROVIDER_CALL
    if elapsed < min_interval:
        time.sleep(min_interval - elapsed)
    _LAST_PROVIDER_CALL = time.time()


def _read_cached_frame(path):
    try:
        frame = pd.read_pickle(path)
        if frame is None or frame.empty:
            return pd.DataFrame()
        if not isinstance(frame.columns, pd.MultiIndex):
            duplicated_ohlcv = [
                col for col in ["Open", "High", "Low", "Close", "Volume"]
                if list(frame.columns).count(col) > 1
            ]
            if duplicated_ohlcv:
                return pd.DataFrame()
        return clean_ohlcv_frame(frame)
    except Exception:
        return pd.DataFrame()


def _write_cached_frame(path, frame):
    try:
        if frame is not None and not frame.empty:
            path.parent.mkdir(parents=True, exist_ok=True)
            frame.to_pickle(path)
    except Exception:
        pass


def _download_history(ticker, period, interval):
    try:
        return clean_ohlcv_frame(provider_manager.get_price(ticker, period=period, interval=interval))
    except Exception as exc:
        log_provider_failure("DataProviderManager", "get_price", ticker, exc)
        return pd.DataFrame()


def get_price_history(ticker, period="1y", interval="1d"):
    ticker = str(ticker or "").upper().strip()
    if not ticker:
        return pd.DataFrame()
    path = _frame_cache_path("history", ticker, period, interval)
    ttl = 15 * 60 if interval in {"1d", "1wk"} else 5 * 60
    if _is_fresh(path, ttl):
        cached = _read_cached_frame(path)
        if not cached.empty:
            return cached

    stale = _read_cached_frame(path) if path.exists() else pd.DataFrame()
    failure_key = (ticker, period, interval)
    if _FAILED_HISTORY_UNTIL.get(failure_key, 0) > time.time():
        return stale
    for attempt in range(3):
        try:
            df = _download_history(ticker, period, interval)
            if not df.empty:
                _write_cached_frame(path, df)
                return df
        except Exception as exc:
            log_provider_failure("yfinance", "get_price_history", ticker, exc)
            time.sleep(0.6 * (2 ** attempt))
    if stale.empty:
        log_data_quality(ticker, "No price history available from provider or cache")
        _FAILED_HISTORY_UNTIL[failure_key] = time.time() + 5 * 60
    return stale


def get_batch_price_history(tickers, period="6mo", interval="1d", fallback_missing=True):
    tickers = [str(ticker).upper().strip() for ticker in tickers if str(ticker).strip()]
    result = {}
    missing = []
    for ticker in tickers:
        path = _frame_cache_path("history", ticker, period, interval)
        if _is_fresh(path, 15 * 60):
            cached = _read_cached_frame(path)
            if not cached.empty:
                result[ticker] = cached
                continue
        missing.append(ticker)

    if missing:
        try:
            _provider_pause()
            downloaded = yf.download(
                tickers=" ".join(missing),
                period=period,
                interval=interval,
                group_by="ticker",
                auto_adjust=False,
                progress=False,
                threads=True,
                timeout=20,
            )
            for ticker in missing:
                frame = pd.DataFrame()
                if downloaded is not None and not downloaded.empty:
                    if isinstance(downloaded.columns, pd.MultiIndex):
                        if ticker in downloaded.columns.get_level_values(0):
                            frame = downloaded[ticker].dropna(how="all")
                        elif ticker in downloaded.columns.get_level_values(-1):
                            frame = downloaded.xs(ticker, axis=1, level=-1).dropna(how="all")
                    else:
                        frame = downloaded.dropna(how="all")
                frame = clean_ohlcv_frame(frame)
                if not frame.empty and {"Open", "High", "Low", "Close"}.issubset(frame.columns):
                    frame = frame.dropna(subset=["Open", "High", "Low", "Close"])
                    _write_cached_frame(_frame_cache_path("history", ticker, period, interval), frame)
                    result[ticker] = frame
        except Exception as exc:
            log_provider_failure("yfinance", "get_batch_price_history", ",".join(missing[:4]), exc)

    if fallback_missing:
        for ticker in missing:
            if ticker not in result:
                fallback = get_price_history(ticker, period=period, interval=interval)
                if not fallback.empty:
                    result[ticker] = fallback
    return result


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


def _read_resolved_symbol_cache(cache_key, max_age_hours=24 * 7):
    try:
        if not RESOLVED_SYMBOL_CACHE.exists():
            return None
        data = json.loads(RESOLVED_SYMBOL_CACHE.read_text(encoding="utf-8")).get(cache_key, {})
        if time.time() - data.get("created_at", 0) > max_age_hours * 3600:
            return None
        return data.get("payload")
    except Exception:
        return None


def _cache_resolved_symbol(cache_key, payload):
    try:
        RESOLVED_SYMBOL_CACHE.parent.mkdir(exist_ok=True)
        existing = {}
        if RESOLVED_SYMBOL_CACHE.exists():
            existing = json.loads(RESOLVED_SYMBOL_CACHE.read_text(encoding="utf-8"))
        existing[cache_key] = {"created_at": time.time(), "payload": payload}
        RESOLVED_SYMBOL_CACHE.write_text(json.dumps(existing), encoding="utf-8")
    except Exception:
        pass


def _ticker_has_recent_prices(ticker):
    try:
        history = get_price_history(ticker, period="5d", interval="1d")
        return history is not None and not history.empty and "Close" in history
    except Exception:
        return False


def _nse_equities():
    tickers = get_listed_stocks("NSE")
    rows = [
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
    known_tickers = {row["ticker"] for row in KNOWN_COMPANIES}
    rows = [row for row in rows if row["ticker"] not in known_tickers]
    return KNOWN_COMPANIES + rows


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
    cache_key = f"v3|nse={include_nse}|bse={include_bse}|etf={include_etfs}|fo={include_fo}"
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


def _normalize_lookup_text(value):
    text = str(value or "").upper()
    for token in ["LIMITED", "LTD", "PRIVATE", "PVT", "INDIA", "THE", "CO", "COMPANY"]:
        text = text.replace(token, " ")
    return "".join(ch for ch in text if ch.isalnum())


def resolve_ticker(query, universe=None, prefer_exchange="NSE"):
    clean = str(query or "").strip()
    if not clean:
        return None
    upper = clean.upper()
    if upper.startswith("^"):
        return {
            "ticker": upper,
            "symbol": upper,
            "display_name": display_symbol(upper),
            "exchange": "INDEX",
            "name": display_symbol(upper),
        }

    stripped_upper = upper.replace(".NS", "").replace(".BO", "")
    cache_key = _normalize_lookup_text(stripped_upper)
    cached = _read_resolved_symbol_cache(cache_key)
    if cached:
        return cached.copy()

    direct = KNOWN_LOOKUP.get(upper) or KNOWN_LOOKUP.get(stripped_upper)
    if direct:
        resolved = direct.copy()
        _cache_resolved_symbol(cache_key, resolved)
        return resolved

    rows = universe if universe is not None else get_market_universe(include_nse=True, include_bse=True)
    needle = _normalize_lookup_text(stripped_upper)
    for row in KNOWN_COMPANIES:
        known_fields = [_normalize_lookup_text(row.get(key)) for key in ["ticker", "symbol", "name", "display_name"]]
        if needle in known_fields or any(field and len(field) >= 4 and (field in needle or needle in field) for field in known_fields):
            resolved = row.copy()
            _cache_resolved_symbol(cache_key, resolved)
            return resolved

    exact = []
    partial = []
    for row in rows:
        fields = [
            row.get("ticker"),
            row.get("symbol"),
            row.get("name"),
            row.get("display_name"),
        ]
        haystacks = [_normalize_lookup_text(field) for field in fields if field]
        if needle in haystacks:
            exact.append(row)
        elif any(needle in hay or hay in needle for hay in haystacks):
            partial.append(row)

    matches = exact or partial
    if not matches and needle:
        fuzzy = []
        for row in rows:
            fields = [row.get("ticker"), row.get("symbol"), row.get("name"), row.get("display_name")]
            haystacks = [_normalize_lookup_text(field) for field in fields if field]
            score = max((SequenceMatcher(None, needle, hay).ratio() for hay in haystacks), default=0)
            if score >= 0.78:
                fuzzy.append((score, row))
        matches = [row for _, row in sorted(fuzzy, key=lambda item: item[0], reverse=True)[:8]]
    if matches:
        def rank(row):
            exchange_penalty = 0 if row.get("exchange") == prefer_exchange else 5
            ticker = str(row.get("ticker", ""))
            numeric_penalty = 4 if ticker.replace(".BO", "").isdigit() else 0
            symbol = _normalize_lookup_text(row.get("symbol") or row.get("ticker"))
            starts_penalty = 0 if symbol.startswith(needle) else 1
            symbol_len = len(symbol)
            return (exchange_penalty + numeric_penalty + starts_penalty, symbol_len)

        for best in sorted(matches, key=rank)[:6]:
            ticker = str(best.get("ticker", "")).upper()
            if ticker and _ticker_has_recent_prices(ticker):
                resolved = {
                    **best,
                    "display_name": best.get("name") or best.get("display_name") or display_symbol(best),
                }
                _cache_resolved_symbol(cache_key, resolved)
                return resolved

        best = sorted(matches, key=rank)[0]
        resolved = {
            **best,
            "display_name": best.get("name") or best.get("display_name") or display_symbol(best),
        }
        _cache_resolved_symbol(cache_key, resolved)
        return resolved

    guess_base = stripped_upper if stripped_upper else upper
    guesses = [f"{guess_base}.NS", f"{guess_base}.BO"] if "." not in guess_base else [guess_base]
    for ticker in guesses:
        if _ticker_has_recent_prices(ticker):
            exchange = "NSE" if ticker.endswith(".NS") else "BSE" if ticker.endswith(".BO") else ""
            resolved = {
                "ticker": ticker,
                "symbol": ticker.replace(".NS", "").replace(".BO", ""),
                "display_name": clean.replace(".NS", "").replace(".BO", "").title(),
                "exchange": exchange,
                "name": clean.replace(".NS", "").replace(".BO", "").title(),
            }
            _cache_resolved_symbol(cache_key, resolved)
            return resolved

    yahoo_guess = f"{guess_base}.NS" if "." not in guess_base else guess_base
    resolved = {
        "ticker": yahoo_guess,
        "symbol": yahoo_guess.replace(".NS", "").replace(".BO", ""),
        "display_name": clean.replace(".NS", "").replace(".BO", "").title(),
        "exchange": "NSE" if yahoo_guess.endswith(".NS") else "",
        "name": clean.replace(".NS", "").replace(".BO", "").title(),
    }
    _cache_resolved_symbol(cache_key, resolved)
    return resolved


def search_universe(query, universe=None, limit=12):
    rows = universe if universe is not None else get_market_universe(include_nse=True, include_bse=True)
    needle = _normalize_lookup_text(query)
    if not needle:
        preferred = {}
        for row in rows:
            key = _normalize_lookup_text(row.get("symbol") or row.get("name") or row.get("ticker"))
            current = preferred.get(key)
            if current is None or (current.get("exchange") != "NSE" and row.get("exchange") == "NSE"):
                preferred[key] = row
        return list(preferred.values())[:limit]
    scored = []
    for row in rows:
        text = " ".join(str(row.get(key, "")) for key in ["ticker", "symbol", "name", "display_name"])
        hay = _normalize_lookup_text(text)
        if needle in hay:
            symbol = _normalize_lookup_text(row.get("symbol") or row.get("ticker"))
            ticker = str(row.get("ticker", ""))
            score = 0 if symbol.startswith(needle) else 1
            if row.get("exchange") != "NSE":
                score += 5
            if ticker.replace(".BO", "").isdigit():
                score += 4
            scored.append((score, row))
    deduped = {}
    for _, row in sorted(scored, key=lambda item: (item[0], item[1].get("exchange") != "NSE")):
        key = _normalize_lookup_text(row.get("symbol") or row.get("name") or row.get("ticker"))
        if key not in deduped:
            deduped[key] = row
    return list(deduped.values())[:limit]


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
    weekly = get_price_history(ticker, period=period, interval="1wk")
    if weekly is None or weekly.empty:
        return pd.Series(dtype=float)

    return weekly["Close"].dropna()


def safe_info(ticker):
    ticker = str(ticker or "").upper().strip()
    path = _json_cache_path("info", ticker)
    if _is_fresh(path, 24 * 3600):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    stale = {}
    if path.exists():
        try:
            stale = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            stale = {}
    for attempt in range(2):
        try:
            _provider_pause(0.5)
            info = provider_manager.get_company_info(ticker) or {}
            if info:
                try:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(json.dumps(info, default=str), encoding="utf-8")
                except Exception:
                    pass
                return info
        except Exception as exc:
            log_provider_failure("DataProviderManager", "get_company_info", ticker, exc)
            time.sleep(0.8 * (2 ** attempt))
    try:
        _provider_pause(0.25)
        fast = get_stock(ticker).fast_info
        fast_info = dict(fast.items()) if hasattr(fast, "items") else dict(fast or {})
        if fast_info:
            mapped = {
                "shortName": fast_info.get("shortName") or fast_info.get("last_price"),
                "regularMarketPrice": fast_info.get("last_price") or fast_info.get("lastPrice"),
                "marketCap": fast_info.get("market_cap") or fast_info.get("marketCap"),
                "currency": fast_info.get("currency") or ("INR" if ticker.endswith((".NS", ".BO")) else "USD"),
                "exchange": "NSE" if ticker.endswith(".NS") else "BSE" if ticker.endswith(".BO") else fast_info.get("exchange"),
            }
            info = {**stale, **{k: v for k, v in mapped.items() if v is not None}}
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(info, default=str), encoding="utf-8")
            except Exception:
                pass
            return info
    except Exception:
        pass
    known = next((row for row in KNOWN_COMPANIES if row["ticker"] == ticker), None)
    if known:
        return {**stale, "shortName": known["name"], "longName": known["name"], "exchange": known["exchange"], "sector": known["sector"], "currency": "INR"}
    return stale


def safe_fast_info(ticker):
    known = next((row for row in KNOWN_COMPANIES if row["ticker"] == str(ticker).upper().strip()), None)
    if known:
        return {"shortName": known["name"], "longName": known["name"], "exchange": known["exchange"], "sector": known["sector"], "currency": "INR"}
    try:
        return safe_info(ticker)
    except Exception:
        return {}


def get_financial_frames(ticker):
    ticker = str(ticker or "").upper().strip()
    path = _frame_cache_path("financials", ticker)
    if _is_fresh(path, 24 * 3600):
        try:
            cached = pd.read_pickle(path)
            if isinstance(cached, dict):
                for key in ["financials", "quarterly_financials", "balance_sheet", "quarterly_balance_sheet", "cashflow", "quarterly_cashflow"]:
                    cached.setdefault(key, pd.DataFrame())
                return cached
        except Exception:
            pass
    try:
        frames = provider_manager.get_balance_sheet(ticker) or {}
    except Exception as exc:
        log_provider_failure("DataProviderManager", "get_balance_sheet", ticker, exc)
        frames = {}
    for key in ["financials", "quarterly_financials", "balance_sheet", "quarterly_balance_sheet", "cashflow", "quarterly_cashflow"]:
        value = frames.get(key, pd.DataFrame()) if isinstance(frames, dict) else pd.DataFrame()
        frames[key] = value if isinstance(value, pd.DataFrame) else pd.DataFrame()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        pd.to_pickle(frames, path)
    except Exception:
        pass
    return frames
