import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from engines.data_service import get_price_history
from engines.formatting import format_currency
from engines.portfolio_engine import analyze_portfolio
from ui_components import BLUE, CYAN, GREEN, YELLOW, apply_chart_theme, compact_alert, health_meter


BENCHMARKS = {
    "NIFTY 50": "^NSEI",
    "SENSEX": "^BSESN",
    "NIFTY BANK": "^NSEBANK",
}

TICKER_COLUMNS = {
    "stock", "stock_name", "stockname", "company", "company_name", "companyname",
    "symbol", "ticker", "stock_nameticker", "name", "scrip", "security", "security_name", "instrument",
}
QUANTITY_COLUMNS = {"quantity", "qty", "shares", "units", "holding", "holdings", "no_of_shares", "noofshares"}
PRICE_COLUMNS = {"buy_price", "buyprice", "buy", "price", "avg_price", "average_price", "avg_cost", "average_cost", "cost", "cost_price"}


def _normalize_column(col):
    return "".join(ch for ch in str(col).strip().lower().replace(" ", "_") if ch.isalnum() or ch == "_")


def _numeric_density(series):
    if series is None:
        return 0
    return pd.to_numeric(series, errors="coerce").notna().mean()


def _prepare_portfolio_frame(df):
    if df is None or df.empty:
        return pd.DataFrame(), ["Uploaded file is empty."]

    original = df.copy()
    normalized_columns = {_normalize_column(col): col for col in original.columns}
    rename_map = {}
    for normalized, original_col in normalized_columns.items():
        compact = normalized.replace("_", "")
        if normalized in TICKER_COLUMNS or compact in TICKER_COLUMNS:
            rename_map[original_col] = "Ticker"
        elif normalized in QUANTITY_COLUMNS or compact in QUANTITY_COLUMNS:
            rename_map[original_col] = "Quantity"
        elif normalized in PRICE_COLUMNS or compact in PRICE_COLUMNS:
            rename_map[original_col] = "Buy_Price"

    prepared = original.rename(columns=rename_map)
    missing = {"Ticker", "Quantity", "Buy_Price"} - set(prepared.columns)

    if missing and len(prepared.columns) >= 3:
        candidates = list(prepared.columns[:8])
        text_cols = sorted(candidates, key=lambda col: _numeric_density(prepared[col]))
        numeric_cols = sorted(candidates, key=lambda col: _numeric_density(prepared[col]), reverse=True)
        inferred = {}
        if "Ticker" in missing and text_cols:
            inferred[text_cols[0]] = "Ticker"
        numeric_unused = [col for col in numeric_cols if col not in inferred]
        if "Quantity" in missing and numeric_unused:
            qty_col = min(numeric_unused, key=lambda col: pd.to_numeric(prepared[col], errors="coerce").median(skipna=True) if pd.to_numeric(prepared[col], errors="coerce").notna().any() else float("inf"))
            inferred[qty_col] = "Quantity"
            numeric_unused = [col for col in numeric_unused if col != qty_col]
        if "Buy_Price" in missing and numeric_unused:
            inferred[numeric_unused[0]] = "Buy_Price"
        prepared = prepared.rename(columns=inferred)

    missing = {"Ticker", "Quantity", "Buy_Price"} - set(prepared.columns)
    if missing:
        return pd.DataFrame(), [f"Missing required columns after normalization: {', '.join(sorted(missing))}."]

    prepared = prepared[["Ticker", "Quantity", "Buy_Price"]].copy()
    prepared["Ticker"] = prepared["Ticker"].astype(str).str.strip()
    prepared["Quantity"] = pd.to_numeric(prepared["Quantity"], errors="coerce")
    prepared["Buy_Price"] = pd.to_numeric(prepared["Buy_Price"], errors="coerce")

    errors = []
    invalid = prepared[
        (prepared["Ticker"] == "")
        | prepared["Ticker"].str.lower().isin({"nan", "none", "null"})
        | prepared["Quantity"].isna()
        | prepared["Buy_Price"].isna()
        | (prepared["Quantity"] <= 0)
        | (prepared["Buy_Price"] < 0)
    ]
    if not invalid.empty:
        errors.append(f"Skipped {len(invalid)} invalid row(s) with missing stock, quantity, or buy price.")

    prepared = prepared.dropna(subset=["Ticker", "Quantity", "Buy_Price"])
    prepared = prepared[
        (prepared["Ticker"] != "")
        & ~prepared["Ticker"].str.lower().isin({"nan", "none", "null"})
        & (prepared["Quantity"] > 0)
        & (prepared["Buy_Price"] >= 0)
    ]
    return prepared, errors


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
    df, parse_errors = _prepare_portfolio_frame(df)
    if df.empty:
        compact_alert(
            "Invalid portfolio file",
            "Expected stock name/ticker, quantity, and buy price. Quantara could not infer those fields from this file.",
            level="error",
            details="\n".join(parse_errors),
        )
        return None

    if parse_errors:
        compact_alert("Portfolio file cleaned", "Quantara skipped invalid rows and continued with the valid holdings.", level="warn", details="\n".join(parse_errors))

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
    c1.metric("Current Value", format_currency(output["total_value"], ticker="NIFTY.NS"))
    c2.metric("Projected 30d", format_currency(output["future_value"], ticker="NIFTY.NS"))
    c3.metric("Portfolio Health", f"{output['portfolio_score']:.0f}%")
    c4.metric("Aggregate Risk", f"{output['aggregate_risk']:.2f}%")
    health_meter(output["portfolio_score"])

    if output["sector_allocation"]:
        st.write("### Sector Allocation")
        st.dataframe(
            [{"Sector": sector, "Allocation %": pct} for sector, pct in output["sector_allocation"].items()],
            use_container_width=True
        )
        from ui_components import csv_download
        csv_download([{"Sector": sector, "Allocation %": pct} for sector, pct in output["sector_allocation"].items()], "quantara_portfolio_sector_allocation.csv", key="portfolio_sector_csv")

    if output["rebalance_suggestions"]:
        st.write("### Rebalancing Suggestions")
        st.dataframe(output["rebalance_suggestions"], use_container_width=True, hide_index=True)
        from ui_components import csv_download
        csv_download(output["rebalance_suggestions"], "quantara_portfolio_rebalancing.csv", key="portfolio_rebalance_csv")

    if output.get("replacement_suggestions"):
        st.write("### Intelligent Replacement Ideas")
        st.dataframe(output["replacement_suggestions"], use_container_width=True, hide_index=True)
        from ui_components import csv_download
        csv_download(output["replacement_suggestions"], "quantara_portfolio_replacements.csv", key="portfolio_replacements_csv")

    if output.get("errors"):
        compact_alert("Some holdings were skipped", "A few portfolio symbols could not be analyzed, but the rest of the report was generated.", level="warn", details="\n".join(output["errors"]))

    # Benchmark comparison removed for performance optimization

    st.write("### Holdings")
    rows = []
    for item in output["holdings"]:
        rows.append({
            "Stock": item.get("display_name", item["ticker"]),
            "Sector": item["sector"],
            "Decision": item.get("portfolio_action", "HOLD"),
            "Quantara Score": item.get("quantara_score", item.get("ai_score")),
            "Risk": item["risk_level"],
            "Quantity": item["quantity"],
            "Buy Price": round(item["buy_price"], 2),
            "Current Price": round(item["price"], 2),
            "Current Value": round(item["current_value"], 2),
            "Allocation %": item.get("allocation_pct", 0),
            "P&L %": round(item["pnl_pct"], 2),
            "Expected 30d %": round(item["expected_return_pct"], 2),
            "Risk-Reward": round(item["risk_reward"], 2)
        })
    st.dataframe(rows, use_container_width=True)
    from ui_components import csv_download
    csv_download(rows, "quantara_portfolio_holdings.csv", key="portfolio_holdings_csv")

    return output
