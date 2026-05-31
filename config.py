import os


def _flag(name, default):
    value = os.getenv(name)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


USE_INDIANAPI = _flag("USE_INDIANAPI", True)
USE_YFINANCE_FALLBACK = _flag("USE_YFINANCE_FALLBACK", True)
ENABLE_LONGTERM_SCAN = _flag("ENABLE_LONGTERM_SCAN", True)
ENABLE_MUTUAL_FUNDS = _flag("ENABLE_MUTUAL_FUNDS", False)
ENABLE_NEWS = _flag("ENABLE_NEWS", True)

CACHE_TTL_PRICE_SECONDS = int(os.getenv("CACHE_TTL_PRICE_SECONDS", "900"))
CACHE_TTL_FUNDAMENTALS_SECONDS = int(os.getenv("CACHE_TTL_FUNDAMENTALS_SECONDS", "86400"))
CACHE_TTL_PROFILE_SECONDS = int(os.getenv("CACHE_TTL_PROFILE_SECONDS", "86400"))
CACHE_TTL_NEWS_SECONDS = int(os.getenv("CACHE_TTL_NEWS_SECONDS", "1800"))

INDIANAPI_KEY = os.getenv("INDIANAPI_KEY", "")
INDIANAPI_BASE_URL = os.getenv("INDIANAPI_BASE_URL", "https://stock.indianapi.in")



FAST_SCAN_MODE = _flag("FAST_SCAN_MODE", True)
BASKET_WORKERS = int(os.getenv("BASKET_WORKERS", "4"))
SCAN_CHUNK = int(os.getenv("SCAN_CHUNK", "80"))
PRESCREEN_PERCENT = float(os.getenv("PRESCREEN_PERCENT", "0.15"))
