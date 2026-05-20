from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
import math
import time

import numpy as np
import pandas as pd
import yfinance as yf

from engines.data_service import DEFAULT_UNIVERSE, classify_sector, get_market_universe
from engines.stock_engine import analyze_stock


def _normalize_candidates(candidates):
    rows = []
    for item in candidates or []:
        if isinstance(item, dict):
            ticker = str(item.get("ticker", "")).upper().strip()
            if ticker:
                rows.append({
                    "ticker": ticker,
                    "symbol": item.get("symbol") or ticker.replace(".NS", "").replace(".BO", ""),
                    "display_name": item.get("display_name") or item.get("name") or ticker.replace(".NS", "").replace(".BO", ""),
                    "sector": item.get("sector") or classify_sector(ticker),
                    "exchange": item.get("exchange", "NSE" if ticker.endswith(".NS") else "BSE" if ticker.endswith(".BO") else ""),
                    "segment": item.get("segment", "Equity"),
                })
        else:
            ticker = str(item).upper().strip()
            if ticker:
                rows.append({
                    "ticker": ticker,
                    "symbol": ticker.replace(".NS", "").replace(".BO", ""),
                    "display_name": ticker.replace(".NS", "").replace(".BO", ""),
                    "sector": classify_sector(ticker),
                    "exchange": "",
                    "segment": "Equity",
                })
    return rows


def _rsi(close, window=14):
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(window).mean()
    loss = -delta.clip(upper=0).rolling(window).mean()
    rs = gain / loss.replace(0, np.nan)
    value = 100 - (100 / (1 + rs))
    return float(value.iloc[-1]) if not value.dropna().empty else 50.0


def _risk_label(atr_pct, risk_reward):
    if atr_pct > 6:
        return "High"
    if risk_reward >= 1.8 and atr_pct <= 3.5:
        return "Low-Medium"
    if risk_reward >= 1.2:
        return "Medium"
    return "Medium-High"


def _momentum_label(trend, expected_return):
    if trend == "Uptrend" and expected_return > 2:
        return "Bullish"
    if trend == "Downtrend" or expected_return < 0:
        return "Bearish"
    return "Neutral"


def _extract_symbol_frame(downloaded, ticker):
    if downloaded is None or downloaded.empty:
        return pd.DataFrame()
    if isinstance(downloaded.columns, pd.MultiIndex):
        if ticker in downloaded.columns.get_level_values(0):
            return downloaded[ticker].dropna(how="all")
        if ticker in downloaded.columns.get_level_values(-1):
            return downloaded.xs(ticker, axis=1, level=-1).dropna(how="all")
        return pd.DataFrame()
    return downloaded.dropna(how="all")


