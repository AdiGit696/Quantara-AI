import time

import pandas as pd
import requests
import yfinance as yf

import config
from cache.persistent_cache import cache
from utils.numbers import clean_ohlcv_frame, numeric_series
from utils.observability import log_provider_failure


class ProviderUnavailable(Exception):
    pass


class BaseProvider:
    name = "base"

    def get_price(self, ticker, period="1y", interval="1d"):
        raise ProviderUnavailable("price not implemented")

    def get_current_price(self, ticker):
        raise ProviderUnavailable("current price not implemented")

    def get_fundamentals(self, ticker):
        raise ProviderUnavailable("fundamentals not implemented")

    def get_balance_sheet(self, ticker):
        raise ProviderUnavailable("balance sheet not implemented")

    def get_news(self, ticker):
        raise ProviderUnavailable("news not implemented")

    def get_company_info(self, ticker):
        raise ProviderUnavailable("company info not implemented")


class IndianAPIProvider(BaseProvider):
    name = "IndianAPI"

    def __init__(self):
        self.enabled = config.USE_INDIANAPI and bool(config.INDIANAPI_KEY)
        self.base_url = config.INDIANAPI_BASE_URL.rstrip("/")

    def _get(self, path, params):
        if not self.enabled:
            raise ProviderUnavailable("IndianAPI disabled or INDIANAPI_KEY missing")
        headers = {"X-Api-Key": config.INDIANAPI_KEY}
        response = requests.get(f"{self.base_url}/{path.lstrip('/')}", params=params, headers=headers, timeout=12)
        response.raise_for_status()
        return response.json()

    def get_company_info(self, ticker):
        payload = self._get("stock", {"name": str(ticker).replace(".NS", "").replace(".BO", "")})
        if isinstance(payload, dict):
            return payload
        raise ProviderUnavailable("IndianAPI profile payload unavailable")

    def get_fundamentals(self, ticker):
        payload = self._get("fundamentals", {"name": str(ticker).replace(".NS", "").replace(".BO", "")})
        if isinstance(payload, dict):
            return payload
        raise ProviderUnavailable("IndianAPI fundamentals payload unavailable")

    def get_balance_sheet(self, ticker):
        payload = self._get("financials", {"name": str(ticker).replace(".NS", "").replace(".BO", "")})
        if isinstance(payload, dict):
            return payload
        raise ProviderUnavailable("IndianAPI financial payload unavailable")


class YFinanceProvider(BaseProvider):
    name = "yfinance"

    def __init__(self):
        self.enabled = config.USE_YFINANCE_FALLBACK

    def _stock(self, ticker):
        if not self.enabled:
            raise ProviderUnavailable("yfinance fallback disabled")
        return yf.Ticker(ticker)

    def get_price(self, ticker, period="1y", interval="1d"):
        if not self.enabled:
            raise ProviderUnavailable("yfinance fallback disabled")
        frame = yf.download(
            tickers=ticker,
            period=period,
            interval=interval,
            auto_adjust=False,
            progress=False,
            threads=False,
            timeout=12,
        )
        frame = clean_ohlcv_frame(frame)
        if frame.empty:
            frame = clean_ohlcv_frame(self._stock(ticker).history(period=period, interval=interval))
        if frame.empty:
            raise ProviderUnavailable("No price history available")
        return frame

    def get_current_price(self, ticker):
        frame = clean_ohlcv_frame(self._stock(ticker).history(period="1d", interval="1d"))
        if frame.empty or "Close" not in frame:
            raise ProviderUnavailable("No latest close price available")
        close = numeric_series(frame["Close"])
        if close.empty:
            raise ProviderUnavailable("No latest close price available")
        return float(close.iloc[-1])

    def get_company_info(self, ticker):
        info = self._stock(ticker).info or {}
        if info:
            return info
        fast = self._stock(ticker).fast_info
        fast_info = dict(fast.items()) if hasattr(fast, "items") else dict(fast or {})
        if not fast_info:
            raise ProviderUnavailable("No company info available")
        return {
            "regularMarketPrice": fast_info.get("last_price") or fast_info.get("lastPrice"),
            "marketCap": fast_info.get("market_cap") or fast_info.get("marketCap"),
            "currency": fast_info.get("currency") or ("INR" if str(ticker).endswith((".NS", ".BO")) else "USD"),
            "exchange": "NSE" if str(ticker).endswith(".NS") else "BSE" if str(ticker).endswith(".BO") else fast_info.get("exchange"),
        }

    def get_fundamentals(self, ticker):
        return self.get_company_info(ticker)

    def get_balance_sheet(self, ticker):
        stock = self._stock(ticker)

        def read_frame(attr):
            value = getattr(stock, attr)
            return value if value is not None else pd.DataFrame()

        return {
            "financials": read_frame("financials"),
            "quarterly_financials": read_frame("quarterly_financials"),
            "balance_sheet": read_frame("balance_sheet"),
            "quarterly_balance_sheet": read_frame("quarterly_balance_sheet"),
            "cashflow": read_frame("cashflow"),
            "quarterly_cashflow": read_frame("quarterly_cashflow"),
        }

    def get_news(self, ticker):
        return self._stock(ticker).news or []


