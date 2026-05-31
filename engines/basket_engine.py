from concurrent.futures import ThreadPoolExecutor, as_completed
import math
import time

import numpy as np
import pandas as pd

from engines.data_service import DEFAULT_UNIVERSE, KNOWN_COMPANIES, classify_sector, get_batch_price_history, get_market_universe
from engines.formatting import detect_market
from engines.prescreen import score_candidates
from engines.risk_engine import calculate_trade_plan
from engines.scoring_engine import build_scorecard
from utils.numbers import numeric_series
from utils.observability import log_performance, log_symbol_failure


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

    close = numeric_series(frame["Close"])
    high = numeric_series(frame["High"]).reindex(close.index).dropna()
    low = numeric_series(frame["Low"]).reindex(close.index).dropna()
    volume = numeric_series(frame["Volume"]).reindex(close.index).fillna(0)
    if close.empty or high.empty or low.empty:
        return None

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
    risk_plan = calculate_trade_plan(
        current_price=price,
        atr_value=atr,
        support=support,
        resistance=resistance,
        prediction={"future_30": price * (1 + max(ret_20, 0) / 100), "expected_return_pct": ret_20},
    )
    stop_loss = risk_plan["stop_loss"]
    target = risk_plan["target"]
    risk_reward = risk_plan["risk_reward"]
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
    scorecard = build_scorecard(
        probability=confidence,
        uncertainty=18 + max(0, atr_pct - 4),
        risk_pct=risk_plan["risk_pct"],
        atr_pct=atr_pct,
        risk_reward=risk_reward,
        fundamental_score=50,
        expected_return_pct=expected_return,
        trend=trend,
    )
    market = detect_market(meta["ticker"], meta.get("exchange"))

    if expected_return <= 0 or risk_reward < 1.8 or atr_pct > 8.5 or trend == "Downtrend" or confidence < 54:
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
        "quantara_score": scorecard["quantara_score"],
        "ai_score": scorecard["ai_score"],
        "confidence_score": scorecard["confidence_score"],
        "risk_score": scorecard["risk_score"],
        "decision_score": scorecard["decision_score"],
        "current_price": round(price, 2),
        "currency_symbol": market["symbol"],
        "probability_model": "Fast Momentum Risk Model",
        "expected_return_pct": round(expected_return, 2),
        "holding_period": "1-4 weeks",
        "atr_pct": round(atr_pct, 2),
        "volume_ratio": round(volume_ratio, 2),
        "reason": "; ".join(reason_parts),
    }


def _download_chunk(tickers, period="6mo"):
    return get_batch_price_history(tickers, period=period, interval="1d", fallback_missing=False)


def prescreen_market_candidates(candidates, keep_ratio=0.15, period="3mo", chunk_size=80, max_workers=4, progress_callback=None):
    candidate_rows = _normalize_candidates(candidates)
    if not candidate_rows:
        return []
    chunks = [candidate_rows[index:index + chunk_size] for index in range(0, len(candidate_rows), chunk_size)]
    scores = []

    def score_chunk(rows):
        tickers = [row["ticker"] for row in rows]
        return score_candidates(_download_chunk(tickers, period=period))

    with ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(chunks)))) as executor:
        future_map = {executor.submit(score_chunk, chunk): chunk for chunk in chunks}
        completed = 0
        for future in as_completed(future_map):
            completed += len(future_map[future])
            try:
                scores.extend(future.result())
            except Exception as exc:
                log_symbol_failure("prescreen", "batch", exc)
            if progress_callback:
                progress_callback(completed, len(candidate_rows))

    if not scores:
        return []
    keep = max(10, int(len(scores) * keep_ratio))
    ranked_tickers = {ticker for ticker, _ in sorted(scores, key=lambda item: item[1], reverse=True)[:keep]}
    return [row for row in candidate_rows if row["ticker"] in ranked_tickers]


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
            frame = downloaded.get(meta["ticker"], pd.DataFrame()) if isinstance(downloaded, dict) else _extract_symbol_frame(downloaded, meta["ticker"])
            scored = _score_fast_candidate(meta, frame)
            if scored:
                analyzed.append(scored)
        except Exception as exc:
            log_symbol_failure("scan", meta["ticker"], exc)
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


def _basket_response(capital, candidates, analyzed, errors, max_positions, risk_per_trade_pct, status="ok", elapsed=None, universe_size=None, scanned_count=None):
    ranked = _rank_candidates(analyzed)
    basket, used_capital = _allocate_basket(capital, ranked, max_positions, risk_per_trade_pct)
    scanned = len(candidates) if scanned_count is None else scanned_count
    rejected = max(0, scanned - len(analyzed) - len(errors))
    return {
        "capital": capital,
        "used_capital": round(used_capital, 2),
        "cash_remaining": round(capital - used_capital, 2),
        "positions": basket,
        "basket_score": round(sum(item["confidence"] for item in basket) / len(basket), 2) if basket else 0,
        "scanned": scanned,
        "deep_scanned": len(candidates),
        "qualified": len(analyzed),
        "rejected": rejected,
        "errors": errors[:12],
        "status": status,
        "elapsed": round(elapsed, 2) if elapsed is not None else None,
        "universe_size": universe_size or len(candidates),
        "notes": [
            f"Fast scan used batched OHLCV downloads for {len(candidates)} symbols instead of full per-stock AI analysis.",
            f"Found {len(analyzed)} technically qualified BUY setups before allocation constraints.",
            "Quantara resolves the best available listing internally and prioritizes the most liquid valid source.",
            "For very large universes, run sector batches to reduce provider rate-limit pressure."
        ],
    }


