"""
Full trading agent — account-aware, macro-aware, live market data.
"""
import logging
from openai import OpenAI
from sqlalchemy.orm import Session

from app.config import settings
from app.data.models import StockPrice, Portfolio
from app.data.kite_client import is_authenticated, get_holdings, get_fno_positions
from app.data.live_market import (
    get_full_market_snapshot, format_market_snapshot,
    get_nifty_levels, format_nifty_levels,
    get_live_quote, get_intraday,
)
from app.indicators.engine import compute_indicators, get_latest_signals
from app.news.fetcher import fetch_news
import pandas as pd

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an AI-powered trading agent connected to Zerodha Kite and Telegram.

You have access to LIVE market data including real Nifty levels, Bank Nifty, VIX, global indices, commodities, and Fibonacci/pivot levels. Use this data to give specific, precise answers — not generic ones.

ACCOUNT AWARENESS
Always check account context first:
- Holdings, positions, P&L, available balance
- Never give isolated advice without account context
- "You already hold ONGC CE from 10.20 — this is continuation, not fresh entry"

TECHNICAL ANALYSIS
When asked about levels, use the actual live data provided:
- Give specific support/resistance numbers
- Give specific Fibonacci levels
- Give specific pivot points
- Give trade bias with entry/SL/target

ALERT FORMATS

[NEWS ALERT]
Event: | Why it matters: | Indian market impact: | Sectors: | Action:

[TRADE ALERT]
Instrument: | Direction: CE/PE/Futures Buy/Sell/Cash Swing
Entry zone: | Stop loss: | Target 1: | Target 2:
Holding type: Intraday/Swing/Positional
Reason: | Confidence: Low/Medium/High

[RISK ALERT]
Issue: | What changed: | What to avoid: | Safer approach:

[PORTFOLIO ALERT]
Holding: | Entry vs current: | P&L: | Action:

RULES
- Use actual numbers from live data — never say "check the levels"
- If asked about Nifty opening — give specific levels based on global cues
- If asked about support/resistance — give exact numbers from pivot/fib data
- No high-probability trade? Say: "No edge right now"
- Never guarantee profit