class CacheProvider(BaseProvider):
    name = "cache"

    def get_price(self, ticker, period="1y", interval="1d"):
        frame = cache.get_pickle("price_history", f"{ticker}_{period}_{interval}", ttl_seconds=None, default=pd.DataFrame())
        if frame is None or frame.empty:
            raise ProviderUnavailable("Cached price history unavailable")
        return frame

    def get_company_info(self, ticker):
        info = cache.get_json("company_info", ticker, ttl_seconds=None, default={})
        if not info:
            raise ProviderUnavailable("Cached company info unavailable")
        return info

    def get_fundamentals(self, ticker):
        info = cache.get_json("fundamentals", ticker, ttl_seconds=None, default={})
        if not info:
            raise ProviderUnavailable("Cached fundamentals unavailable")
        return info

    def get_balance_sheet(self, ticker):
        frames = cache.get_pickle("financial_frames", ticker, ttl_seconds=None, default={})
        if not frames:
            raise ProviderUnavailable("Cached balance sheet unavailable")
        return frames

    def get_news(self, ticker):
        news = cache.get_json("news", ticker, ttl_seconds=None, default=[])
        if not news:
            raise ProviderUnavailable("Cached news unavailable")
        return news


class DataProviderManager:
    def __init__(self, providers=None, retries=2):
        self.providers = providers or [IndianAPIProvider(), YFinanceProvider(), CacheProvider()]
        self.retries = max(1, int(retries))

    def _call(self, method, ticker, *args, cache_namespace=None, cache_key=None, ttl_seconds=None, **kwargs):
        cache_key = cache_key or str(ticker)
        if cache_namespace:
            cached = cache.get_pickle(cache_namespace, cache_key, ttl_seconds=ttl_seconds)
            if cached is not None:
                if not hasattr(cached, "empty") or not cached.empty:
                    return cached

        last_exc = None
        for provider in self.providers:
            if hasattr(provider, "enabled") and not provider.enabled:
                continue
            fn = getattr(provider, method)
            for attempt in range(self.retries):
                try:
                    value = fn(ticker, *args, **kwargs)
                    if cache_namespace and value is not None:
                        cache.set_pickle(cache_namespace, cache_key, value)
                    return value
                except Exception as exc:
                    last_exc = exc
                    log_provider_failure(provider.name, method, ticker, exc)
                    time.sleep(0.25 * (2 ** attempt))
        raise ProviderUnavailable(str(last_exc or "All providers failed"))

    def get_price(self, ticker, period="1y", interval="1d"):
        return self._call(
            "get_price",
            ticker,
            period,
            interval,
            cache_namespace="price_history",
            cache_key=f"{ticker}_{period}_{interval}",
            ttl_seconds=config.CACHE_TTL_PRICE_SECONDS,
        )

    def get_current_price(self, ticker):
        last_exc = None
        for provider in self.providers:
            if isinstance(provider, CacheProvider):
                continue
            if hasattr(provider, "enabled") and not provider.enabled:
                continue
            try:
                return provider.get_current_price(ticker)
            except Exception as exc:
                last_exc = exc
                log_provider_failure(provider.name, "get_current_price", ticker, exc)
        raise ProviderUnavailable(str(last_exc or "Fresh current price unavailable"))

    def get_fundamentals(self, ticker):
        return self._call("get_fundamentals", ticker, cache_namespace="fundamentals", ttl_seconds=config.CACHE_TTL_FUNDAMENTALS_SECONDS)

    def get_balance_sheet(self, ticker):
        return self._call("get_balance_sheet", ticker, cache_namespace="financial_frames", ttl_seconds=config.CACHE_TTL_FUNDAMENTALS_SECONDS)

    def get_news(self, ticker):
        return self._call("get_news", ticker, cache_namespace="news", ttl_seconds=config.CACHE_TTL_NEWS_SECONDS)

    def get_company_info(self, ticker):
        return self._call("get_company_info", ticker, cache_namespace="company_info", ttl_seconds=config.CACHE_TTL_PROFILE_SECONDS)


provider_manager = DataProviderManager()
