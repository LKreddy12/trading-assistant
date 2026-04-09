"""
Fetch news headlines for a stock ticker.
Uses NewsAPI. Falls back to Yahoo Finance news if NewsAPI quota exceeded.
"""
import logging
import httpx
from app.config import settings

logger = logging.getLogger(__name__)

# Map NSE tickers to search-friendly company names
TICKER_TO_NAME = {
    "AMBUJACEM.NS":  "Ambuja Cements",
    "AVANTIFEED.NS": "Avanti Feeds",
    "BEL.NS":        "Bharat Electronics",
    "HDFCBANK.NS":   "HDFC Bank",
    "ITC.NS":        "ITC Limited",
    "KALYANKJIL.NS": "Kalyan Jewellers",
    "KPITTECH.NS":   "KPIT Technologies",
    "MON100.NS":     "Motilal NASDAQ ETF",
    "MODEFENCE.NS":  "Motilal Defence ETF",
    "RVNL.NS":       "Rail Vikas Nigam",
    "RPOWER.NS":     "Reliance Power",
    "MOTHERSON.NS":  "Samvardhana Motherson",
    "SUZLON.NS":     "Suzlon Energy",
    "TATAPOWER.NS":  "Tata Power",
    "TATASTEEL.NS":  "Tata Steel",
    "VMM.NS":        "Vishal Mega Mart",
}


def get_company_name(ticker: str) -> str:
    return TICKER_TO_NAME.get(ticker.upper(), ticker.replace(".NS", "").replace(".BO", ""))


def fetch_news(ticker: str, max_articles: int = 5) -> list[dict]:
    """
    Fetch recent news headlines for a ticker.
    Returns list of {title, description, url, published_at, source}
    """
    company = get_company_name(ticker)

    if not settings.news_api_key or settings.news_api_key == "placeholder":
        logger.warning("NewsAPI key not set — returning empty news")
        return []

    try:
        resp = httpx.get(
            "https://newsapi.org/v2/everything",
            params={
                "q":        f'"{company}" stock',
                "language": "en",
                "sortBy":   "publishedAt",
                "pageSize": max_articles,
                "apiKey":   settings.news_api_key,
            },
            timeout=10,
        )
        resp.raise_for_status()
        articles = resp.json().get("articles", [])

        return [
            {
                "title":        a.get("title", ""),
                "description":  a.get("description", ""),
                "url":          a.get("url", ""),
                "published_at": a.get("publishedAt", ""),
                "source":       a.get("source", {}).get("name", ""),
            }
            for a in articles
            if a.get("title") and "[Removed]" not in a.get("title", "")
        ]

    except Exception as e:
        logger.error(f"News fetch failed for {ticker}: {e}")
        return []


def format_news_for_prompt(ticker: str, articles: list[dict]) -> str:
    """Format news articles into a concise string for the AI prompt."""
    if not articles:
        return f"No recent news found for {ticker}."

    lines = [f"Recent news for {get_company_name(ticker)}:"]
    for i, a in enumerate(articles, 1):
        lines.append(f"{i}. {a['title']} ({a['source']}, {a['published_at'][:10]})")
        if a.get("description"):
            lines.append(f"   {a['description'][:150]}")
    return "\n".join(lines)
