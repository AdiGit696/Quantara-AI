import html
from base64 import b64encode
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st


CHART_BG = "rgba(7, 18, 33, 0)"
GRID_COLOR = "rgba(130, 177, 206, 0.18)"
TEXT_COLOR = "#E7F8FF"
MUTED_COLOR = "#8FB1C7"
CYAN = "#62F5FF"
BLUE = "#1C8DFF"
GREEN = "#17E6A5"
RED = "#FF5E7A"
YELLOW = "#F8C75A"


def apply_chart_theme(fig, height=430, title=None):
    fig.update_layout(
        title=title,
        height=height,
        template="plotly_dark",
        paper_bgcolor=CHART_BG,
        plot_bgcolor="rgba(8, 24, 43, 0.78)",
        font=dict(color=TEXT_COLOR, family="Inter, Segoe UI, Arial"),
        title_font=dict(size=18, color=TEXT_COLOR),
        legend=dict(
            bgcolor="rgba(4, 15, 27, 0.35)",
            bordercolor="rgba(98,245,255,0.16)",
            borderwidth=1,
            font=dict(color=TEXT_COLOR),
        ),
        hoverlabel=dict(
            bgcolor="#06111F",
            bordercolor=CYAN,
            font_size=13,
            font_family="Inter, Segoe UI, Arial",
        ),
        margin=dict(l=12, r=12, t=46 if title else 28, b=12),
    )
    fig.update_xaxes(
        gridcolor=GRID_COLOR,
        zerolinecolor="rgba(130,177,206,0.22)",
        linecolor="rgba(130,177,206,0.28)",
        tickfont=dict(color=MUTED_COLOR),
    )
    fig.update_yaxes(
        gridcolor=GRID_COLOR,
        zerolinecolor="rgba(130,177,206,0.22)",
        linecolor="rgba(130,177,206,0.28)",
        tickfont=dict(color=MUTED_COLOR),
    )
    return fig


