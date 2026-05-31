import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import config
from engines.backtester import compare_strategies, run_backtest
from engines.basket_engine import build_investing_basket, build_stock_basket, prescreen_market_candidates
from engines.data_service import SECTOR_OPTIONS, get_market_universe, get_price_history, resolve_ticker, safe_info, search_universe
from engines.formatting import format_currency, format_metric_value
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
    csv_download,
    section_help,
    stock_header_card,
)


APP_NAME = "Quantara AI"
APP_DIR = Path(__file__).parent
STATE_DIR = APP_DIR / ".quantara"
STATE_DIR.mkdir(exist_ok=True)
NOTES_FILE = STATE_DIR / "notes.txt"
WATCHLIST_FILE = STATE_DIR / "watchlist.json"


st.set_page_config(page_title=APP_NAME, page_icon=str(APP_DIR / "assets" / "favicon.svg"), layout="wide")
try:
    st.set_option("client.showErrorDetails", False)
except Exception:
    pass
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


@st.cache_data(ttl=86400, show_spinner=False)
def cached_resolve_symbol(query):
    return resolve_ticker(query, cached_market_universe())


@st.cache_data(ttl=900, show_spinner=False)
def cached_price_history(ticker):
    return get_price_history(ticker, period="5d")


@st.cache_data(ttl=1800, show_spinner=False)
def cached_history(ticker, period="1y"):
    return get_price_history(ticker, period=period)


def _numeric_series(value):
    if value is None:
        return pd.Series(dtype=float)
    if isinstance(value, pd.DataFrame):
        if value.empty:
            return pd.Series(dtype=float)
        value = value.iloc[:, 0]
    series = pd.to_numeric(pd.Series(value).squeeze(), errors="coerce")
    if not isinstance(series, pd.Series):
        series = pd.Series([series])
    return series.dropna().astype(float)


def _close_series(history):
    if history is None or history.empty or "Close" not in history:
        return pd.Series(dtype=float)
    return _numeric_series(history["Close"])


def _clean_stock_label(value):
    return str(value or "").replace(".NS", "").replace(".BO", "")


def _public_universe_frame(rows, limit=500):
    public_rows = []
    for row in rows[:limit]:
        public_rows.append({
            "Company": row.get("display_name") or row.get("name") or _clean_stock_label(row.get("symbol") or row.get("ticker")),
            "Symbol": _clean_stock_label(row.get("symbol") or row.get("ticker")),
            "Sector": row.get("sector", "Other"),
            "Segment": row.get("segment", "Equity"),
        })
    return pd.DataFrame(public_rows)


def _render_backtest_summary(bt, comparison=None):
    summary = bt.get("summary", {})
    total_return = float(summary.get("total_return", summary.get("roi", 0)) or 0)
    cagr = float(summary.get("cagr", 0) or 0)
    win_rate = float(summary.get("win_rate", 0) or 0)
    drawdown = float(summary.get("max_drawdown", 0) or 0)
    sharpe = float(summary.get("sharpe", 0) or 0)
    profit_factor = float(summary.get("profit_factor", 0) or 0)
    confidence = float(summary.get("strategy_confidence", 0) or 0)

    if total_return > 0 and sharpe >= 0.8 and drawdown <= 18:
        interpretation = "Strategy quality is constructive: returns are positive and drawdown is controlled."
    elif total_return > 0:
        interpretation = "Strategy produced positive returns, but risk-adjusted quality needs monitoring."
    elif summary.get("total_trades", 0):
        interpretation = "Strategy generated trades but did not produce a positive net edge in this period."
    else:
        interpretation = "No trades qualified under the selected rules; this can be prudent during weak or noisy regimes."

    benchmark_note = "Benchmark comparison unavailable for this run."
    if comparison is not None and not comparison.empty and "total_return" in comparison.columns:
        try:
            best = comparison.sort_values("total_return", ascending=False).iloc[0]
            benchmark_note = f"Best tested risk profile was {best.get('strategy')} with {float(best.get('total_return', 0)):.2f}% total return."
        except Exception:
            pass

    strengths = []
    weaknesses = []
    if win_rate >= 52:
        strengths.append(f"Win rate is healthy at {win_rate:.1f}%.")
    else:
        weaknesses.append(f"Win rate is modest at {win_rate:.1f}%.")
    if drawdown <= 15:
        strengths.append(f"Drawdown stayed controlled at {drawdown:.1f}%.")
    else:
        weaknesses.append(f"Drawdown is elevated at {drawdown:.1f}%.")
    if profit_factor >= 1.2:
        strengths.append(f"Profit factor is acceptable at {profit_factor:.2f}.")
    else:
        weaknesses.append(f"Profit factor is weak at {profit_factor:.2f}.")

    insight_card("Backtesting Summary", [
        f"Total return {total_return:.2f}%, CAGR {cagr:.2f}%, win rate {win_rate:.2f}%, max drawdown {drawdown:.2f}%.",
        f"Risk-adjusted read: Sharpe {sharpe:.2f}, profit factor {profit_factor:.2f}, strategy confidence {confidence:.0f}/100.",
        interpretation,
        benchmark_note,
        "Strengths: " + (" ".join(strengths) if strengths else "No dominant strength yet."),
        "Weaknesses: " + (" ".join(weaknesses) if weaknesses else "No major weakness stood out in this run."),
    ])


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
    mode = st.sidebar.radio(
        "Workspace mode",
        ["Stock Terminal", "Portfolio", "Swing Basket", "Long Term Investing", "Stock Comparison"],
        label_visibility="collapsed",
    )

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
    new_symbol = st.sidebar.text_input("Add symbol", placeholder="E.g. HDFC Bank", key="watch_add")
    add_col, clear_col = st.sidebar.columns([1, 1])
    if add_col.button("Add", use_container_width=True) and new_symbol:
        symbol = cached_resolve_symbol(new_symbol)["ticker"]
        if symbol and symbol not in st.session_state["watchlist"]:
            st.session_state["watchlist"].append(symbol)
            write_watchlist(st.session_state["watchlist"])
    if clear_col.button("Clear", use_container_width=True):
        st.session_state["watchlist"] = []
        write_watchlist([])

    for symbol in st.session_state["watchlist"][:12]:
        display = _clean_stock_label(symbol)
        try:
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
            st.sidebar.caption(f"{display} | data unavailable")
        remove_key = f"remove_{symbol}"
        if st.sidebar.button("Remove", key=remove_key, use_container_width=True):
            st.session_state["watchlist"] = [item for item in st.session_state["watchlist"] if item != symbol]
            write_watchlist(st.session_state["watchlist"])
            st.rerun()
    return mode


