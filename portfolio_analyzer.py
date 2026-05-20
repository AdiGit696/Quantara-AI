import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from engines.data_service import get_price_history
from engines.portfolio_engine import analyze_portfolio
from ui_components import BLUE, CYAN, GREEN, YELLOW, apply_chart_theme, compact_alert, health_meter


BENCHMARKS = {
    "NIFTY 50": "^NSEI",
    "SENSEX": "^BSESN",
    "NIFTY BANK": "^NSEBANK",
}


def _portfolio_growth_curve(holdings):
    curves = []
    weights = []
    for item in holdings:
        history = item.get("history")
        if history is None or history.empty:
            continue
        close = history["Close"].dropna()
        if len(close) < 2:
            continue
        indexed = close / close.iloc[0]
        curves.append(indexed.rename(item["ticker"]))
        weights.append(item["current_value"])

    if not curves or not weights:
        return pd.Series(dtype=float)

    frame = pd.concat(curves, axis=1).ffill().dropna(how="all")
    normalized_weights = pd.Series(weights, index=frame.columns)
    normalized_weights = normalized_weights / normalized_weights.sum()
    return (frame * normalized_weights).sum(axis=1) * 100


def _benchmark_curves(portfolio_curve):
    curves = {}
    if portfolio_curve.empty:
        return curves

    for label, symbol in BENCHMARKS.items():
        hist = get_price_history(symbol, period="1y")
        if hist.empty:
            continue
        close = hist["Close"].dropna()
        aligned = close[close.index >= portfolio_curve.index.min()]
        if len(aligned) < 2:
            continue
        curves[label] = (aligned / aligned.iloc[0]) * 100
    return curves


def _render_benchmark_analysis(output):
    portfolio_curve = _portfolio_growth_curve(output["holdings"])
    benchmark_curves = _benchmark_curves(portfolio_curve)
    if portfolio_curve.empty or not benchmark_curves:
        st.info("Benchmark comparison needs enough historical data across holdings and indices.")
        return

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=portfolio_curve.index, y=portfolio_curve.values, mode="lines", name="Portfolio", line=dict(color=GREEN, width=4)))
    palette = [CYAN, BLUE, YELLOW]
    rows = []
    portfolio_return = ((portfolio_curve.iloc[-1] / portfolio_curve.iloc[0]) - 1) * 100
    portfolio_drawdown = ((portfolio_curve / portfolio_curve.cummax()) - 1).min() * 100

    for index, (label, curve) in enumerate(benchmark_curves.items()):
        aligned_portfolio = portfolio_curve.reindex(curve.index, method="nearest").dropna()
        benchmark_return = ((curve.iloc[-1] / curve.iloc[0]) - 1) * 100
        benchmark_drawdown = ((curve / curve.cummax()) - 1).min() * 100
        alpha = portfolio_return - benchmark_return
        rows.append({
            "Benchmark": label,
            "Portfolio Return %": round(portfolio_return, 2),
            "Benchmark Return %": round(benchmark_return, 2),
            "Alpha %": round(alpha, 2),
            "Portfolio Drawdown %": round(portfolio_drawdown, 2),
            "Benchmark Drawdown %": round(benchmark_drawdown, 2),
            "Risk-adjusted Edge": round(alpha / max(abs(portfolio_drawdown), 1), 2),
        })
        fig.add_trace(go.Scatter(x=curve.index, y=curve.values, mode="lines", name=label, line=dict(color=palette[index % len(palette)], width=2)))

    apply_chart_theme(fig, height=430, title="Portfolio vs Benchmark Growth")
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(rows, use_container_width=True, hide_index=True)


def analyze_uploaded_portfolio(df):
    required = {"Ticker", "Quantity", "Buy_Price"}
    missing = required - set(df.columns)
    if missing:
        compact_alert(
            "Invalid portfolio file",
            f"Missing required columns: {', '.join(sorted(missing))}. Expected Ticker, Quantity, Buy_Price.",
            level="error",
        )
        return None

    df = df.copy()
    df["Ticker"] = df["Ticker"].astype(str).str.upper().str.strip()
    df["Quantity"] = pd.to_numeric(df["Quantity"], errors="coerce")
    df["Buy_Price"] = pd.to_numeric(df["Buy_Price"], errors="coerce")
    df = df.dropna(subset=["Ticker", "Quantity", "Buy_Price"])
    df = df[(df["Ticker"] != "") & (df["Quantity"] > 0)]
    if df.empty:
        compact_alert("No valid holdings", "The uploaded file did not contain usable rows after validation.", level="error")
        return None

    generate_replacements = st.checkbox("Generate replacement ideas", value=False, help="Runs an additional fast batched scan. Keep off for the fastest portfolio load.")
    with st.spinner("Analyzing holdings in parallel..."):
        output = analyze_portfolio(df, generate_replacements=generate_replacements)
    if not output["holdings"]:
        compact_alert(
            "Portfolio data unavailable",
            "No holdings could be analyzed. This is usually caused by invalid tickers or a temporary market data rate limit.",
            level="error",
            details="\n".join(output.get("errors", [])),
        )
        return output

    st.subheader("Portfolio Intelligence")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Current Value", f"Rs. {output['total_value']:.2f}")
    c2.metric("Projected 30d", f"Rs. {output['future_value']:.2f}")
    c3.metric("Portfolio Health", f"{output['portfolio_score']:.0f}%")
    c4.metric("Aggregate Risk", f"{output['aggregate_risk']:.2f}%")
    health_meter(output["portfolio_score"])

    if output["sector_allocation"]:
        st.write("### Sector Allocation")
        st.dataframe(
            [{"Sector": sector, "Allocation %": pct} for sector, pct in output["sector_allocation"].items()],
            use_container_width=True
        )

    if output["rebalance_suggestions"]:
        st.write("### Rebalancing Suggestions")
        st.dataframe(output["rebalance_suggestions"], use_container_width=True, hide_index=True)

    if output.get("replacement_suggestions"):
        st.write("### Intelligent Replacement Ideas")
        st.dataframe(output["replacement_suggestions"], use_container_width=True, hide_index=True)

    if output.get("errors"):
        compact_alert("Some holdings were skipped", "A few portfolio symbols could not be analyzed, but the rest of the report was generated.", level="warn", details="\n".join(output["errors"]))

    st.write("### Benchmark Comparison")
    if st.checkbox("Render benchmark comparison chart", value=False, help="Lazy-loads NIFTY/SENSEX benchmark data. Keep off for fastest portfolio switching."):
        _render_benchmark_analysis(output)
    else:
        compact_alert("Benchmark chart ready", "Enable the benchmark chart when needed. It is lazy-loaded to keep portfolio analysis responsive.", level="info")

    st.write("### Holdings")
    rows = []
    for item in output["holdings"]:
        rows.append({
            "Ticker": item["ticker"],
            "Sector": item["sector"],
            "Decision": item["decision"],
            "Confidence": item["trade_confidence"],
            "Risk": item["risk_level"],
            "P&L %": round(item["pnl_pct"], 2),
            "Expected 30d %": round(item["expected_return_pct"], 2),
            "Risk-Reward": round(item["risk_reward"], 2)
        })
    st.dataframe(rows, use_container_width=True)

    return output