def _score_fast_candidate(meta, frame):
    required = {"Open", "High", "Low", "Close", "Volume"}
    if frame.empty or not required.issubset(set(frame.columns)):
        return None
    frame = frame.dropna(subset=["Open", "High", "Low", "Close"])
    if len(frame) < 45:
        return None

    close = frame["Close"].astype(float)
    high = frame["High"].astype(float)
    low = frame["Low"].astype(float)
    volume = frame["Volume"].fillna(0).astype(float)

    price = float(close.iloc[-1])
    sma20 = float(close.rolling(20).mean().iloc[-1])
    sma50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else sma20
    support = float(low.tail(20).min())
    resistance = float(high.tail(20).max())
    atr = float((high - low).tail(14).mean())
    atr_pct = (atr / price) * 100 if price else 0
    rsi = _rsi(close)
    ret_20 = ((price / float(close.iloc[-21])) - 1) * 100 if len(close) > 21 and close.iloc[-21] else 0
    ret_60 = ((price / float(close.iloc[-61])) - 1) * 100 if len(close) > 61 and close.iloc[-61] else ret_20
    avg_volume = float(volume.tail(20).mean()) if len(volume) >= 20 else 0
    volume_ratio = float(volume.iloc[-1] / avg_volume) if avg_volume else 1.0

    trend = "Uptrend" if price > sma20 > sma50 else "Downtrend" if price < sma20 < sma50 else "Sideways"
    stop_loss = min(price - (1.5 * atr), support * 0.98)
    target = max(price * (1 + max(ret_20, 1.5) / 100), resistance * 0.99)
    risk = max(price - stop_loss, 0)
    reward = max(target - price, 0)
    risk_reward = reward / risk if risk else 0
    expected_return = ((target / price) - 1) * 100 if price else 0

    score = 42
    score += 16 if trend == "Uptrend" else -10 if trend == "Downtrend" else 4
    score += min(max(ret_20, -8), 12) * 1.8
    score += min(max(ret_60, -12), 20) * 0.7
    score += 8 if 45 <= rsi <= 68 else -5 if rsi > 78 else 2
    score += min(risk_reward, 3) * 7
    score += 4 if volume_ratio >= 1.1 else 0
    score -= min(atr_pct, 10) * 1.2
    confidence = int(max(0, min(100, round(score))))

    if expected_return <= 0 or risk_reward < 0.75 or trend == "Downtrend" or confidence < 54:
        return None

    reason_parts = [
        f"{trend} price structure",
        f"{ret_20:.1f}% 20-session momentum",
        f"{risk_reward:.2f} risk-reward",
        f"{volume_ratio:.2f}x volume"
    ]

    return {
        "ticker": meta["ticker"],
        "symbol": meta.get("symbol") or meta["ticker"].replace(".NS", "").replace(".BO", ""),
        "display_name": meta.get("display_name") or meta.get("symbol") or meta["ticker"].replace(".NS", "").replace(".BO", ""),
        "action": "BUY",
        "sector": meta.get("sector") or classify_sector(meta["ticker"]),
        "exchange": meta.get("exchange", ""),
        "segment": meta.get("segment", "Equity"),
        "risk_level": _risk_label(atr_pct, risk_reward),
        "momentum": _momentum_label(trend, expected_return),
        "entry": round(price, 2),
        "stop_loss": round(stop_loss, 2),
        "target": round(target, 2),
        "risk_reward": round(risk_reward, 2),
        "confidence": confidence,
        "expected_return_pct": round(expected_return, 2),
        "holding_period": "1-4 weeks",
        "atr_pct": round(atr_pct, 2),
        "volume_ratio": round(volume_ratio, 2),
        "reason": "; ".join(reason_parts),
    }


def _download_chunk(tickers, period="6mo"):
    return yf.download(
        tickers=" ".join(tickers),
        period=period,
        interval="1d",
        group_by="ticker",
        auto_adjust=False,
        progress=False,
        threads=True,
    )


def _scan_chunk(rows):
    tickers = [row["ticker"] for row in rows]
    try:
        downloaded = _download_chunk(tickers)
    except Exception as exc:
        return [], [f"{tickers[0]}-{tickers[-1]}: {exc}"]

    analyzed = []
    errors = []
    for meta in rows:
        try:
            frame = _extract_symbol_frame(downloaded, meta["ticker"])
            scored = _score_fast_candidate(meta, frame)
            if scored:
                analyzed.append(scored)
        except Exception as exc:
            errors.append(f"{meta['ticker']}: {exc}")
    return analyzed, errors


def _rank_candidates(analyzed):
    return sorted(
        analyzed,
        key=lambda item: (
            item["confidence"],
            item["risk_reward"],
            item["expected_return_pct"],
            -item["atr_pct"],
        ),
        reverse=True,
    )