def render_stock_terminal():
    st.title(APP_NAME)
    st.caption("Market decision intelligence for stocks, portfolios, baskets, backtests, and funds")

    universe = cached_market_universe()
    search_query = st.text_input(
        "Search stock",
        value=st.session_state.get("active_stock_query", "Tata Consultancy Services"),
        placeholder="Search company or ticker, e.g. Tata Motors, Reliance, Apple",
        key="stock_search_top",
    )
    matches = search_universe(search_query, universe, limit=8) if search_query else []
    if matches:
        labels = [row.get("display_name") or row.get("name") or row.get("symbol") for row in matches]
        selected_label = st.selectbox("Best matches", labels, label_visibility="collapsed")
        selected_row = matches[labels.index(selected_label)]
    else:
        selected_row = cached_resolve_symbol(search_query or "TCS")
    ticker = selected_row["ticker"]
    st.session_state["active_stock_query"] = selected_row.get("display_name") or search_query

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

    section_help("Stock Terminal", "Runs full AI analysis for one ticker: price structure, fundamentals, technicals, probability, risk plan, backtesting, and news sentiment. This is intentionally heavier than basket scanning.")
    result["metadata"] = {**result.get("metadata", {}), **selected_row, "ticker": ticker}

    def money(value, compact=False):
        return format_currency(value, ticker=ticker, exchange=result.get("exchange"), currency=result.get("currency"), compact=compact)

    stock_header_card(result["metadata"], result, money)

    quantara_score = result.get("quantara_score", result.get("ai_score", 0))
    k1, k2, k3, k4 = st.columns([1, 1, 1, 1])
    k1.metric("Price", money(result["price"]), f"{result.get('day_change_pct', 0):+.2f}%")
    k2.metric("Status", result["decision"])
    with k3:
        confidence_ring(quantara_score)
    k4.metric("Risk", result["risk_level"])
    decision_badge(result["decision"], quantara_score)

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
        c4.metric("Quantara Score", f"{quantara_score:.0f}/100")

        with st.expander("Score details", expanded=False):
            st.dataframe([{
                "Quantara Score": round(quantara_score, 2),
                "Technical": result.get("technical_score"),
                "Fundamentals": result.get("fundamental_score"),
                "Momentum": result.get("momentum_score"),
                "Risk": result.get("risk_score"),
                "Sentiment": result.get("sentiment_score"),
                "Signal Confidence": result.get("trade_confidence"),
                "Decision Quality": result.get("decision_score"),
                "Recommendation Gate": "Master score maps 80+ Strong Buy, 65-79 Buy, 50-64 Hold, below 50 Avoid, with ATR risk-reward protection.",
            }], use_container_width=True, hide_index=True)

        insight_card("AI Trade Summary", result["probability_reasons"])
        insight_card("Decision Logic", result["decision_reasons"])
        insight_card("User Trust Layer", result.get("trust_explanation", []))

    elif terminal_view == "Chart":
        section_help("Chart", "Professional Plotly chart with optional volume, moving averages, and RSI overlays.")
        chart_cols = st.columns([1, 1, 1, 1])
        chart_period = chart_cols[0].selectbox("Timeframe", ["6mo", "1y", "2y", "5y"], index=1)
        show_volume = chart_cols[1].checkbox("Volume", value=True)
        show_ma = chart_cols[2].checkbox("MA 20/50", value=True)
        show_rsi = chart_cols[3].checkbox("RSI", value=False)
        chart_history = cached_history(ticker, chart_period)
        if chart_history.empty:
            compact_alert("Chart data unavailable", "Cached chart data is unavailable right now. Please retry after the market data provider cools down.", level="info")
        else:
            candlestick_chart(
                chart_history,
                title=f"{result.get('company_name', 'Stock')} Price Structure",
                support=result["support"],
                resistance=result["resistance"],
                show_volume=show_volume,
                show_ma=show_ma,
                show_rsi=show_rsi,
            )

    elif terminal_view == "Fundamentals":
        section_help("Fundamentals", "Scores growth, margins, debt, valuation, cash flow, and data quality from available financial statements.")
        fundamentals = result["fundamentals"]
        f1, f2, f3 = st.columns(3)
        f1.metric("Fundamental Rating", fundamentals["rating"])
        f2.metric("Fundamental Score", f"{fundamentals['score']}%")
        f3.metric("Data Quality", fundamentals["data_quality"])

        metrics = fundamentals["metrics"]
        metric_rows = [{"Metric": key.replace("_", " ").title(), "Value": format_metric_value(key, value, ticker=ticker, exchange=result.get("exchange"), currency=result.get("currency"))} for key, value in metrics.items()]
        st.dataframe(metric_rows, use_container_width=True)
        csv_download(metric_rows, f"quantara_{ticker}_fundamentals.csv", key=f"{ticker}_fundamentals_csv")
        balance_sheet = fundamentals.get("balance_sheet_summary", {})
        if balance_sheet:
            with st.expander("Balance sheet summary", expanded=False):
                st.dataframe(
                    [{"Metric": key.replace("_", " ").title(), "Value": format_metric_value(key, value, ticker=ticker, exchange=result.get("exchange"), currency=result.get("currency"))} for key, value in balance_sheet.items()],
                    use_container_width=True,
                    hide_index=True,
                )
        fundamentals_chart(fundamentals["trend_data"])
        insight_card("Fundamental Explanation", fundamentals["insights"])

    elif terminal_view == "Technical & Patterns":
        section_help("Technical & Patterns", "Shows RSI, MACD, ATR, volume strength, support/resistance, breakout state, and detected price patterns.")
        insight_card("AI Technical Summary", result.get("technical_summary", []))
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
        csv_download([{
            "Support": round(result["support"], 2),
            "Resistance": round(result["resistance"], 2),
            "Zone": result["zone"],
            "Breakout": result["breakout"],
            "Structure": result["structure"],
            "Consolidation": result["consolidation"]
        }], f"quantara_{ticker}_price_structure.csv", key=f"{ticker}_structure_csv")

        st.write("### Detected Patterns")
        st.dataframe(result["patterns"], use_container_width=True)
        csv_download(result["patterns"], f"quantara_{ticker}_patterns.csv", key=f"{ticker}_patterns_csv")

    elif terminal_view == "Probability & Risk":
        section_help("Probability & Risk", "Combines forecast, trend, volume, structure, patterns, fundamentals, sentiment, ATR risk, stop loss, and target quality.")
        r1, r2, r3, r4 = st.columns(4)
        r1.metric("Entry", money(result["price"]))
        r2.metric("Stop Loss", money(result["stop_loss"]))
        r3.metric("Target", money(result["target"]))
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
            s3.metric("Total Return", f"{summary.get('total_return', summary['roi'])}%")
            s4.metric("Drawdown", f"{summary['max_drawdown']}%")
            s5.metric("Sharpe", summary["sharpe"])
            s6.metric("CAGR", f"{summary.get('cagr', 0)}%")
            x1, x2, x3 = st.columns(3)
            x1.metric("Profit Factor", summary["profit_factor"])
            x2.metric("Strategy Confidence", f"{summary.get('strategy_confidence', 0)}%")
            x3.metric("Ending Capital", money(summary.get("ending_capital", capital)))
            _render_backtest_summary(bt, st.session_state.get("last_backtest_compare"))
            equity_curve_chart(bt["equity_curve"])
            csv_download(bt["equity_curve"], f"quantara_{ticker}_equity_curve.csv", key=f"{ticker}_equity_csv")

            trade_extremes = []
            if summary.get("best_trade"):
                trade_extremes.append({"Label": "Best Trade", **summary["best_trade"]})
            if summary.get("worst_trade"):
                trade_extremes.append({"Label": "Worst Trade", **summary["worst_trade"]})
            if trade_extremes:
                st.write("### Best / Worst Trade")
                st.dataframe(trade_extremes, use_container_width=True, hide_index=True)
                csv_download(trade_extremes, f"quantara_{ticker}_best_worst_trades.csv", key=f"{ticker}_best_worst_csv")

            if bt["trades"]:
                st.write("### Trades")
                st.dataframe(bt["trades"], use_container_width=True, hide_index=True)
                csv_download(bt["trades"], f"quantara_{ticker}_backtest_trades.csv", key=f"{ticker}_trades_csv")
            else:
                st.info("No trade rows to display. Adjust risk level or holding period to test a broader setup.")

            monthly = bt.get("monthly_performance", [])
            if monthly:
                st.write("### Monthly Performance")
                st.dataframe(monthly, use_container_width=True, hide_index=True)
                csv_download(monthly, f"quantara_{ticker}_monthly_performance.csv", key=f"{ticker}_monthly_csv")

            st.write("### Strategy Comparison")
            comparison = st.session_state.get("last_backtest_compare")
            if comparison is not None and not comparison.empty:
                st.dataframe(comparison, use_container_width=True, hide_index=True)
                csv_download(comparison, f"quantara_{ticker}_strategy_comparison.csv", key=f"{ticker}_strategy_csv")
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
    section_help("Portfolio Analyzer", "Upload CSV with Stock Name or Ticker, Buy Price, and Quantity. Quantara resolves tickers, identifies the market, and computes health, risk, sector allocation, replacement candidates, and benchmark comparison.")
    file = st.file_uploader("Upload CSV with Stock Name/Ticker, Buy Price, Quantity", type=["csv"])
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
    st.title("Swing Basket")
    st.caption("Auto-scanning the listed universe for the strongest BUY opportunities.")
    section_help("Basket Scanner", "Uses a fast batched OHLCV pre-scan for thousands of symbols, then ranks technically qualified BUY setups. It avoids full per-stock fundamentals during the scan to keep the app responsive.")
    universe_rows = cached_market_universe()
    st.caption(f"Auto-resolved stock universe: {len(universe_rows)} validated listings")

    selected_sectors = st.multiselect(
        "Sector Filter",
        SECTOR_OPTIONS + ["Other"],
        placeholder="Scan all sectors",
        help="Select one or more sectors to restrict the scan. Leave empty to scan the full auto-resolved universe.",
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
    scan_limit = controls[3].slider(
        "Scan Limit",
        20,
        dynamic_scan_max,
        dynamic_scan_max,
        25
    )
    candidates = filtered_universe[:scan_limit]

    with st.expander(f"Universe preview ({len(filtered_universe)} symbols available)", expanded=False):
        st.dataframe(_public_universe_frame(filtered_universe), use_container_width=True, hide_index=True)

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
        table_rows = [{
            "Stock": item.get("display_name") or item.get("symbol"),
            "Current Price": item.get("current_price") or item.get("entry"),
            "Entry": item.get("entry"),
            "Target": item.get("target"),
            "Stop Loss": item.get("stop_loss"),
            "Confidence": item.get("confidence"),
            "Risk/Reward": item.get("risk_reward"),
            "Probability Model": item.get("probability_model", "Fast Momentum Risk Model"),
            "Quantara Score": item.get("quantara_score", item.get("ai_score")),
            "Risk": item.get("risk_level"),
            "Allocation": item.get("allocation"),
            "Quantity": item.get("qty"),
            "Sector": item.get("sector"),
        } for item in positions]
        with metrics_slot.container():
            b1, b2, b3, b4, b5 = st.columns(5)
            b1.metric("BUY Score", f"{basket['basket_score']}%")
            b2.metric("Used Capital", f"Rs. {basket['used_capital']:.2f}")
            b3.metric("Cash Remaining", f"Rs. {basket['cash_remaining']:.2f}")
            b4.metric("Accepted", basket["qualified"])
            b5.metric("Rejected", basket.get("rejected", max(0, basket.get("scanned", 0) - basket.get("qualified", 0))))
            if basket.get("elapsed") is not None:
                st.caption(f"Scanned {basket['scanned']}/{basket.get('universe_size', basket['scanned'])} in {basket['elapsed']}s")
        with cards_slot.container():
            basket_cards(positions)
        with table_slot.container():
            if positions and not is_partial:
                with st.expander("Detailed allocation table", expanded=False):
                    st.dataframe(table_rows, use_container_width=True, hide_index=True)
                    csv_download(table_rows, "quantara_swing_basket.csv", key="swing_basket_csv")
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
            progress_bar.progress(completed / total, text=f"Analyzed shortlist {completed}/{total}")
            if partial_basket["positions"]:
                render_basket_result(partial_basket, is_partial=True)

        def on_prescreen_progress(completed, total):
            progress_bar.progress(completed / max(total, 1), text=f"Prescreened {completed}/{total} symbols")

        shortlisted = prescreen_market_candidates(
            candidates,
            keep_ratio=config.PRESCREEN_PERCENT,
            period="6mo",
            chunk_size=config.SCAN_CHUNK,
            max_workers=config.BASKET_WORKERS,
            progress_callback=on_prescreen_progress,
        )

        basket = build_stock_basket(
            capital,
            shortlisted,
            max_positions,
            risk_pct,
            min(scan_limit, len(shortlisted)) if shortlisted else scan_limit,
            progress_callback=on_progress,
            max_workers=config.BASKET_WORKERS,
            chunk_size=config.SCAN_CHUNK,
            universe_size=len(candidates),
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


def render_investing_basket():
    if not config.ENABLE_LONGTERM_SCAN:
        compact_alert("Long-term scan disabled", "This module is currently disabled by feature flag while the platform keeps other workflows responsive.", level="info")
        return
    st.title("Long Term Investing")
    st.caption("Builds a research-first basket for 1 year, 3 year, and longer-term compounding workflows.")
    universe_rows = cached_market_universe()
    selected_sectors = st.multiselect("Sector Filter", SECTOR_OPTIONS + ["Other"], placeholder="All sectors", key="investing_sector")
    if selected_sectors:
        universe_rows = [row for row in universe_rows if row.get("sector", "Other") in selected_sectors]
    search = st.text_input("Search / Filter Universe", placeholder="Type company or sector text", key="investing_search")
    filtered = [
        row for row in universe_rows
        if not search or search.upper() in " ".join(str(row.get(k, "")) for k in ["ticker", "symbol", "name", "display_name", "sector"]).upper()
    ]
    controls = st.columns([1, 1, 1, 1])
    capital = controls[0].number_input("Investment Amount", min_value=5000, value=100000, step=5000, key="investing_capital")
    horizon = controls[1].selectbox("Horizon", ["1 Year", "3 Years", "Long Term"], index=1)
    max_positions = controls[2].slider("Max Holdings", 3, 12, 6)
    scan_limit = controls[3].slider(
        "Scan Limit",
        20,
        max(20, len(filtered)),
        max(20, len(filtered)),
        20,
        key="investing_scan_limit"
    )
    with st.expander(f"Universe preview ({len(filtered)} symbols available)", expanded=False):
        preview = _public_universe_frame(filtered)
        st.dataframe(preview, use_container_width=True, hide_index=True)
        csv_download(preview, "quantara_investing_universe_preview.csv", key="investing_universe_csv")
    if st.button("Build Investing Basket"):
        progress = st.progress(0, text="Starting long-term quality scan...")
        live_slot = st.empty()

        def on_investing_progress(partial_basket, completed, total):
            progress.progress(completed / max(total, 1), text=f"Analyzed {completed}/{total} candidates")
            live_positions = partial_basket.get("positions", [])
            if live_positions:
                with live_slot.container():
                    basket_cards(live_positions[:max_positions])

        with st.spinner("Ranking long-term candidates..."):
            filtered_candidates = prescreen_market_candidates(
                filtered[:scan_limit],
                keep_ratio=config.PRESCREEN_PERCENT,
                period="6mo",
                chunk_size=config.SCAN_CHUNK,
                max_workers=config.BASKET_WORKERS,
                progress_callback=lambda completed, total: progress.progress(
                    completed / max(total, 1),
                    text=f"Prescreened {completed}/{total} symbols",
                ),
            )

            st.session_state["last_investing_basket"] = build_investing_basket(
                capital,
                filtered_candidates,
                horizon=horizon,
                max_positions=max_positions,
                scan_limit=min(scan_limit, len(filtered_candidates)) if filtered_candidates else scan_limit,
                progress_callback=on_investing_progress,
                chunk_size=config.SCAN_CHUNK,
                universe_size=min(scan_limit, len(filtered)),
            )
        progress.empty()
    basket = st.session_state.get("last_investing_basket")
    if not basket:
        compact_alert("Ready to build", "Choose filters and click Build Investing Basket for a long-term shortlist.", level="info")
        return
    positions = basket.get("positions", [])
    b1, b2, b3, b4 = st.columns(4)
    b1.metric("Investing Score", f"{basket.get('basket_score', 0)}%")
    b2.metric("Used Capital", format_currency(basket.get("used_capital", 0), ticker="NIFTY.NS"))
    b3.metric("Cash Remaining", format_currency(basket.get("cash_remaining", 0), ticker="NIFTY.NS"))
    b4.metric("Candidates", len(positions))
    if positions:
        basket_cards(positions)
        rows = [{
            "Stock": item.get("display_name"),
            "Sector": item.get("sector"),
            "Current Price": item.get("current_price"),
            "1Y Outlook": item.get("one_year_outlook"),
            "3Y Outlook": item.get("three_year_outlook"),
            "5Y Potential": item.get("five_year_potential"),
            "Estimated CAGR": item.get("estimated_cagr"),
            "Long-Term Confidence": item.get("long_term_confidence"),
            "Quantara Score": item.get("quantara_score", item.get("ai_score")),
            "Risk": item.get("risk_profile"),
            "Risk Profile": item.get("risk_profile"),
            "Investment Thesis": item.get("investment_thesis"),
        } for item in positions]
        st.dataframe(rows, use_container_width=True, hide_index=True)
        csv_download(rows, "quantara_long_term_investing_basket.csv", key="investing_basket_csv")
        sector_rows = pd.DataFrame(rows).groupby("Sector").size().reset_index(name="Holdings").to_dict("records")
        st.write("### Sector Allocation")
        st.dataframe(sector_rows, use_container_width=True, hide_index=True)
        csv_download(sector_rows, "quantara_investing_sector_allocation.csv", key="investing_sector_alloc_csv")
    else:
        compact_alert("No long-term candidates", "Try a wider scan or fewer sector filters.", level="info")


def _score_comparison(result):
    technical = max(0, min(100, (result["trade_confidence"] * 0.45) + (result["risk_reward"] * 12) + (result["expected_return_pct"] * 2)))
    fundamental = result["fundamentals"].get("score", 0)
    risk = max(0, min(100, 100 - (result["risk_pct"] * 8) - (result["atr_pct"] * 5)))
    momentum = 75 if result["trend"] == "Uptrend" else 35 if result["trend"] == "Downtrend" else 55
    ai_score = round((technical * 0.45) + (fundamental * 0.35) + (risk * 0.2), 2)
    return {
        "Quantara score": result.get("quantara_score", ai_score),
        "Fundamental score": round(fundamental, 2),
        "Technical score": round(technical, 2),
        "Momentum": momentum,
        "Risk quality": round(risk, 2),
        "Volatility quality": round(max(0, 100 - result["atr_pct"] * 8), 2),
    }


def _benchmark_return(symbol):
    try:
        hist = cached_history(symbol, "1y")
        close = _close_series(hist)
        if len(close) < 2 or float(close.iloc[0]) == 0:
            return None
        return ((float(close.iloc[-1]) / float(close.iloc[0])) - 1) * 100
    except Exception:
        return None


def _comparison_row(symbol, result, nifty_return, sensex_return):
    scores = _score_comparison(result)
    history = _close_series(result.get("history"))
    returns = ((float(history.iloc[-1]) / float(history.iloc[0])) - 1) * 100 if len(history) > 1 and float(history.iloc[0]) else 0
    metrics = result["fundamentals"]["metrics"]
    ma20 = float(history.rolling(20).mean().iloc[-1]) if len(history) >= 20 and pd.notna(history.rolling(20).mean().iloc[-1]) else None
    ma50 = float(history.rolling(50).mean().iloc[-1]) if len(history) >= 50 and pd.notna(history.rolling(50).mean().iloc[-1]) else None
    trend_strength = round(abs(float(history.iloc[-1]) - (ma50 or float(history.iloc[-1]))) / float(history.iloc[-1]) * 100, 2) if len(history) else 0
    volume_strength = round(result["volume_ratio"] * 50, 2)
    breakout_probability = max(0, min(100, result["trade_confidence"] + (10 if result["breakout"] == "Bullish breakout" else -10 if result["breakout"] == "Bearish breakdown" else 0)))
    risk_score = max(0, min(100, 100 - result["risk_pct"] * 8 - result["atr_pct"] * 4))
    suitability = round((scores["Quantara score"] * 0.5) + (scores["Technical score"] * 0.25) + (risk_score * 0.25), 2)
    return {
        "Stock": result.get("company_name") or symbol.replace(".NS", "").replace(".BO", ""),
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
        "Quantara Score": scores["Quantara score"],
        "Risk": result.get("risk_level"),
        "Confidence Detail": result["trade_confidence"],
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
    symbols_text = st.text_input("Stocks", value="Reliance, TCS, Infosys", help="Comma-separated company names or tickers")
    resolved_symbols = [cached_resolve_symbol(item.strip()) for item in symbols_text.split(",") if item.strip()]
    symbols = [item["ticker"] for item in resolved_symbols]
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
        if nifty_return is None or sensex_return is None:
            compact_alert("Benchmark data temporarily unavailable", "Comparison will continue without benchmark alpha until index data is available.", level="info")
        with st.spinner("Building comparative intelligence..."):
            for symbol in symbols:
                try:
                    result = cached_stock_analysis(symbol)
                    results.append(_comparison_row(symbol, result, nifty_return, sensex_return))
                except Exception as exc:
                    friendly = next((item.get("display_name") or item.get("name") for item in resolved_symbols if item.get("ticker") == symbol), symbol.replace(".NS", "").replace(".BO", ""))
                    compact_alert(f"{friendly} skipped", "Market data was unavailable. Quantara kept the comparison running for the remaining stocks.", level="warn", details=exc)
        st.session_state["last_comparison"] = results

    if not results:
        compact_alert("No comparison data", "All requested symbols failed or were rate-limited. Try fewer symbols or wait for the provider cooldown.", level="error")
        return

    table = pd.DataFrame([{k: v for k, v in row.items() if not k.startswith("_")} for row in results])
    view = st.radio("Comparison View", ["Summary", "Fundamentals", "Technicals", "AI Analytics", "Market Comparison"], horizontal=True, label_visibility="collapsed")
    view_columns = {
        "Summary": ["Stock", "Decision", "Quantara Score", "Risk", "Swing Suitability", "Returns %", "Expected 30d %"],
        "Fundamentals": ["Stock", "Revenue Growth", "Profit Growth", "ROE", "ROCE", "Debt to Equity", "Operating Margin", "EPS Growth", "PE Ratio", "PB Ratio", "Promoter Holding", "Institutional Holding"],
        "Technicals": ["Stock", "RSI", "MACD", "MA20", "MA50", "Trend Strength", "Momentum Score", "Volume Strength", "Breakout Probability", "Volatility", "Relative Strength"],
        "AI Analytics": ["Stock", "Quantara Score", "Risk", "Confidence Detail", "Swing Suitability", "Suggested Holding", "Risk/Reward Quality"],
        "Market Comparison": ["Stock", "Performance vs NIFTY", "Performance vs SENSEX", "Relative Alpha", "Returns %"],
    }
    st.dataframe(table[[col for col in view_columns[view] if col in table.columns]], use_container_width=True, hide_index=True)
    csv_download(table[[col for col in view_columns[view] if col in table.columns]], f"quantara_stock_comparison_{view.lower().replace(' ', '_')}.csv", key=f"comparison_{view}_csv")

    radar_metrics = ["Quantara score", "Fundamental score", "Technical score", "Momentum", "Risk quality", "Volatility quality"]
    radar = go.Figure()
    try:
        for row in results:
            values = [float(row.get(metric, 0) or 0) for metric in radar_metrics]
            radar.add_trace(go.Scatterpolar(r=values + [values[0]], theta=radar_metrics + [radar_metrics[0]], fill="toself", name=row["Stock"]))
        radar.update_polars(bgcolor="rgba(8,24,43,.78)", radialaxis=dict(range=[0, 100], gridcolor="rgba(130,177,206,.18)"))
        apply_chart_theme(radar, height=460, title="Factor Radar")
        st.plotly_chart(radar, use_container_width=True, config={"displaylogo": False})
    except Exception as exc:
        compact_alert("Radar chart unavailable", "The comparison table is available, but the radar chart could not render for this batch.", level="info", details=exc)

    perf = go.Figure()
    palette = [CYAN, GREEN, BLUE, YELLOW, RED]
    for idx, row in enumerate(results):
        hist = row["_history"]
        if len(hist) > 1:
            indexed = (hist / hist.iloc[0]) * 100
            perf.add_trace(go.Scatter(x=indexed.index, y=indexed.values, mode="lines", name=row["Stock"], line=dict(color=palette[idx % len(palette)], width=3)))
    apply_chart_theme(perf, height=430, title="Relative Performance Indexed to 100")
    st.plotly_chart(perf, use_container_width=True, config={"displaylogo": False})


def _fund_metrics(symbol, benchmark_symbol="^NSEI"):
    hist = cached_history(symbol, "5y")
    close = hist["Close"].dropna() if not hist.empty else pd.Series(dtype=float)
    info = safe_info(symbol)
    if len(close) < 2:
        return None
    years = max((close.index[-1] - close.index[0]).days / 365.25, 0.1)
    total_return = ((float(close.iloc[-1]) / float(close.iloc[0])) - 1) * 100
    cagr = ((float(close.iloc[-1]) / float(close.iloc[0])) ** (1 / years) - 1) * 100
    rolling_1y = close.pct_change(252).dropna() * 100
    drawdown = ((close / close.cummax()) - 1).min() * 100
    volatility = close.pct_change().dropna().std() * (252 ** 0.5) * 100
    benchmark_return = _benchmark_return(benchmark_symbol)
    risk_score = max(0, min(100, 85 - abs(drawdown) * 1.2 - volatility * 0.7))
    return {
        "Fund": info.get("shortName") or symbol,
        "Symbol": symbol,
        "Category": info.get("category") or info.get("quoteType") or "Fund",
        "NAV / Price": round(float(close.iloc[-1]), 2),
        "Total Return %": round(total_return, 2),
        "CAGR %": round(cagr, 2),
        "Rolling 1Y Median %": round(float(rolling_1y.median()), 2) if not rolling_1y.empty else "N/A",
        "Best Rolling 1Y %": round(float(rolling_1y.max()), 2) if not rolling_1y.empty else "N/A",
        "Worst Rolling 1Y %": round(float(rolling_1y.min()), 2) if not rolling_1y.empty else "N/A",
        "Max Drawdown %": round(float(drawdown), 2),
        "Volatility %": round(float(volatility), 2),
        "Benchmark Alpha %": round(total_return - benchmark_return, 2) if benchmark_return is not None else "N/A",
        "Expense Ratio": info.get("annualReportExpenseRatio") or info.get("expenseRatio") or "N/A",
        "Risk Quality": round(risk_score, 2),
        "Quantara Fund Score": round(max(0, min(100, cagr * 2.2 + risk_score * 0.55)), 2),
        "_history": close,
    }


def render_mutual_funds():
    st.title("Mutual Funds")
    st.caption("Fund research, rolling-return quality, risk, SIP projection, and benchmark comparison.")
    symbols_text = st.text_input("Fund symbols", value="", placeholder="Enter fund names or provider symbols", help="Comma-separated fund identifiers")
    benchmark = st.selectbox("Benchmark", ["^NSEI", "^BSESN"], format_func=lambda item: "NIFTY 50" if item == "^NSEI" else "SENSEX")
    sip_cols = st.columns(3)
    sip_amount = sip_cols[0].number_input("Monthly SIP", min_value=500, value=10000, step=500)
    sip_years = sip_cols[1].number_input("Years", min_value=1, max_value=40, value=10)
    sip_return = sip_cols[2].number_input("Expected CAGR %", min_value=1.0, max_value=30.0, value=12.0, step=0.5)
    monthly_rate = (sip_return / 100) / 12
    months = int(sip_years * 12)
    sip_value = sip_amount * (((1 + monthly_rate) ** months - 1) / monthly_rate) * (1 + monthly_rate) if monthly_rate else sip_amount * months
    st.metric("Projected SIP Value", format_currency(sip_value, ticker="NIFTY.NS", compact=True))

    if not st.button("Analyze Funds"):
        compact_alert("Ready to analyze", "Add fund symbols and click Analyze Funds. CSV export appears with the analysis table.", level="info")
        return
    rows = []
    with st.spinner("Analyzing mutual fund history..."):
        for symbol in [item.strip().upper() for item in symbols_text.split(",") if item.strip()]:
            try:
                metrics = _fund_metrics(symbol, benchmark)
                if metrics:
                    rows.append(metrics)
            except Exception as exc:
                compact_alert(f"{symbol} skipped", "Fund data was unavailable from the provider.", level="warn", details=exc)
    if not rows:
        compact_alert("No fund data", "Try valid Yahoo Finance fund symbols or ETFs.", level="error")
        return
    table = pd.DataFrame([{k: v for k, v in row.items() if not k.startswith("_")} for row in rows])
    st.dataframe(table, use_container_width=True, hide_index=True)
    csv_download(table, "quantara_mutual_fund_analysis.csv", key="mutual_fund_csv")

    fig = go.Figure()
    for row in rows:
        hist = row["_history"]
        indexed = (hist / hist.iloc[0]) * 100
        fig.add_trace(go.Scatter(x=indexed.index, y=indexed.values, mode="lines", name=row["Symbol"]))
    apply_chart_theme(fig, height=430, title="Fund Growth Indexed to 100")
    st.plotly_chart(fig, use_container_width=True)


try:
    mode = render_sidebar_tools()

    if mode == "Stock Terminal":
        render_stock_terminal()
    elif mode == "Portfolio":
        render_portfolio()
    elif mode == "Swing Basket":
        render_basket()
    elif mode == "Long Term Investing":
        render_investing_basket()
    else:
        render_stock_comparison()
except Exception as exc:
    compact_alert(
        "This workspace could not finish loading",
        "Quantara recovered from an internal error. Please retry the action or switch to another workspace while cached data refreshes.",
        level="error",
        details=exc,
    )

footer()
