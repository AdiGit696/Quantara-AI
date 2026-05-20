import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

from engines.backtester import compare_strategies, run_backtest
from engines.basket_engine import build_stock_basket
from engines.data_service import SECTOR_OPTIONS, get_market_universe, get_price_history
from engines.news_engine import aggregate_news_sentiment, get_news
from engines.stock_engine import analyze_stock
from portfolio_analyzer import analyze_uploaded_portfolio
from ui_components import (
    BLUE,
    CYAN,
    GREEN,
    RED,
    YELLOW,
    apply_chart_theme,
    basket_cards,
    brand_header,
    candlestick_chart,
    confidence_ring,
    decision_badge,
    equity_curve_chart,
    footer,
    fundamentals_chart,
    health_meter,
    inject_theme,
    insight_card,
    probability_summary,
    scan_skeleton,
    compact_alert,
    section_help,
)


APP_NAME = "Quantara AI"
APP_DIR = Path(__file__).parent
STATE_DIR = APP_DIR / ".quantara"
STATE_DIR.mkdir(exist_ok=True)
NOTES_FILE = STATE_DIR / "notes.txt"
WATCHLIST_FILE = STATE_DIR / "watchlist.json"


st.set_page_config(page_title=APP_NAME, page_icon=str(APP_DIR / "assets" / "favicon.svg"), layout="wide")
inject_theme()


@st.cache_data(ttl=900, show_spinner=False)
def cached_stock_analysis(ticker):
    return analyze_stock(ticker)


@st.cache_data(ttl=900, show_spinner=False)
def cached_news(ticker):
    return get_news(ticker)


@st.cache_data(ttl=86400, show_spinner=False)
def cached_market_universe():
    return get_market_universe()


@st.cache_data(ttl=900, show_spinner=False)
def cached_price_history(ticker):
    return get_price_history(ticker, period="5d")


@st.cache_data(ttl=1800, show_spinner=False)
def cached_history(ticker, period="1y"):
    return get_price_history(ticker, period=period)


def tradingview_symbol(ticker):
    clean_ticker = ticker.upper().strip()
    if clean_ticker.endswith(".NS"):
        return f"NSE:{clean_ticker[:-3]}"
    if clean_ticker.endswith(".BO"):
        return f"BSE:{clean_ticker[:-3]}"
    return clean_ticker


def show_tradingview_chart(ticker):
    symbol = tradingview_symbol(ticker)
    html = f"""
    <style>
      html, body {{ margin:0; padding:0; width:100%; height:100%; background:#071525; color:#E7F8FF; }}
      .tv-wrap {{
        width: 100%;
        height: 760px;
        min-height: 560px;
        border: 1px solid rgba(98,245,255,.16);
        border-radius: 8px;
        overflow: hidden;
        background: #071525;
      }}
      #tradingview_chart {{ width:100%; height:100%; }}
      @media (max-width: 900px) {{ .tv-wrap {{ height: 620px; min-height: 420px; }} }}
    </style>
    <div class="tv-wrap">
      <div id="tradingview_chart"></div>
    </div>
    <script src="https://s3.tradingview.com/tv.js"></script>
    <script>
    new TradingView.widget({{
        "autosize": true,
        "symbol": "{symbol}",
        "interval": "D",
        "timezone": "Asia/Kolkata",
        "theme": "dark",
        "style": "1",
        "locale": "en",
        "hide_side_toolbar": false,
        "allow_symbol_change": true,
        "container_id": "tradingview_chart"
    }});
    </script>
    """
    components.html(html, height=780)


def read_notes():
    if NOTES_FILE.exists():
        return NOTES_FILE.read_text(encoding="utf-8")
    return ""


def write_notes():
    NOTES_FILE.write_text(st.session_state.get("trading_notes", ""), encoding="utf-8")


