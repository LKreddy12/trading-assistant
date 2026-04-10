"""
Geopolitical & macro news alerts.
Watches for high-impact news keywords (war, sanctions, Fed, oil, RBI, etc.)
and sends a Telegram alert if something significant is detected.
"""
import logging
from datetime import date

import httpx
from app.config import settings
from app.bot.notifier import send_message

logger = logging.getLogger(__name__)

# High-impact keywords that affect Indian markets
GEOPOLITICAL_KEYWORDS = [
    "war", "sanction", "nuclear", "missile", "attack", "invasion",
    "oil embargo", "crude oil", "OPEC", "Fed rate", "interest rate",
    "RBI rate", "inflation", "recession", "China tension", "Pakistan",
    "Russia Ukraine", "Middle East", "Israel", "Iran", "US tariff",
    "trade war", "dollar index", "rupee fall", "FII sell",
]

MARKET_IMPACT_KEYWORDS = [
    "Nifty", "Sensex", "BSE", "NSE", "SEBI", "Budget", "GST",
    "bank crisis", "market crash", "circuit breaker", "stock halt",
]

ALL_KEYWORDS = GEOPOLITICAL_KEYWORDS + MARKET_IMPACT_KEYWORDS

# Track sent articles to avoid duplicates
_sent_urls: set[str] = set()
_sent_date: str = ""


def _reset_if_new_day():
    global _sent_urls, _sent_date
    today = str(date.today())
    if _sent_date != today:
        _sent_urls.clear()
        _sent_date = today


def _is_high_impact(title: str, description: str) -> tuple[bool, str]:
    """Returns (is_high_impact, matched_keyword)."""
    text = f"{title} {description}".lower()
    for kw in ALL_KEYWORDS:
        if kw.lower() in text:
            return True, kw
    return False, ""


def fetch_geo_news(max_articles: int = 20) -> list[dict]:
    """Fetch latest world/business news that may affect markets."""
    if not settings.news_api_key or settings.news_api_key in ("", "placeholder"):
        return []

    try:
        resp = httpx.get(
            "https://newsapi.org/v2/top-headlines",
            params={
                "category": "business",
                "language": "en",
                "pageSize": max_articles,
                "apiKey":   settings.news_api_key,
            },
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get("articles", [])
    except Exception as e:
        logger.error(f"Geo news fetch failed: {e}")
        return []


def run_geo_news_scan():
    """Check for high-impact news and alert via Telegram."""
    _reset_if_new_day()

    articles = fetch_geo_news()
    if not articles:
        logger.info("Geo news: no articles fetched (check NEWS_API_KEY)")
        return 0

    sent = 0
    for a in articles:
        url   = a.get("url", "")
        title = a.get("title", "")
        desc  = a.get("description", "") or ""

        if not title or "[Removed]" in title:
            continue
        if url in _sent_urls:
            continue

        is_impact, keyword = _is_high_impact(title, desc)
        if not is_impact:
            continue

        _sent_urls.add(url)
        source    = a.get("source", {}).get("name", "")
        published = a.get("publishedAt", "")[:16].replace("T", " ")

        msg = (
            f"🌍 *MARKET-MOVING NEWS*\n"
            f"\n"
            f"📰 {title}\n"
            f"\n"
            f"_{desc[:200] + '...' if len(desc) > 200 else desc}_\n"
            f"\n"
            f"🔑 Keyword: `{keyword}`\n"
            f"📡 Source: {source}  •  {published} UTC"
        )
        send_message(msg)
        logger.info(f"Geo news alert sent: {title[:60]}")
        sent += 1

    return sent