def inject_theme():
    st.markdown(
        """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
    :root {
        --if-bg: #050B14;
        --if-panel: rgba(10, 25, 44, .78);
        --if-panel-2: rgba(12, 33, 57, .72);
        --if-border: rgba(98, 245, 255, .16);
        --if-border-strong: rgba(98, 245, 255, .34);
        --if-text: #E7F8FF;
        --if-muted: #8FB1C7;
        --if-accent: #1C8DFF;
        --if-green: #17E6A5;
        --if-yellow: #F8C75A;
        --if-cyan: #62F5FF;
        --if-red: #FF5E7A;
    }
    .stApp {
        background:
            radial-gradient(circle at 18% -4%, rgba(28, 141, 255, .26), transparent 28%),
            radial-gradient(circle at 86% 2%, rgba(23, 230, 165, .16), transparent 32%),
            linear-gradient(145deg, #03070D 0%, #071525 45%, #0B1828 100%);
        color: var(--if-text);
        font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    .block-container { padding-top: 1.35rem; padding-bottom: 2.5rem; max-width: 1600px; }
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, rgba(5, 14, 26, .96), rgba(8, 24, 43, .98));
        border-right: 1px solid var(--if-border);
        box-shadow: 18px 0 40px rgba(0, 0, 0, .22);
    }
    section[data-testid="stSidebar"] * { color: var(--if-text) !important; }
    h1, h2, h3 { letter-spacing: 0; color: var(--if-text); }
    h1 { font-weight: 900; font-size: clamp(2rem, 3.2vw, 3.2rem); }
    h3 { color: #CFEFFF; }
    p, li, label, span, div, button { color: inherit; }
    div[data-testid="stMarkdownContainer"] p,
    div[data-testid="stCaptionContainer"],
    .stCaptionContainer,
    label,
    [data-testid="stWidgetLabel"] p {
        color: var(--if-text) !important;
    }
    [data-testid="stWidgetLabel"] { color: var(--if-text) !important; font-weight: 750; }
    div[data-testid="stTabs"] button {
        border-radius: 10px;
        padding: 8px 14px;
        color: var(--if-muted) !important;
        font-weight: 800;
        transition: color .18s ease, background .18s ease, box-shadow .18s ease, transform .18s ease;
    }
    div[data-testid="stTabs"] button p { color: var(--if-muted) !important; font-weight: 800; }
    div[data-testid="stTabs"] button:hover {
        background: rgba(98,245,255,.08);
        box-shadow: inset 0 0 0 1px rgba(98,245,255,.14);
        transform: translateY(-1px);
    }
    div[data-testid="stTabs"] button:hover p,
    div[data-testid="stTabs"] button[aria-selected="true"] p { color: var(--if-cyan) !important; }
    div[data-testid="stButton"] button {
        border-radius: 9px;
        border: 1px solid rgba(98,245,255,.28);
        background: linear-gradient(135deg, #0C6BEF, #12B7D8 55%, #17E6A5);
        color: #03101C;
        font-weight: 800;
        box-shadow: 0 14px 28px rgba(28,141,255,.18);
        transition: transform .18s ease, box-shadow .18s ease, filter .18s ease;
    }
    div[data-testid="stButton"] button * { color: #03101C !important; }
    div[data-testid="stButton"] button:hover {
        filter: saturate(1.08);
        box-shadow: 0 18px 34px rgba(98,245,255,.24);
        transform: translateY(-1px);
    }
    div[data-baseweb="input"], div[data-baseweb="select"], textarea, input, select {
        border-radius: 10px !important;
        background: rgba(4, 15, 27, .78) !important;
        color: var(--if-text) !important;
        caret-color: var(--if-cyan) !important;
        border-color: var(--if-border) !important;
    }
    div[data-baseweb="input"] input,
    div[data-baseweb="select"] div,
    textarea,
    input {
        color: var(--if-text) !important;
        -webkit-text-fill-color: var(--if-text) !important;
        opacity: 1 !important;
    }
    input::placeholder, textarea::placeholder {
        color: var(--if-muted) !important;
        -webkit-text-fill-color: var(--if-muted) !important;
        opacity: 1 !important;
    }
    div[role="radiogroup"] label,
    div[role="radiogroup"] p,
    div[role="radiogroup"] span,
    div[data-testid="stRadio"] label,
    div[data-testid="stRadio"] p,
    div[data-testid="stRadio"] span { color: var(--if-text) !important; font-weight: 650; }
    div[data-testid="stMetric"] {
        background: linear-gradient(180deg, rgba(12,30,51,.92), rgba(8,23,41,.82));
        border: 1px solid var(--if-border);
        padding: 20px;
        border-radius: 8px;
        box-shadow: 0 18px 42px rgba(0, 0, 0, .18);
        transition: transform .18s ease, border-color .18s ease, box-shadow .18s ease;
    }
    div[data-testid="stMetric"]:hover {
        transform: translateY(-2px);
        border-color: var(--if-border-strong);
        box-shadow: 0 20px 48px rgba(28,141,255,.12);
    }
    div[data-testid="stMetricLabel"] p { color: var(--if-muted) !important; font-weight: 850; }
    div[data-testid="stMetricValue"], div[data-testid="stMetricValue"] * { color: var(--if-text) !important; }
    .insight-card {
        background: linear-gradient(180deg, rgba(12,30,51,.9), rgba(8,23,41,.76));
        border: 1px solid var(--if-border);
        border-radius: 8px;
        padding: 18px 20px;
        margin: 14px 0;
        box-shadow: 0 18px 42px rgba(0, 0, 0, .16);
    }
    .insight-card b { color: var(--if-cyan); }
    .insight-card ul { margin-bottom: 0; padding-left: 1.2rem; color: var(--if-text); }
    .insight-card li { color: #C9E5F2 !important; }
    .tv-wrap {
        width: 100%;
        height: min(72vh, 760px);
        min-height: 560px;
        border: 1px solid var(--if-border);
        border-radius: 8px;
        overflow: hidden;
        background: var(--if-panel);
        box-shadow: 0 18px 42px rgba(0, 0, 0, .20);
    }
    .tv-wrap > div { height: 100%; width: 100%; }
    .confidence-ring {
        --value: 50;
        --ring: conic-gradient(var(--if-green) calc(var(--value) * 1%), rgba(143,177,199,.14) 0);
        width: 112px;
        height: 112px;
        border-radius: 50%;
        display: grid;
        place-items: center;
        background: var(--ring);
        position: relative;
        box-shadow: 0 14px 32px rgba(23,230,165,.18);
        transition: background .6s ease;
    }
    .confidence-ring::before {
        content: "";
        width: 82px;
        height: 82px;
        border-radius: 50%;
        background: #071525;
        position: absolute;
    }
    .confidence-ring span {
        position: relative;
        font-size: 1.55rem;
        font-weight: 900;
        color: var(--if-text);
    }
    .confidence-label { color: var(--if-muted); font-size: .82rem; font-weight: 700; text-align: center; margin-top: 8px; }
    .suggestion-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 14px; margin: 16px 0; }
    .stock-card {
        background:
            linear-gradient(180deg, rgba(12,30,51,.95), rgba(8,23,41,.82)),
            linear-gradient(135deg, rgba(28,141,255,.20), rgba(23,230,165,.13));
        border: 1px solid var(--if-border);
        border-radius: 8px;
        padding: 17px;
        box-shadow: 0 18px 42px rgba(0, 0, 0, .18);
        transition: transform .18s ease, box-shadow .18s ease, border-color .18s ease;
    }
    .stock-card:hover {
        transform: translateY(-3px);
        border-color: rgba(98,245,255,.34);
        box-shadow: 0 22px 48px rgba(28,141,255,.16);
    }
    .stock-card-head { display:flex; align-items:center; justify-content:space-between; gap:10px; margin-bottom:12px; }
    .stock-symbol { font-size:1.02rem; font-weight:900; color: var(--if-text) !important; line-height:1.28; }
    .pill { border-radius: 999px; padding: 4px 9px; font-size:.76rem; font-weight:800; border:1px solid transparent; }
    .pill-buy { color:#052016; background:linear-gradient(135deg, #62F5FF, #17E6A5); border-color:rgba(98,245,255,.42); }
    .stock-meta { display:grid; grid-template-columns: 1fr 1fr; gap: 12px; color:#C9E5F2; font-size:.92rem; }
    .stock-meta b { color:var(--if-muted); display:block; font-size:.72rem; text-transform:uppercase; }
    .reason { margin-top:13px; color:#ABCBDD; font-size:.88rem; line-height:1.55; }
    .allocation-bar { height: 8px; background: rgba(143,177,199,.12); border-radius:999px; overflow:hidden; margin-top:12px; border:1px solid rgba(98,245,255,.10); }
    .allocation-bar span { display:block; height:100%; background:linear-gradient(90deg, #1C8DFF, #17E6A5); border-radius:999px; }
    .card-details { margin-top: 12px; border-top:1px solid rgba(98,245,255,.10); padding-top: 10px; color:#C9E5F2; font-size:.82rem; }
    .compact-alert {
        border: 1px solid rgba(255,94,122,.25);
        background: rgba(255,94,122,.09);
        color: #FFD7DE;
        border-radius: 8px;
        padding: 12px 14px;
        margin: 12px 0;
        box-shadow: 0 16px 36px rgba(0,0,0,.14);
    }
    .compact-alert.warn {
        border-color: rgba(248,199,90,.28);
        background: rgba(248,199,90,.08);
        color: #FFE9B8;
    }
    .compact-alert.info {
        border-color: rgba(98,245,255,.20);
        background: rgba(98,245,255,.07);
        color: #D9FAFF;
    }
    .compact-alert b { color: inherit; }
    .help-row { display:flex; align-items:center; gap:8px; margin: 8px 0 12px; }
    .help-icon {
        display:inline-flex;
        align-items:center;
        justify-content:center;
        width:18px;
        height:18px;
        border-radius:50%;
        color:#03101C;
        background:linear-gradient(135deg, #62F5FF, #17E6A5);
        font-size:.72rem;
        font-weight:900;
        cursor:help;
    }
    .help-title { color: var(--if-cyan); font-weight:900; letter-spacing:.3px; }
    .prob-grid { display:grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; margin: 12px 0 16px; }
    .prob-tile { background:rgba(12,30,51,.82); border:1px solid rgba(98,245,255,.15); border-radius:8px; padding:14px 15px; }
    .prob-tile b { display:block; color:var(--if-muted); font-size:.72rem; text-transform:uppercase; margin-bottom:5px; }
    .prob-tile span { color:var(--if-text); font-size:1.1rem; font-weight:900; }
    .skeleton {
        min-height: 220px;
        border-radius: 8px;
        background: linear-gradient(90deg, rgba(12,30,51,.7) 25%, rgba(98,245,255,.12) 40%, rgba(12,30,51,.7) 60%);
        background-size: 240% 100%;
        animation: shimmer 1.4s infinite;
        border: 1px solid var(--if-border);
    }
    @keyframes shimmer { to { background-position: -240% 0; } }
    .scan-banner {
        background: linear-gradient(135deg, rgba(28,141,255,.16), rgba(23,230,165,.10));
        border: 1px solid var(--if-border);
        border-radius: 8px;
        padding: 16px 18px;
        margin: 14px 0;
        box-shadow: 0 18px 42px rgba(0, 0, 0, .14);
    }
    .scan-banner, .scan-banner * { color: var(--if-text) !important; }
    div[data-testid="stDataFrame"] { border: 1px solid var(--if-border); border-radius: 8px; overflow: hidden; box-shadow: 0 18px 42px rgba(0, 0, 0, .14); }
    div[data-testid="stDataFrame"] div[role="gridcell"],
    div[data-testid="stDataFrame"] div[role="columnheader"] {
        font-size: .9rem !important;
        line-height: 1.5 !important;
        padding-top: 8px !important;
        padding-bottom: 8px !important;
    }
    .brand-lockup { display:flex; align-items:center; gap:12px; margin: 4px 0 20px; }
    .brand-lockup img { width:42px; height:42px; }
    .brand-title { font-size:1.1rem; font-weight:900; color:var(--if-text); line-height:1; }
    .brand-subtitle { color:var(--if-muted); font-size:.68rem; letter-spacing:1.8px; margin-top:4px; }
    .q-section-title { color:var(--if-cyan); font-size:.76rem; font-weight:900; letter-spacing:1.6px; text-transform:uppercase; margin:18px 0 8px; }
    .watch-row { display:grid; grid-template-columns: 1.1fr .8fr .7fr; gap:8px; align-items:center; padding:9px 0; border-bottom:1px solid rgba(98,245,255,.08); font-size:.82rem; }
    .watch-row b { color:var(--if-text); }
    .watch-pos { color:var(--if-green) !important; font-weight:800; }
    .watch-neg { color:var(--if-red) !important; font-weight:800; }
    .watch-flat { color:var(--if-muted) !important; font-weight:800; }
    .status-badge { display:inline-flex; align-items:center; border-radius:999px; padding:5px 10px; font-weight:900; font-size:.78rem; border:1px solid transparent; }
    .status-bullish { color:#031D15; background:linear-gradient(135deg, #7CFFD1, #17E6A5); box-shadow:0 0 22px rgba(23,230,165,.22); }
    .status-strong { color:#031D15; background:linear-gradient(135deg, #D1FFE8, #17E6A5); box-shadow:0 0 30px rgba(23,230,165,.32); }
    .status-bearish { color:#FFE9EE; background:rgba(255,94,122,.13); border-color:rgba(255,94,122,.32); }
    .status-neutral { color:#C9E5F2; background:rgba(98,245,255,.08); border-color:rgba(98,245,255,.18); }
    .app-footer { margin-top: 26px; padding: 18px 0 4px; color: var(--if-muted); text-align:center; border-top:1px solid rgba(98,245,255,.12); font-size:.84rem; }
    .health-meter { height: 12px; border-radius:999px; background:rgba(143,177,199,.12); overflow:hidden; border:1px solid rgba(98,245,255,.14); }
    .health-meter span { display:block; height:100%; border-radius:999px; background:linear-gradient(90deg, #FF5E7A, #F8C75A 46%, #17E6A5); }
    @media (max-width: 900px) {
        .tv-wrap { min-height: 420px; height: 65vh; }
        .confidence-ring { width: 96px; height: 96px; }
        .confidence-ring::before { width: 70px; height: 70px; }
    }
    .buy, .avoid, .hold, .strongbuy {
        padding: 12px 14px;
        border-radius: 10px;
        font-weight: 800;
        border: 1px solid transparent;
    }
    .buy { background: rgba(23,230,165,.14); color: #7CFFD1; border-color: rgba(23,230,165,.34); box-shadow:0 0 24px rgba(23,230,165,.12); }
    .strongbuy { background: linear-gradient(135deg, rgba(98,245,255,.25), rgba(23,230,165,.20)); color: #B9FFE8; border-color: rgba(23,230,165,.48); box-shadow:0 0 34px rgba(23,230,165,.20); }
    .avoid { background: rgba(255,94,122,.13); color: #FFB4C0; border-color: rgba(255,94,122,.32); }
    .hold { background: rgba(98,245,255,.08); color: #BFEFFF; border-color: rgba(98,245,255,.22); }
    .buy *, .avoid *, .hold *, .strongbuy * { color: inherit !important; }
    </style>
    """,
        unsafe_allow_html=True,
    )


