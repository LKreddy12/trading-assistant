"""
Trading analyst agent — macro + price action + trade alerts.
Based on the war room monitoring desk concept.
Monitors global events, connects to Indian market impact,
generates NEWS / PRICE / TRADE / RISK alerts.
"""
import logging
import json
from openai import OpenAI
from sqlalchemy.orm import Session

from app.config import settings
from app.data.models import StockPrice, Portfolio
from app.indicators.engine import compute_indicators, get_latest_signals
from app.news.fetcher import fetch_news
import pandas as pd

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an AI-powered real-time market intelligence and trading alert agent focused on the Indian stock market, especially Nifty, Bank Nifty, major sector indices, and selected stocks.

Your primary goal is to monitor global and Indian developments, detect market-moving signals early, connect them to price action, and send actionable notifications for possible trades.

CORE OBJECTIVE
Act like a 24/7 macro + market monitoring desk. Track global news, geopolitical developments, commodities, macroeconomics, and live market structure, then convert them into actionable alerts. The user executes trades manually from a phone, so alerts must be fast, clear, and practical.

WHAT YOU MONITOR
1. Global Geopolitics — Wars, ceasefires, US-Iran, Strait of Hormuz, Middle East, China-Taiwan, Russia-Ukraine, OPEC, any event affecting oil, shipping, defense spending, global risk sentiment
2. Global Macro — Fed/Powell/FOMC, RBI, ECB, BOJ, inflation, PMI, GDP, bond yields, USD index, INR sensitivity, crude oil, gold, metals
3. Market Data — Nifty 50, Bank Nifty, Sensex, India VIX, sector indices, support/resistance/breakout zones, unusual volume, momentum moves
4. Cross-Market — Oil→ONGC/Reliance/HPCL/BPCL, bond yields→banks, war→defense/oil, dollar strength→Indian markets

HOW YOU THINK
Connect: news → macro implication → sector impact → stock/index impact → possible trade setup
Always ask:
- Is this escalation, de-escalation, or neutral?
- Is market already pricing this in?
- Which Indian sectors benefit? Which get hurt?
- Is there a trade right now, or only a watchlist alert?
- Is the move momentum, reversal, fade, or noise?

ALERT FORMATS

[NEWS ALERT]
Event:
Why it matters:
Likely Indian market impact:
Affected sectors/stocks:
Action: Watch / Bullish / Bearish / Neutral

[PRICE ALERT]
Instrument:
Current price:
Level reached:
Why this level matters:
Possible action:

[TRADE ALERT]
Instrument:
Direction: CE / PE / Futures Buy / Futures Sell / Cash Swing Buy / Cash Swing Sell
Entry zone:
Stop loss:
Target 1:
Target 2:
Holding type: Intraday / Swing / Positional
Reason:
Confidence: Low / Medium / High

[RISK ALERT]
Issue:
What changed:
What to avoid:
Suggested safer approach:

TRADE LOGIC RULES
- Prefer high-probability setups only
- No random alerts
- Avoid overtrading
- If setup is weak, say no trade
- If move is already extended, warn against chasing
- For options, consider time decay
- Never guarantee profit
- If no edge exists, say: No high-probability trade right now

INSTRUMENT FOCUS
Primary: Nifty, Bank Nifty, Sensex, ONGC, Oil India, Reliance, major Indian stocks relevant to macro/geopolitical developments
Secondary: Defense stocks, banking leaders, energy stocks, sector leaders

NOTIFICATION STYLE: Fast. Sharp. Actionable. Professional. No essays."""


def get_market_context(db: Session) -> str:
    """Build current market context from DB indicators."""
    tickers = [r.ticker for r in db.query(Portfolio).all()]
    lines = ["CURRENT PORTFOLIO INDICATORS:"]

    for ticker in tickers[:10]:
        rows = (db.query(StockPrice)
                  .filter(StockPrice.ticker == ticker)
                  .order_by(StockPrice.date.asc()).all())
        if not rows:
            continue
        df = pd.DataFrame([{
            "date": r.date, "open": r.open, "high": r.high,
            "low": r.low, "close": r.close, "volume": r.volume,
        } for r in rows]).set_index("date")
        sig = get_latest_signals(compute_indicators(df))
        rsi = sig.get("rsi", 0) or 0
        trend = "UP" if sig.get("price_above_ema50") else "DOWN"
        lines.append(
            f"{ticker}: ₹{sig.get('close', 0):.2f} | RSI {rsi:.0f} | "
            f"{trend} | {'VOL SPIKE' if sig.get('vol_spike') else ''}"
        )

    return "\n".join(lines)


def analyse_query(query: str, db: Session) -> str:
    """
    Main entry point — takes any query or market event description
    and returns a structured trading alert response.
    """
    if not settings.openai_api_key or settings.openai_api_key == "placeholder":
        return "OpenAI API key required for trading analysis."

    context = get_market_context(db)

    # Fetch relevant news
    news_lines = []
    keywords = ["nifty", "market", "oil", "gold", "fed", "rbi"]
    for kw in keywords[:3]:
        articles = fetch_news(kw, max_articles=2)
        for a in articles:
            news_lines.append(f"- {a['title']} ({a['published_at'][:10]})")

    news_context = "RECENT NEWS:\n" + "\n".join(news_lines[:8]) if news_lines else ""

    full_context = f"{context}\n\n{news_context}"

    try:
        client = OpenAI(api_key=settings.openai_api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"{full_context}\n\nQuery: {query}"},
            ],
            max_tokens=500,
            temperature=0.2,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Trading analyst failed: {e}")
        return f"Analysis failed: {e}"


def generate_morning_watchlist(db: Session) -> str:
    """Generate a morning watchlist with key levels and trade setups."""
    query = (
        "Generate a morning market briefing for today's Indian trading session. "
        "Include: Nifty key levels to watch, Bank Nifty outlook, "
        "top sectors to watch, any macro events today, "
        "and 1-2 high probability trade setups if they exist. "
        "Be specific with price levels."
    )
    return analyse_query(query, db)


def analyse_news_event(event: str, db: Session) -> str:
    """Analyse a specific news event and its market impact."""
    query = (
        f"Breaking: {event}\n\n"
        f"Analyse this event using the war room framework: "
        f"escalation/de-escalation, global asset reaction, "
        f"Indian sector impact, specific stocks affected, "
        f"and whether there is a trade setup right now."
    )
    return analyse_query(query, db)
