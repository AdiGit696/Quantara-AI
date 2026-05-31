import logging
import time
from contextlib import contextmanager
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)


ERROR_CATEGORIES = {
    "provider": "provider_failure",
    "portfolio": "portfolio_symbol_failure",
    "scan": "scan_symbol_failure",
    "performance": "performance",
    "data": "data_quality",
    "app": "application",
}


def _logger(name, filename):
    logger = logging.getLogger(f"quantara.{name}")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    logger.propagate = False
    handler = logging.FileHandler(LOG_DIR / filename, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(handler)
    return logger


provider_logger = _logger("provider", "provider_errors.log")
scan_logger = _logger("scan", "scan_errors.log")
portfolio_logger = _logger("portfolio", "portfolio_errors.log")
performance_logger = _logger("performance", "performance.log")


def compact_error(exc):
    text = str(exc or "").strip()
    if not text:
        return exc.__class__.__name__ if exc else "Unknown error"
    return text.splitlines()[0][:240]


def log_provider_failure(provider, method, symbol, exc, category="provider_failure"):
    provider_logger.warning(
        "category=%s provider=%s method=%s symbol=%s error=%s",
        category,
        provider,
        method,
        symbol or "-",
        compact_error(exc),
    )


def log_symbol_failure(area, symbol, exc, category=None):
    logger = portfolio_logger if area == "portfolio" else scan_logger
    logger.warning(
        "category=%s symbol=%s error=%s",
        category or ERROR_CATEGORIES.get(area, "symbol_failure"),
        symbol or "-",
        compact_error(exc),
    )


def log_data_quality(symbol, message):
    provider_logger.info("category=data_quality symbol=%s message=%s", symbol or "-", message)


def log_performance(operation, elapsed, count=None, status="ok"):
    performance_logger.info(
        "operation=%s elapsed=%.3fs count=%s status=%s",
        operation,
        float(elapsed or 0),
        "-" if count is None else count,
        status,
    )


@contextmanager
def timed_operation(operation, count=None):
    start = time.perf_counter()
    status = "ok"
    try:
        yield
    except Exception:
        status = "error"
        raise
    finally:
        log_performance(operation, time.perf_counter() - start, count=count, status=status)