def read_watchlist():
    if WATCHLIST_FILE.exists():
        try:
            return json.loads(WATCHLIST_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return ["RELIANCE.NS", "TCS.NS", "INFY.NS"]
    return ["RELIANCE.NS", "TCS.NS", "INFY.NS"]


def write_watchlist(items):
    WATCHLIST_FILE.write_text(json.dumps(items, indent=2), encoding="utf-8")


def render_sidebar_tools():
    brand_header()
    st.sidebar.markdown("<div class='q-section-title'>Workspace</div>", unsafe_allow_html=True)
    mode = st.sidebar.radio("Workspace mode", ["Stock Terminal", "Portfolio", "Stock Basket", "Stock Comparison"], label_visibility="collapsed")

    if "trading_notes" not in st.session_state:
        st.session_state["trading_notes"] = read_notes()
    if "watchlist" not in st.session_state:
        st.session_state["watchlist"] = read_watchlist()

    st.sidebar.markdown("<div class='q-section-title'>Notes</div>", unsafe_allow_html=True)
    st.sidebar.text_area(
        "Trading notes",
        key="trading_notes",
        height=160,
        label_visibility="collapsed",
        placeholder="Market observations, setups, risk notes...",
        on_change=write_notes,
    )

    st.sidebar.markdown("<div class='q-section-title'>Watchlist</div>", unsafe_allow_html=True)
    new_symbol = st.sidebar.text_input("Add symbol", placeholder="E.g. HDFCBANK.NS", key="watch_add")
    add_col, clear_col = st.sidebar.columns([1, 1])
    if add_col.button("Add", use_container_width=True) and new_symbol:
        symbol = new_symbol.upper().strip()
        if symbol and symbol not in st.session_state["watchlist"]:
            st.session_state["watchlist"].append(symbol)
            write_watchlist(st.session_state["watchlist"])
    if clear_col.button("Clear", use_container_width=True):
        st.session_state["watchlist"] = []
        write_watchlist([])

    for symbol in st.session_state["watchlist"][:12]:
        try:
            display = symbol.replace(".NS", "").replace(".BO", "")
            hist = cached_price_history(symbol)["Close"].dropna()
            price = float(hist.iloc[-1])
            prev = float(hist.iloc[-2]) if len(hist) > 1 else price
            change = ((price / prev) - 1) * 100 if prev else 0
            cls = "watch-pos" if change > 0 else "watch-neg" if change < 0 else "watch-flat"
            st.sidebar.markdown(
                f"""
                <div class="watch-row">
                    <b>{display}</b>
                    <span>Rs. {price:.2f}</span>
                    <span class="{cls}">{change:+.2f}%</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.sidebar.caption("Tracking | signal opens in terminal")
        except Exception:
            st.sidebar.caption(f"{symbol} | data unavailable")
        remove_key = f"remove_{symbol}"
        if st.sidebar.button("Remove", key=remove_key, use_container_width=True):
            st.session_state["watchlist"] = [item for item in st.session_state["watchlist"] if item != symbol]
            write_watchlist(st.session_state["watchlist"])
            st.rerun()
    return mode


def render_stock_terminal():
    ticker = st.sidebar.text_input("Ticker", "TCS.NS").upper().strip()
    chart_mode = st.sidebar.radio("Chart Source", ["Plotly Native", "TradingView"], horizontal=False)

    try:
        with st.spinner("Running AI quant analysis..."):
            result = cached_stock_analysis(ticker)
    except Exception as exc:
        compact_alert(
            "Analysis temporarily unavailable",
            "The market data provider throttled or failed this request. Wait briefly, retry, or switch to a lighter module like Stock Basket.",
            level="error",
            details=exc,
        )
        if st.button("Retry analysis"):
            st.cache_data.clear()
            st.rerun()
        return

    st.title(APP_NAME)
    st.caption("AI-powered swing trading ecosystem for institutional-style swing trading decisions")
    section_help("Stock Terminal", "Runs full AI analysis for one ticker: price structure, fundamentals, technicals, probability, risk plan, backtesting, and news sentiment. This is intentionally heavier than basket scanning.")

    k1, k2, k3, k4, k5 = st.columns([1, 1, 1, 1, 1])
    k1.metric("Price", f"Rs. {result['price']:.2f}")
    k2.metric("Decision", result["decision"])
    with k3:
        confidence_ring(result["trade_confidence"])
    k4.metric("Risk", result["risk_level"])
    k5.metric("Holding", result["holding_period"])
    decision_badge(result["decision"], result["trade_confidence"])

    terminal_view = st.radio("Terminal View", [
        "Dashboard",
        "Chart",
        "Fundamentals",
        "Technical & Patterns",
        "Probability & Risk",
        "Backtesting",
        "News"
    ], horizontal=True, label_visibility="collapsed")

    if terminal_view == "Dashboard":
        section_help("Dashboard", "Summarizes trend, expected return, risk-reward, uncertainty, and the AI decision rationale.")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Trend", result["trend"])
        c2.metric("Expected 30d", f"{result['expected_return_pct']:.2f}%")
        c3.metric("Risk-Reward", f"{result['risk_reward']:.2f}")
        c4.metric("Uncertainty", f"{result['uncertainty']}%")

        insight_card("AI Trade Summary", result["probability_reasons"])
        insight_card("Decision Logic", result["decision_reasons"])

    elif terminal_view == "Chart":
        section_help("Chart", "Displays either Quantara's dark Plotly candlestick view or an embedded TradingView chart.")
        if chart_mode == "TradingView":
            show_tradingview_chart(ticker)
        else:
            candlestick_chart(
                result["history"],
                title=f"{ticker} Price Structure",
                support=result["support"],
                resistance=result["resistance"]
            )

    elif terminal_view == "Fundamentals":
        section_help("Fundamentals", "Scores growth, margins, debt, valuation, cash flow, and data quality from available financial statements.")
        fundamentals = result["fundamentals"]
        f1, f2, f3 = st.columns(3)
        f1.metric("Fundamental Rating", fundamentals["rating"])
        f2.metric("Fundamental Score", f"{fundamentals['score']}%")
        f3.metric("Data Quality", fundamentals["data_quality"])

        metrics = fundamentals["metrics"]
        metric_rows = [{"Metric": key.replace("_", " ").title(), "Value": value} for key, value in metrics.items()]
        st.dataframe(metric_rows, use_container_width=True)
        fundamentals_chart(fundamentals["trend_data"])
        insight_card("Fundamental Explanation", fundamentals["insights"])

    elif terminal_view == "Technical & Patterns":
        section_help("Technical & Patterns", "Shows RSI, MACD, ATR, volume strength, support/resistance, breakout state, and detected price patterns.")
        t1, t2, t3, t4 = st.columns(4)
        t1.metric("RSI", f"{result['rsi']:.2f}")
        t2.metric("MACD", f"{result['macd']:.2f}")
        t3.metric("ATR", f"{result['atr']:.2f}")
        t4.metric("Volume", f"{result['volume_ratio']:.2f}x")

        st.write("### Price Structure")
        st.dataframe([{
            "Support": round(result["support"], 2),
            "Resistance": round(result["resistance"], 2),
            "Zone": result["zone"],
            "Breakout": result["breakout"],
            "Structure": result["structure"],
            "Consolidation": result["consolidation"]
        }], use_container_width=True)

        st.write("### Detected Patterns")
        st.dataframe(result["patterns"], use_container_width=True)

    elif terminal_view == "Probability & Risk":
        section_help("Probability & Risk", "Combines forecast, trend, volume, structure, patterns, fundamentals, sentiment, ATR risk, stop loss, and target quality.")
        r1, r2, r3, r4 = st.columns(4)
        r1.metric("Entry", f"Rs. {result['price']:.2f}")
        r2.metric("Stop Loss", f"Rs. {result['stop_loss']:.2f}")
        r3.metric("Target", f"Rs. {result['target']:.2f}")
        r4.metric("ATR Volatility", f"{result['atr_pct']:.2f}%")
        probability_summary(result.get("probability_model", {}))
        insight_card("Probability Model", result["probability_reasons"])

    elif terminal_view == "Backtesting":
        section_help("Backtesting", "Runs a historical strategy simulation only after you click Run Backtest; results are cached in session state.")
        b1, b2, b3, b4 = st.columns(4)
        capital = b1.number_input("Capital", min_value=1000, value=10000, step=1000)
        holding_days = b2.number_input("Holding Days", min_value=5, max_value=60, value=20, step=5)
        risk_level = b3.selectbox("Risk Level", ["Conservative", "Balanced", "Aggressive"], index=1)
        run = b4.button("Run Backtest")

        if run:
            with st.spinner("Running historical strategy simulation..."):
                st.session_state["last_backtest"] = run_backtest(
                    ticker,
                    initial_capital=capital,
                    holding_days=holding_days,
                    risk_level=risk_level
                )
                st.session_state["last_backtest_compare"] = compare_strategies(ticker, capital)

        bt = st.session_state.get("last_backtest")
        if bt:
            if bt.get("status") == "no_data":
                st.error(bt.get("message", "Backtest could not be completed."))
            elif bt.get("status") == "no_trades":
                st.warning(bt.get("message", "No trades were generated for these settings."))
            else:
                st.success(bt.get("message", "Backtest completed."))

            summary = bt["summary"]
            s1, s2, s3, s4, s5, s6 = st.columns(6)
            s1.metric("Trades", summary["total_trades"])
            s2.metric("Win Rate", f"{summary['win_rate']}%")
            s3.metric("ROI", f"{summary['roi']}%")
            s4.metric("Drawdown", f"{summary['max_drawdown']}%")
            s5.metric("Sharpe", summary["sharpe"])
            s6.metric("Profit Factor", summary["profit_factor"])
            equity_curve_chart(bt["equity_curve"])

            if bt["trades"]:
                st.write("### Trades")
                st.dataframe(bt["trades"], use_container_width=True, hide_index=True)
            else:
                st.info("No trade rows to display. Adjust risk level or holding period to test a broader setup.")

            st.write("### Strategy Comparison")
            comparison = st.session_state.get("last_backtest_compare")
            if comparison is not None and not comparison.empty:
                st.dataframe(comparison, use_container_width=True, hide_index=True)
            else:
                st.info("Strategy comparison will appear after a successful run.")
        else:
            st.info("Choose your capital, holding period, and risk level, then run a backtest to see metrics, equity curve, and trades.")

    elif terminal_view == "News":
        section_help("News", "Fetches recent sentiment-linked market news for the active ticker. This view is lazy to avoid extra calls during normal tab switching.")
        news = cached_news(ticker)
        sentiment = aggregate_news_sentiment(news)
        st.metric("Market Sentiment", f"{sentiment['label']} ({sentiment['score']})")
        if news:
            for item in news:
                st.write(f"- {item['title']} | {item.get('source', 'News')} | Sentiment: {item.get('sentiment', 0)}")
                if item.get("url"):
                    st.write(item["url"])
        else:
            st.info("No news found from Yahoo Finance. Set NEWSAPI_KEY for broader coverage.")


def render_portfolio():
    st.title("Portfolio Analyzer & Rebalancing")
    section_help("Portfolio Analyzer", "Upload CSV columns Ticker, Quantity, and Buy_Price. Quantara computes health, risk, sector allocation, weak holdings, replacement candidates, and index-relative performance.")
    file = st.file_uploader("Upload CSV with Ticker, Quantity, Buy_Price", type=["csv"])
    if file:
        try:
            df = pd.read_csv(file)
            analyze_uploaded_portfolio(df)
        except Exception as exc:
            compact_alert(
                "Portfolio analysis could not complete",
                "Check the file columns and retry after the market data provider cooldown if rate-limited.",
                level="error",
                details=exc,
            )


def render_basket():
    st.title("Smart Stock Basket")
    st.caption("Auto-scanning the listed universe for the strongest BUY opportunities.")
    section_help("Basket Scanner", "Uses a fast batched OHLCV pre-scan for thousands of symbols, then ranks technically qualified BUY setups. It avoids full per-stock fundamentals during the scan to keep the app responsive.")
    universe_rows = cached_market_universe()
    st.caption(f"Combined NSE+BSE stock universe: {len(universe_rows)} validated listings")

    selected_sectors = st.multiselect(
        "Sector Filter",
        SECTOR_OPTIONS + ["Other"],
        placeholder="Scan all sectors",
        help="Select one or more sectors to restrict the scan. Leave empty to scan the selected exchange universe.",
    )
    if selected_sectors:
        universe_rows = [row for row in universe_rows if row.get("sector", "Other") in selected_sectors or row.get("segment") in selected_sectors]

    search = st.text_input("Search / Filter Universe", placeholder="Type symbol text, e.g. BANK, TATA, RELIANCE")
    filtered_universe = [
        item for item in universe_rows
        if not search
        or search.upper() in item.get("ticker", "").upper()
        or search.upper() in item.get("symbol", "").upper()
        or search.upper() in item.get("name", "").upper()
        or search.upper() in item.get("display_name", "").upper()
    ]
    controls = st.columns([1, 1, 1, 1])
    capital = controls[0].number_input("Investment Amount", min_value=1000, value=10000, step=1000)
    max_positions = controls[1].slider("Max Positions", 2, 8, 4)
    risk_pct = controls[2].slider("Risk per Trade %", 0.5, 3.0, 1.5, 0.25)
    dynamic_scan_max = max(20, len(filtered_universe))
    scan_limit = controls[3].slider("Scan Limit", 20, dynamic_scan_max, min(60, dynamic_scan_max), 10)
    candidates = filtered_universe[:scan_limit]

    with st.expander(f"Universe preview ({len(filtered_universe)} symbols available)", expanded=False):
        st.dataframe(pd.DataFrame(filtered_universe[:500]), use_container_width=True, hide_index=True)

    sort_by = st.selectbox("Sort BUY opportunities by", ["confidence", "expected_return_pct", "risk_reward", "allocation"], index=0)
    rescan = st.button("Run / Refresh BUY Scan")

    scan_key = (
        int(capital),
        tuple(item.get("ticker") for item in candidates),
        tuple(selected_sectors),
        int(max_positions),
        float(risk_pct),
        int(scan_limit)
    )
    should_scan = rescan

    progress_slot = st.empty()
    metrics_slot = st.empty()
    cards_slot = st.empty()
    table_slot = st.empty()
    notes_slot = st.empty()

    def render_basket_result(basket, is_partial=False):
        positions = sorted(basket["positions"], key=lambda item: item.get(sort_by, 0), reverse=True)
        with metrics_slot.container():
            b1, b2, b3, b4 = st.columns(4)
            b1.metric("BUY Score", f"{basket['basket_score']}%")
            b2.metric("Used Capital", f"Rs. {basket['used_capital']:.2f}")
            b3.metric("Cash Remaining", f"Rs. {basket['cash_remaining']:.2f}")
            b4.metric("Qualified BUYs", basket["qualified"])
            if basket.get("elapsed") is not None:
                st.caption(f"Scanned {basket['scanned']}/{basket.get('universe_size', basket['scanned'])} in {basket['elapsed']}s")
        with cards_slot.container():
            basket_cards(positions)
        with table_slot.container():
            if positions:
                with st.expander("Detailed allocation table", expanded=False):
                    st.dataframe(positions, use_container_width=True, hide_index=True)
            elif not is_partial:
                compact_alert("No BUY setups found", "Increase scan limit, choose fewer sector filters, or retry later if data was throttled.", level="info")
        if not is_partial:
            with notes_slot.container():
                if basket.get("errors"):
                    compact_alert("Some symbols were skipped", "A few symbols had no data or were rate-limited. The scan continued with the rest of the universe.", level="warn", details="\n".join(basket["errors"]))
                insight_card("Basket Notes", basket["notes"])

    if should_scan and candidates:
        st.session_state["basket_scan_key"] = scan_key
        with progress_slot.container():
            scan_skeleton(f"Auto-scanning {len(candidates)} symbols for BUY setups...")
        progress_bar = st.progress(0, text="Starting scan...")

        def on_progress(partial_basket, completed, total):
            progress_bar.progress(completed / total, text=f"Scanned {completed}/{total} symbols")
            if partial_basket["positions"]:
                render_basket_result(partial_basket, is_partial=True)

        basket = build_stock_basket(
            capital,
            candidates,
            max_positions,
            risk_pct,
            scan_limit,
            progress_callback=on_progress,
            max_workers=4,
            chunk_size=80,
        )
        progress_bar.empty()
        progress_slot.empty()
        st.session_state["last_basket"] = basket
    else:
        basket = st.session_state.get("last_basket")

    if basket:
        render_basket_result(basket)
    else:
        compact_alert("Ready to scan", "Choose your universe, optional sector filters, and click Run / Refresh BUY Scan. Scans no longer run automatically on every tab switch.", level="info")


def _score_comparison(result):
    technical = max(0, min(100, (result["trade_confidence"] * 0.45) + (result["risk_reward"] * 12) + (result["expected_return_pct"] * 2)))
    fundamental = result["fundamentals"].get("score", 0)
    risk = max(0, min(100, 100 - (result["risk_pct"] * 8) - (result["atr_pct"] * 5)))
    momentum = 75 if result["trend"] == "Uptrend" else 35 if result["trend"] == "Downtrend" else 55
    ai_score = round((technical * 0.45) + (fundamental * 0.35) + (risk * 0.2), 2)
    return {
        "AI score": ai_score,
        "Fundamental score": round(fundamental, 2),
        "Technical score": round(technical, 2),
        "Momentum": momentum,
        "Risk quality": round(risk, 2),
        "Volatility quality": round(max(0, 100 - result["atr_pct"] * 8), 2),
    }


def _benchmark_return(symbol):
    hist = cached_history(symbol, "1y")
    close = hist["Close"].dropna() if not hist.empty else pd.Series(dtype=float)
    if len(close) < 2:
        return None
    return ((float(close.iloc[-1]) / float(close.iloc[0])) - 1) * 100


def _comparison_row(symbol, result, nifty_return, sensex_return):
    scores = _score_comparison(result)
    history = result["history"]["Close"].dropna()
    returns = ((float(history.iloc[-1]) / float(history.iloc[0])) - 1) * 100 if len(history) > 1 else 0
    metrics = result["fundamentals"]["metrics"]
    ma20 = float(history.rolling(20).mean().iloc[-1]) if len(history) >= 20 else None
    ma50 = float(history.rolling(50).mean().iloc[-1]) if len(history) >= 50 else None
    trend_strength = round(abs(float(history.iloc[-1]) - (ma50 or float(history.iloc[-1]))) / float(history.iloc[-1]) * 100, 2) if len(history) else 0
    volume_strength = round(result["volume_ratio"] * 50, 2)
    breakout_probability = max(0, min(100, result["trade_confidence"] + (10 if result["breakout"] == "Bullish breakout" else -10 if result["breakout"] == "Bearish breakdown" else 0)))
    risk_score = max(0, min(100, 100 - result["risk_pct"] * 8 - result["atr_pct"] * 4))
    suitability = round((scores["AI score"] * 0.5) + (scores["Technical score"] * 0.25) + (risk_score * 0.25), 2)
    return {
        "Ticker": symbol,
        "Decision": result["decision"],
        "Revenue Growth": metrics.get("revenue_growth", "N/A"),
        "Profit Growth": metrics.get("net_profit_growth", "N/A"),
        "ROE": metrics.get("roe", "N/A"),
        "ROCE": metrics.get("roce", "N/A"),
        "Debt to Equity": metrics.get("debt_to_equity", "N/A"),
        "Operating Margin": metrics.get("operating_margin", "N/A"),
        "EPS Growth": metrics.get("eps_growth", "N/A"),
        "PE Ratio": metrics.get("pe_ratio", "N/A"),
        "PB Ratio": metrics.get("pb_ratio", "N/A"),
        "Promoter Holding": metrics.get("promoter_holding", "N/A"),
        "Institutional Holding": metrics.get("institutional_holding", "N/A"),
        "RSI": round(result["rsi"], 2),
        "MACD": round(result["macd"], 2),
        "MA20": round(ma20, 2) if ma20 else "N/A",
        "MA50": round(ma50, 2) if ma50 else "N/A",
        "Trend Strength": trend_strength,
        "Momentum Score": scores["Momentum"],
        "Volume Strength": volume_strength,
        "Breakout Probability": breakout_probability,
        "Volatility": round(result["atr_pct"], 2),
        "Relative Strength": round(returns - (nifty_return or 0), 2),
        "AI Score": scores["AI score"],
        "Risk Score": round(risk_score, 2),
        "Confidence Score": result["trade_confidence"],
        "Swing Suitability": suitability,
        "Suggested Holding": result["holding_period"],
        "Risk/Reward Quality": round(result["risk_reward"], 2),
        "Performance vs NIFTY": round(returns - nifty_return, 2) if nifty_return is not None else "N/A",
        "Performance vs SENSEX": round(returns - sensex_return, 2) if sensex_return is not None else "N/A",
        "Relative Alpha": round(returns - max(nifty_return or 0, sensex_return or 0), 2),
        "Returns %": round(returns, 2),
        "Expected 30d %": round(result["expected_return_pct"], 2),
        **scores,
        "_history": history,
    }


def render_stock_comparison():
    st.title("Stock Comparison")
    st.caption("Compare multi-factor strength, risk, growth, momentum, and AI conviction side-by-side.")
    section_help("Stock Comparison", "Compares up to five symbols using cached full AI analysis. Click Compare manually so tab switches do not trigger repeated yfinance requests.")
    symbols_text = st.text_input("Symbols", value="RELIANCE.NS, TCS.NS, INFY.NS", help="Comma-separated tickers")
    symbols = [item.strip().upper() for item in symbols_text.split(",") if item.strip()]
    if not symbols:
        st.info("Add at least one ticker to compare.")
        return
    if len(symbols) > 5:
        compact_alert("Comparison capped at five symbols", "Large comparison sets are intentionally capped to avoid Yahoo rate limits. Narrow the set or run another batch.", level="warn")
        symbols = symbols[:5]
    compare = st.button("Compare Stocks")
    if not compare and "last_comparison" in st.session_state:
        results = st.session_state["last_comparison"]
    elif not compare:
        compact_alert("Ready to compare", "Click Compare Stocks to fetch cached full AI metrics and render the radar/performance charts.", level="info")
        return
    else:
        results = []
        nifty_return = _benchmark_return("^NSEI")
        sensex_return = _benchmark_return("^BSESN")
        with st.spinner("Building comparative intelligence..."):
            for symbol in symbols:
                try:
                    result = cached_stock_analysis(symbol)
                    results.append(_comparison_row(symbol, result, nifty_return, sensex_return))
                except Exception as exc:
                    compact_alert(f"{symbol} skipped", "Market data was unavailable or rate-limited for this symbol.", level="warn", details=exc)
        st.session_state["last_comparison"] = results

    if not results:
        compact_alert("No comparison data", "All requested symbols failed or were rate-limited. Try fewer symbols or wait for the provider cooldown.", level="error")
        return

    table = pd.DataFrame([{k: v for k, v in row.items() if not k.startswith("_")} for row in results])
    view = st.radio("Comparison View", ["Summary", "Fundamentals", "Technicals", "AI Analytics", "Market Comparison"], horizontal=True, label_visibility="collapsed")
    view_columns = {
        "Summary": ["Ticker", "Decision", "AI Score", "Confidence Score", "Risk Score", "Swing Suitability", "Returns %", "Expected 30d %"],
        "Fundamentals": ["Ticker", "Revenue Growth", "Profit Growth", "ROE", "ROCE", "Debt to Equity", "Operating Margin", "EPS Growth", "PE Ratio", "PB Ratio", "Promoter Holding", "Institutional Holding"],
        "Technicals": ["Ticker", "RSI", "MACD", "MA20", "MA50", "Trend Strength", "Momentum Score", "Volume Strength", "Breakout Probability", "Volatility", "Relative Strength"],
        "AI Analytics": ["Ticker", "AI Score", "Risk Score", "Confidence Score", "Swing Suitability", "Suggested Holding", "Risk/Reward Quality"],
        "Market Comparison": ["Ticker", "Performance vs NIFTY", "Performance vs SENSEX", "Relative Alpha", "Returns %"],
    }
    st.dataframe(table[[col for col in view_columns[view] if col in table.columns]], use_container_width=True, hide_index=True)

    radar_metrics = ["AI score", "Fundamental score", "Technical score", "Momentum", "Risk quality", "Volatility quality"]
    radar = go.Figure()
    for row in results:
        values = [row[metric] for metric in radar_metrics]
        radar.add_trace(go.Scatterpolar(r=values + [values[0]], theta=radar_metrics + [radar_metrics[0]], fill="toself", name=row["Ticker"]))
    radar.update_polars(bgcolor="rgba(8,24,43,.78)", radialaxis=dict(range=[0, 100], gridcolor="rgba(130,177,206,.18)"))
    apply_chart_theme(radar, height=460, title="Factor Radar")
    st.plotly_chart(radar, use_container_width=True)

    perf = go.Figure()
    palette = [CYAN, GREEN, BLUE, YELLOW, RED]
    for idx, row in enumerate(results):
        hist = row["_history"]
        if len(hist) > 1:
            indexed = (hist / hist.iloc[0]) * 100
            perf.add_trace(go.Scatter(x=indexed.index, y=indexed.values, mode="lines", name=row["Ticker"], line=dict(color=palette[idx % len(palette)], width=3)))
    apply_chart_theme(perf, height=430, title="Relative Performance Indexed to 100")
    st.plotly_chart(perf, use_container_width=True)


mode = render_sidebar_tools()

if mode == "Stock Terminal":
    render_stock_terminal()
elif mode == "Portfolio":
    render_portfolio()
elif mode == "Stock Basket":
    render_basket()
else:
    render_stock_comparison()

footer()