CROSS-MARKET LOGIC
Oil rise → ONGC/Oil India/Reliance up → Airlines/Paint stocks down
Bond yields up → Banks under pressure → Growth stocks down
War escalation → Defense up, Oil up, Market risk-off
Dollar strong → IT stocks up → Import sectors down
Fed hawkish → FIIs sell → Nifty pressure
VIX above 20 → High volatility → Reduce position size"""


def build_account_context(db: Session) -> str:
    lines = []
    if is_authenticated():
        try:
            holdings = get_holdings()
            if holdings:
                lines.append("LIVE KITE HOLDINGS:")
                total_pnl = sum(h["pnl"] for h in holdings)
                sign = "+" if total_pnl >= 0 else ""
                lines.append(f"Total P&L today: {sign}₹{total_pnl:,.2f}")
                for h in holdings:
                    s = "+" if h["pnl"] >= 0 else ""
                    lines.append(
                        f"  {h['ticker']}: {h['shares']} shares @ "
                        f"₹{h['avg_buy_price']:.2f} | LTP ₹{h['ltp']:.2f} | "
                        f"P&L: {s}₹{h['pnl']:.2f} ({s}{h['pnl_pct']:.1f}%)"
                    )
            fno = get_fno_positions()
            if fno:
                lines.append("\nF&O POSITIONS:")
                for p in fno:
                    s = "+" if p["pnl"] >= 0 else ""
                    lines.append(
                        f"  {p['symbol']}: qty {p['quantity']} @ "
                        f"₹{p['avg_price']:.2f} | LTP ₹{p['ltp']:.2f} | "
                        f"P&L: {s}₹{p['pnl']:.2f}"
                    )
        except Exception as e:
            lines.append(f"Kite live fetch failed: {e}")
            lines.extend(_cached_context(db))
    else:
        lines.append("KITE: Session expired — run kite_daily_login.py")
        lines.extend(_cached_context(db))
    return "\n".join(lines)


def _cached_context(db: Session) -> list:
    from app.data.pnl import get_live_pnl
    rows = get_live_pnl(db)
    lines = ["CACHED PORTFOLIO:"]
    for r in rows:
        if r.get("ltp"):
            s = "+" if (r.get("pnl_pct") or 0) >= 0 else ""
            lines.append(
                f"  {r['ticker']}: {r['shares']} @ ₹{r['avg_buy_price']:.2f} | "
                f"LTP ₹{r['ltp']:.2f} | {s}{r.get('pnl_pct',0):.1f}%"
            )
    return lines


def build_technical_context(db: Session) -> str:
    tickers = [r.ticker for r in db.query(Portfolio).all()]
    lines = ["\nPORTFOLIO TECHNICALS:"]
    for ticker in tickers[:12]:
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
        rsi  = sig.get("rsi", 0) or 0
        macd = sig.get("macd", 0) or 0
        trend = "UP" if sig.get("price_above_ema50") else "DOWN"
        flags = []
        if sig.get("rsi_oversold"):       flags.append("OVERSOLD")
        if sig.get("rsi_overbought"):     flags.append("OVERBOUGHT")
        if sig.get("macd_bullish_cross"): flags.append("MACD_BULL")
        if sig.get("macd_bearish_cross"): flags.append("MACD_BEAR")
        if sig.get("vol_spike"):          flags.append("VOL_SPIKE")
        lines.append(
            f"  {ticker}: ₹{sig.get('close',0):.2f} RSI:{rsi:.0f} "
            f"MACD:{macd:.2f} {trend} {' '.join(flags)}"
        )
    return "\n".join(lines)


def build_news_context() -> str:
    lines = ["\nLATEST NEWS:"]
    for topic in ["nifty india market", "crude oil opec", "federal reserve rbi india"]:
        for a in fetch_news(topic, max_articles=2):
            lines.append(f"  [{a['published_at'][:10]}] {a['title']}")
    return "\n".join(lines)


def run(query: str, db: Session) -> str:
    if not settings.openai_api_key or settings.openai_api_key == "placeholder":
        return "OpenAI API key required."

    # Detect if query needs live market data
    needs_nifty  = any(w in query.lower() for w in [
        "nifty", "bank nifty", "open", "level", "support", "resistance",
        "fibonacci", "fib", "pivot", "target", "market", "sensex", "vix"
    ])
    needs_stock  = any(w in query.lower() for w in [
        "ongc", "reliance", "hdfc", "crude", "gold", "silver", "oil"
    ])

    # Always fetch live market data
    print("Fetching live market data...")
    snapshot   = get_full_market_snapshot()
    market_ctx = format_market_snapshot(snapshot)

    nifty_ctx = ""
    if needs_nifty:
        print("Fetching Nifty levels...")
        levels    = get_nifty_levels()
        nifty_ctx = format_nifty_levels(levels)

    account_ctx   = build_account_context(db)
    technical_ctx = build_technical_context(db)
    news_ctx      = build_news_context()

    full_context = (
        f"{market_ctx}\n"
        f"{nifty_ctx}\n"
        f"{account_ctx}\n"
        f"{technical_ctx}\n"
        f"{news_ctx}"
    )

    try:
        client = OpenAI(api_key=settings.openai_api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",
                 "content": f"{full_context}\n\nUser query: {query}"},
            ],
            max_tokens=600,
            temperature=0.2,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Agent error: {e}")
        return f"Agent error: {e}"


def morning_briefing(db: Session) -> str:
    query = (
        "Generate a sharp morning trading briefing. Include: "
        "1) Nifty and Bank Nifty opening bias with specific levels "
        "2) Global cues summary "
        "3) Key support and resistance for Nifty today "
        "4) Top sectors to watch "
        "5) 1-2 trade setups if edge exists "
        "6) Risk warnings. Use the actual live data provided. Be specific."
    )
    return run(query, db)