def _allocate_basket(capital, ranked, max_positions, risk_per_trade_pct):
    basket = []
    used_capital = 0
    sector_counts = {}
    max_single_allocation = capital * 0.40
    risk_budget = capital * (risk_per_trade_pct / 100)

    for item in ranked:
        if len(basket) >= max_positions:
            break
        sector = item.get("sector", "Unknown")
        if sector_counts.get(sector, 0) >= 2 and sector != "Other":
            continue

        entry = float(item["entry"])
        per_share_risk = max(entry - item["stop_loss"], 0)
        if per_share_risk <= 0:
            continue

        risk_based_qty = int(risk_budget / per_share_risk)
        allocation_qty = int(max_single_allocation / entry)
        remaining_qty = int((capital - used_capital) / entry)
        qty = max(0, min(risk_based_qty, allocation_qty, remaining_qty))
        if qty <= 0 and allocation_qty > 0 and remaining_qty > 0 and per_share_risk <= risk_budget * 1.5:
            qty = 1
        if qty <= 0:
            continue

        allocation = qty * entry
        used_capital += allocation
        sector_counts[sector] = sector_counts.get(sector, 0) + 1
        basket.append({
            **item,
            "qty": qty,
            "allocation": round(allocation, 2),
            "allocation_pct": round((allocation / capital) * 100, 2) if capital else 0,
        })

    return basket, used_capital


def _basket_response(capital, candidates, analyzed, errors, max_positions, risk_per_trade_pct, status="ok", elapsed=None, universe_size=None):
    ranked = _rank_candidates(analyzed)
    basket, used_capital = _allocate_basket(capital, ranked, max_positions, risk_per_trade_pct)
    return {
        "capital": capital,
        "used_capital": round(used_capital, 2),
        "cash_remaining": round(capital - used_capital, 2),
        "positions": basket,
        "basket_score": round(sum(item["confidence"] for item in basket) / len(basket), 2) if basket else 0,
        "scanned": len(candidates),
        "qualified": len(analyzed),
        "errors": errors[:12],
        "status": status,
        "elapsed": round(elapsed, 2) if elapsed is not None else None,
        "universe_size": universe_size or len(candidates),
        "notes": [
            f"Fast scan used batched OHLCV downloads for {len(candidates)} symbols instead of full per-stock AI analysis.",
            f"Found {len(analyzed)} technically qualified BUY setups before allocation constraints.",
            "The previous 2364-stock ceiling came from NSE equity-only listings; Quantara now combines NSE and BSE stocks by default.",
            "For very large universes, run sector or exchange batches to reduce Yahoo rate-limit pressure."
        ],
    }


def build_stock_basket(
    capital,
    candidates=None,
    max_positions=4,
    risk_per_trade_pct=1.5,
    scan_limit=80,
    progress_callback=None,
    max_workers=4,
    chunk_size=80,
):
    start = time.perf_counter()
    raw_candidates = candidates or get_market_universe(limit=scan_limit) or DEFAULT_UNIVERSE
    candidate_rows = _normalize_candidates(raw_candidates)[:scan_limit]
    if not candidate_rows:
        return _basket_response(capital, [], [], [], max_positions, risk_per_trade_pct, status="empty")

    analyzed = []
    errors = []
    chunks = [candidate_rows[index:index + chunk_size] for index in range(0, len(candidate_rows), chunk_size)]
    completed = 0

    with ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(chunks)))) as executor:
        future_map = {executor.submit(_scan_chunk, chunk): chunk for chunk in chunks}
        for future in as_completed(future_map):
            chunk = future_map[future]
            completed += len(chunk)
            try:
                chunk_analyzed, chunk_errors = future.result()
                analyzed.extend(chunk_analyzed)
                errors.extend(chunk_errors)
            except Exception as exc:
                errors.append(f"{chunk[0]['ticker']}-{chunk[-1]['ticker']}: {exc}")

            if progress_callback:
                progress_callback(
                    _basket_response(
                        capital,
                        candidate_rows[:completed],
                        analyzed,
                        errors,
                        max_positions,
                        risk_per_trade_pct,
                        status="scanning",
                        elapsed=time.perf_counter() - start,
                        universe_size=len(candidate_rows),
                    ),
                    completed,
                    len(candidate_rows),
                )

    return _basket_response(
        capital,
        candidate_rows,
        analyzed,
        errors,
        max_positions,
        risk_per_trade_pct,
        elapsed=time.perf_counter() - start,
        universe_size=len(candidate_rows),
    )


@lru_cache(maxsize=256)
def enrich_candidate_with_full_ai(ticker):
    return analyze_stock(ticker)