def brand_header():
    icon_path = Path(__file__).parent / "assets" / "quantara-icon.svg"
    encoded = b64encode(icon_path.read_bytes()).decode("ascii") if icon_path.exists() else ""
    st.sidebar.markdown(
        f"""
        <div class="brand-lockup">
            <img src="data:image/svg+xml;base64,{encoded}" alt="Quantara AI icon" />
            <div>
                <div class="brand-title">Quantara AI</div>
                <div class="brand-subtitle">QUANT INTELLIGENCE</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def footer():
    st.markdown(
        "<div class='app-footer'>Developed by Aditya Sharma | Ideation by Nidhi Kulkarni</div>",
        unsafe_allow_html=True,
    )


def html_block(markup):
    if hasattr(st, "html"):
        st.html(markup)
    else:
        st.markdown(markup, unsafe_allow_html=True)


def section_help(title, body):
    st.markdown(
        f"""
        <div class="help-row">
            <span class="help-title">{html.escape(title)}</span>
            <span class="help-icon" title="{html.escape(body)}">i</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def compact_alert(title, message, level="warn", details=None):
    css = "compact-alert info" if level == "info" else "compact-alert" if level == "error" else "compact-alert warn"
    st.markdown(
        f"<div class='{css}'><b>{html.escape(title)}</b><br>{html.escape(message)}</div>",
        unsafe_allow_html=True,
    )
    if details:
        with st.expander("View details", expanded=False):
            st.code(str(details))


def decision_badge(decision, confidence=None):
    css = "buy" if decision == "BUY" else "avoid" if decision == "AVOID" else "hold"
    if decision == "BUY" and confidence and confidence >= 75:
        css = "strongbuy"
    st.markdown(f"<div class='{css}'>{html.escape(str(decision))}</div>", unsafe_allow_html=True)


def status_badge(label, score=None):
    label_text = str(label or "Neutral")
    lower = label_text.lower()
    css = "status-neutral"
    if "strong" in lower and ("bull" in lower or "buy" in lower):
        css = "status-strong"
    elif "bull" in lower or "buy" in lower or (score is not None and score >= 70):
        css = "status-bullish"
    elif "bear" in lower or "avoid" in lower or "sell" in lower or (score is not None and score <= 35):
        css = "status-bearish"
    st.markdown(f"<span class='status-badge {css}'>{html.escape(label_text)}</span>", unsafe_allow_html=True)


def confidence_ring(value, label="Trade Confidence"):
    value = int(max(0, min(100, value or 0)))
    st.markdown(
        f"""
        <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;">
            <div class="confidence-ring" style="--value:{value};"><span>{value}%</span></div>
            <div class="confidence-label">{html.escape(label)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def insight_card(title, lines):
    body = "".join([f"<li>{html.escape(str(line))}</li>" for line in lines])
    st.markdown(f"<div class='insight-card'><b>{html.escape(title)}</b><ul>{body}</ul></div>", unsafe_allow_html=True)


def health_meter(value):
    value = int(max(0, min(100, value or 0)))
    st.markdown(f"<div class='health-meter'><span style='width:{value}%'></span></div>", unsafe_allow_html=True)


def probability_summary(model):
    factors = model.get("factors", [])
    rows = "".join(
        f"<li><b>{html.escape(str(item.get('factor')))}</b>: {item.get('weight'):+.2f} - {html.escape(str(item.get('explanation')))}</li>"
        for item in factors[:6]
    )
    st.markdown(
        f"""
        <div class="prob-grid">
            <div class="prob-tile"><b>Probability Score</b><span>{model.get('trade_confidence', 0)}%</span></div>
            <div class="prob-tile"><b>Model Used</b><span>{html.escape(str(model.get('model_name', 'Hybrid AI Scoring Model')))}</span></div>
            <div class="prob-tile"><b>Confidence Level</b><span>{html.escape(str(model.get('confidence_level', 'Moderate')))}</span></div>
            <div class="prob-tile"><b>Risk Confidence</b><span>{model.get('risk_confidence', 0):.0f}%</span></div>
        </div>
        <div class="insight-card">
            <b>Model Logic</b>
            <ul>
                <li>{html.escape(str(model.get('model_description', '')))}</li>
                <li>{html.escape(str(model.get('selected_reason', '')))}</li>
                <li>Positive weight: +{model.get('positive_weight', 0)} | Negative weight: -{model.get('negative_weight', 0)}</li>
            </ul>
        </div>
        <div class="insight-card"><b>Top Probability Factors</b><ul>{rows}</ul></div>
        """,
        unsafe_allow_html=True,
    )


def candlestick_chart(df, title="Price Chart", support=None, resistance=None):
    fig = go.Figure(
        data=[
            go.Candlestick(
                x=df.index,
                open=df["Open"],
                high=df["High"],
                low=df["Low"],
                close=df["Close"],
                name="Price",
                increasing_line_color=GREEN,
                decreasing_line_color=RED,
                increasing_fillcolor="rgba(23,230,165,.72)",
                decreasing_fillcolor="rgba(255,94,122,.72)",
            )
        ]
    )

    if support:
        fig.add_hline(y=support, line_dash="dot", line_color=GREEN, annotation_text="Support")
    if resistance:
        fig.add_hline(y=resistance, line_dash="dot", line_color=RED, annotation_text="Resistance")

    fig.update_layout(xaxis_rangeslider_visible=False)
    apply_chart_theme(fig, height=540, title=title)
    st.plotly_chart(fig, use_container_width=True)


def equity_curve_chart(equity_curve):
    if not equity_curve:
        st.info("No equity curve available.")
        return

    df = pd.DataFrame(equity_curve)
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df["date"],
            y=df["capital"],
            mode="lines+markers",
            name="Capital",
            line=dict(color=CYAN, width=3),
            marker=dict(color=GREEN, size=8),
        )
    )
    apply_chart_theme(fig, height=430, title="Equity Curve")
    st.plotly_chart(fig, use_container_width=True)


def scan_skeleton(message="Scanning the market for BUY setups..."):
    st.markdown(
        f"""
        <div class="scan-banner">
            <b>{html.escape(message)}</b>
            <div style="color:#8FB1C7;margin-top:4px;">Results will appear as soon as qualified opportunities are found.</div>
        </div>
        <div class="suggestion-grid">
            <div class="skeleton"></div>
            <div class="skeleton"></div>
            <div class="skeleton"></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def basket_cards(positions):
    if not positions:
        st.info("No BUY-qualified positions found yet. Try a wider scan, another search filter, or a larger capital amount.")
        return

    cards = []
    for item in positions:
        allocation_pct = float(item.get("allocation_pct", 0) or 0)
        cards.append(
            f"""
        <div class="stock-card">
            <div class="stock-card-head">
                <div class="stock-symbol">{html.escape(str(item.get('display_name') or item.get('symbol') or item.get('ticker')))}</div>
                <div class="pill pill-buy">BUY</div>
            </div>
            <div class="stock-meta">
                <div><b>Confidence</b>{item.get('confidence')}%</div>
                <div><b>Sector</b>{html.escape(str(item.get('sector', 'Unknown')))}</div>
                <div><b>Risk</b>{html.escape(str(item.get('risk_level', 'Unknown')))}</div>
                <div><b>Momentum</b>{html.escape(str(item.get('momentum', 'Neutral')))}</div>
                <div><b>Qty</b>{item.get('qty')}</div>
                <div><b>Allocation</b>Rs. {item.get('allocation')} ({allocation_pct:.1f}%)</div>
            </div>
            <div class="allocation-bar"><span style="width:{max(0, min(100, allocation_pct))}%"></span></div>
            <div class="card-details">
                Entry Rs. {item.get('entry')} | SL Rs. {item.get('stop_loss')} | Target Rs. {item.get('target')} | R:R {item.get('risk_reward')}
            </div>
            <div class="reason">{html.escape(str(item.get('reason', '')))}</div>
        </div>
        """
        )
    html_block(f"<div class='suggestion-grid'>{''.join(cards)}</div>")


def fundamentals_chart(trend_data):
    rows = []
    for metric, values in trend_data.items():
        for date, value in values.items():
            rows.append({"Date": str(date)[:10], "Metric": metric, "Value": value})

    if not rows:
        st.info("Financial trend data unavailable for this ticker.")
        return

    df = pd.DataFrame(rows)
    fig = go.Figure()
    palette = [CYAN, GREEN, BLUE, YELLOW, RED]
    for index, metric in enumerate(df["Metric"].unique()):
        subset = df[df["Metric"] == metric]
        fig.add_trace(
            go.Scatter(
                x=subset["Date"],
                y=subset["Value"],
                mode="lines+markers",
                name=metric,
                line=dict(color=palette[index % len(palette)], width=3),
            )
        )
    apply_chart_theme(fig, height=380, title="Fundamental Trend")
    st.plotly_chart(fig, use_container_width=True)