def build_stock_basket(
    capital,
    candidates=None,
    max_positions=4,
    risk_per_trade_pct=1.5,
    scan_limit=None,
    progress_callback=None,
    max_workers=6,
    chunk_size=30,
    universe_size=None,
):
    start = time.perf_counter()
    raw_candidates = (get_market_universe(limit=scan_limit) or DEFAULT_UNIVERSE) if candidates is None else candidates
    candidate_rows = _normalize_candidates(raw_candidates)
    if scan_limit is not None:
        candidate_rows = candidate_rows[:scan_limit]
    if not candidate_rows:
        return _basket_response(
            capital,
            [],
            [],
            [],
            max_positions,
            risk_per_trade_pct,
            status="empty",
            universe_size=universe_size or 0,
            scanned_count=universe_size or 0,
        )

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
                        universe_size=universe_size or len(candidate_rows),
                        scanned_count=completed,
                    ),
                    completed,
                    len(candidate_rows),
                )

    response = _basket_response(
        capital,
        candidate_rows,
        analyzed,
        errors,
        max_positions,
        risk_per_trade_pct,
        elapsed=time.perf_counter() - start,
        universe_size=universe_size or len(candidate_rows),
        scanned_count=universe_size or len(candidate_rows),
    )
    log_performance("swing_scan", time.perf_counter() - start, count=len(candidate_rows), status="partial" if response.get("errors") else "ok")
    return response


