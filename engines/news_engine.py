import os
import requests
import yfinance as yf

import config
from providers.manager import provider_manager
from utils.observability import log_provider_failure

API_KEY = os.getenv("NEWSAPI_KEY", "YOUR_NEWSAPI_KEY")

POSITIVE_TERMS = {
    "beats": 2,
    "profit": 1,
    "growth": 1,
    "upgrade": 2,
    "buy": 1,
    "strong": 1,
    "record": 1,
    "expansion": 1,
    "order": 1,
    "surge": 1
}

NEGATIVE_TERMS = {
    "misses": -2,
    "loss": -1,
    "downgrade": -2,
    "sell": -1,
    "weak": -1,
    "fraud": -3,
    "probe": -2,
    "debt": -1,
    "fall": -1,
    "slump": -1,
    "resigns": -1
}


def score_text_sentiment(text):
    if not text:
        return 0

    text = text.lower()
    score = 0

    for term, weight in POSITIVE_TERMS.items():
        if term in text:
            score += weight

    for term, weight in NEGATIVE_TERMS.items():
        if term in text:
            score += weight

    return max(-5, min(5, score))


def _normalize_yfinance_item(item):
    content = item.get("content", item)
    title = content.get("title", "")
    summary = content.get("summary", "") or content.get("description", "")

    url = ""
    if isinstance(content.get("canonicalUrl"), dict):
        url = content["canonicalUrl"].get("url", "")
    elif content.get("link"):
        url = content.get("link", "")
    elif content.get("url"):
        url = content.get("url", "")

    return {
        "title": title,
        "url": url,
        "sentiment": score_text_sentiment(f"{title} {summary}"),
        "source": "Yahoo Finance"
    }


def get_yfinance_news(ticker, limit=8):
    try:
        stock = yf.Ticker(ticker)
        raw_news = stock.news or []

        articles = []
        for item in raw_news[:limit]:
            article = _normalize_yfinance_item(item)
            if article["title"]:
                articles.append(article)

        return articles
    except Exception:
        return []


def get_newsapi_news(ticker, limit=8):
    url = f"https://newsapi.org/v2/everything?q={ticker}&apiKey={API_KEY}"

    response = requests.get(url, timeout=10).json()

    articles = []

    for item in response.get("articles", [])[:limit]:
        title = item.get("title", "")
        description = item.get("description", "")
        sentiment = score_text_sentiment(f"{title} {description}")

        articles.append({
            "title": title,
            "url": item.get("url", ""),
            "sentiment": sentiment,
            "source": item.get("source", {}).get("name", "NewsAPI")
        })

    return articles


def get_news(ticker):
    if not config.ENABLE_NEWS:
        return []
    if API_KEY != "YOUR_NEWSAPI_KEY":
        try:
            articles = get_newsapi_news(ticker)
            if articles:
                return articles
        except Exception as exc:
            log_provider_failure("NewsAPI", "get_news", ticker, exc)

    try:
        raw = provider_manager.get_news(ticker)
        return [_normalize_yfinance_item(item) for item in raw[:8]] if raw else []
    except Exception as exc:
        log_provider_failure("DataProviderManager", "get_news", ticker, exc)
        return get_yfinance_news(ticker)


def aggregate_news_sentiment(articles):
    if not articles:
        return {"score": 0, "label": "No news signal"}

    weighted_score = 0
    total_weight = 0

    for index, article in enumerate(articles):
        recency_weight = max(1, 5 - index)
        weighted_score += article.get("sentiment", 0) * recency_weight
        total_weight += recency_weight

    score = weighted_score / total_weight if total_weight else 0

    if score >= 1.5:
        label = "Positive"
    elif score <= -1.5:
        label = "Negative"
    else:
        label = "Neutral"

    return {"score": round(score, 2), "label": label}