def build_investing_basket(
    capital,
    candidates=None,
    horizon="3 Years",
    max_positions=6,
    scan_limit=None,
    progress_callback=None,
    chunk_size=80,
    universe_size=None,
):
    start = time.perf_counter()
    base = _normalize_candidates(KNOWN_COMPANIES if candidates is None else candidates)
    known_tickers = {row["ticker"] for row in KNOWN_COMPANIES}
    priority = [row for row in KNOWN_COMPANIES if candidates is None or row["ticker"] in {item.get("ticker") if isinstance(item, dict) else str(item).upper() for item in candidates}]
    candidate_rows = priority + [row for row in base if row["ticker"] not in known_tickers]
    if scan_limit is not None:
        candidate_rows = candidate_rows[:scan_limit]
    horizon_years = {"1 Year": 1, "3 Years": 3, "Long Term": 5}.get(horizon, 3)
    positions = []
    errors = []
    history_cache = {}
    for start_index in range(0, len(candidate_rows), chunk_size):
        chunk = candidate_rows[start_index:start_index + chunk_size]
        history_cache.update(get_batch_price_history([row["ticker"] for row in chunk], period="5y", interval="1d", fallback_missing=False))
        if progress_callback:
            live = sorted(positions, key=lambda row: (row["long_term_confidence"], row["estimated_cagr"]), reverse=True)[:max_positions]
            progress_callback({"positions": live, "errors": errors[:8]}, start_index, len(candidate_rows))

    for index, meta in enumerate(candidate_rows, start=1):
        frame = history_cache.get(meta["ticker"], pd.DataFrame())
        if frame.empty or len(frame) < 180:
            errors.append(f"{meta['display_name']}: insufficient history")
            if progress_callback:
                progress_callback({"positions": positions[:max_positions], "errors": errors[:8]}, index, len(candidate_rows))
            continue
        close = numeric_series(frame["Close"])
        if len(close) < 180:
            continue
        price = float(close.iloc[-1])
        one_year = ((price / float(close.iloc[-252])) - 1) * 100 if len(close) >= 252 else ((price / float(close.iloc[0])) - 1) * 100
        three_year = ((price / float(close.iloc[-756])) ** (252 / min(len(close), 756)) - 1) * 100 if len(close) >= 360 else one_year
        five_year = ((price / float(close.iloc[0])) ** (252 / len(close)) - 1) * 100
        volatility = float(close.pct_change().dropna().std() * math.sqrt(252) * 100)
        drawdown = abs(float(((close / close.cummax()) - 1).min() * 100))
        sma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else float(close.mean())
        trend_quality = 72 if price >= sma200 else 54
        quality_bias = 16 if meta["ticker"] in known_tickers else 0
        volatility_quality = max(0, 100 - volatility * 1.15 - drawdown * 0.35)
        growth_quality = max(0, min(100, (max(one_year, 0) * 1.2) + (max(three_year, 0) * 1.8) + (max(five_year, 0) * 2.0)))
        long_term_confidence = round(min(100, trend_quality * 0.24 + volatility_quality * 0.30 + growth_quality * 0.30 + 42 * 0.16 + quality_bias), 2)
        if long_term_confidence < 45 and meta["ticker"] not in known_tickers:
            if progress_callback:
                live = sorted(positions, key=lambda row: (row["long_term_confidence"], row["estimated_cagr"]), reverse=True)[:max_positions]
                progress_callback({"positions": live, "errors": errors[:8]}, index, len(candidate_rows))
            continue
        expected_cagr = round(max(4, min(22, (three_year * 0.45) + (five_year * 0.35) + (one_year * 0.10) + (long_term_confidence * 0.05))), 2)
        target_price = round(price * ((1 + expected_cagr / 100) ** horizon_years), 2)
        scorecard = build_scorecard(
            probability=long_term_confidence,
            uncertainty=max(12, min(34, volatility / 2)),
            risk_pct=drawdown / 3,
            atr_pct=volatility / 8,
            risk_reward=max(expected_cagr / 6, 1),
            fundamental_score=68 if meta["ticker"] in known_tickers else 55,
            expected_return_pct=((target_price / price) - 1) * 100,
            trend="Uptrend" if price >= sma200 else "Sideways",
        )
        market = detect_market(meta["ticker"], meta.get("exchange"))
        qty = int((capital / max_positions) / price) if price and max_positions else 0
        allocation = round(qty * price, 2)
        positions.append({
            "ticker": meta["ticker"],
            "symbol": meta.get("symbol"),
            "display_name": meta.get("display_name") or meta.get("name") or meta.get("symbol"),
            "sector": meta.get("sector", "Unknown"),
            "exchange": meta.get("exchange", "NSE"),
            "current_price": round(price, 2),
            "entry": round(price, 2),
            "target": target_price,
            "stop_loss": "Long-term review below 200DMA",
            "risk_reward": round(max(expected_cagr / max(volatility / 5, 1), 0.5), 2),
            "confidence": round(long_term_confidence),
            "quantara_score": scorecard["quantara_score"],
            "ai_score": scorecard["ai_score"],
            "confidence_score": scorecard["confidence_score"],
            "risk_score": scorecard["risk_score"],
            "decision_score": scorecard["decision_score"],
            "currency_symbol": market["symbol"],
            "probability_model": "Long-Term Quality CAGR Model",
            "expected_return_pct": round(((target_price / price) - 1) * 100, 2),
            "atr_pct": round(volatility / 8, 2),
            "volume_ratio": 1,
            "qty": qty,
            "allocation": allocation,
            "allocation_pct": round((allocation / capital) * 100, 2) if capital else 0,
            "momentum": "Compounding Uptrend" if price >= sma200 else "Quality Watchlist",
            "risk_level": "Core" if scorecard["risk_score"] >= 68 else "Satellite",
            "long_term_confidence": long_term_confidence,
            "estimated_cagr": expected_cagr,
            "one_year_outlook": round(price * ((1 + expected_cagr / 100) ** 1), 2),
            "three_year_outlook": round(price * ((1 + expected_cagr / 100) ** 3), 2),
            "five_year_potential": round(price * ((1 + expected_cagr / 100) ** 5), 2),
            "investment_thesis": f"Market-leader style {meta.get('sector', 'business')} exposure with {expected_cagr}% estimated CAGR, {round(volatility, 2)}% annualized volatility, and long-term review discipline.",
            "risk_profile": "Core Compounder" if scorecard["risk_score"] >= 68 else "Satellite Compounder",
            "horizon": horizon,
        })
        if progress_callback:
            live = sorted(positions, key=lambda row: (row["long_term_confidence"], row["estimated_cagr"]), reverse=True)[:max_positions]
            progress_callback(
                {
                    "positions": live,
                    "basket_score": round(sum(item["long_term_confidence"] for item in live) / len(live), 2) if live else 0,
                    "scanned": len(positions),
                    "qualified": len(live),
                    "errors": errors[:8],
                },
                index,
                len(candidate_rows),
            )
    positions = sorted(positions, key=lambda row: (row["long_term_confidence"], row["estimated_cagr"]), reverse=True)[:max_positions]
    used_capital = sum(float(item.get("allocation", 0) or 0) for item in positions)
    response = {
        "capital": capital,
        "used_capital": round(used_capital, 2),
        "cash_remaining": round(capital - used_capital, 2),
        "positions": positions,
        "basket_score": round(sum(item["long_term_confidence"] for item in positions) / len(positions), 2) if positions else 0,
        "scanned": universe_size or len(candidate_rows),
        "deep_scanned": len(candidate_rows),
        "qualified": len(positions),
        "errors": errors[:8],
        "status": "ok",
        "elapsed": None,
        "universe_size": universe_size or len(candidate_rows),
        "notes": [
        f"Investing basket optimized for {horizon.lower()} compounding rather than short swing exits.",
        "Ranking favors large-cap quality, trend durability, lower drawdown, CAGR potential, and sector balance.",
        "Use this as a research shortlist; validate fundamentals before capital deployment.",
        ],
    }
    log_performance("long_term_scan", time.perf_counter() - start, count=len(candidate_rows), status="partial" if errors else "ok")
    return response
