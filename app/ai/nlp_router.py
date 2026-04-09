"""
Natural language router.
Parses free-text messages and routes to the right agent function.
No commands needed — just plain English.
"""
import re
import logging
from sqlalchemy.orm import Session
from openai import OpenAI
from app.config import settings

logger = logging.getLogger(__name__)

# Known tickers and aliases
TICKER_ALIASES = {
    "kpit":        "KPITTECH.NS",
    "kpittech":    "KPITTECH.NS",
    "hdfc":        "HDFCBANK.NS",
    "hdfcbank":    "HDFCBANK.NS",
    "tata power":  "TATAPOWER.NS",
    "tatapower":   "TATAPOWER.NS",
    "tata steel":  "TATASTEEL.NS",
    "tatasteel":   "TATASTEEL.NS",
    "tata motors": "TATAMOTORS.NS",
    "tatamotors":  "TATAMOTORS.NS",
    "bel":         "BEL.NS",
    "itc":         "ITC.NS",
    "rvnl":        "RVNL.NS",
    "suzlon":      "SUZLON.NS",
    "rpower":      "RPOWER.NS",
    "reliance power": "RPOWER.NS",
    "motherson":   "MOTHERSON.NS",
    "avantifeed":  "AVANTIFEED.NS",
    "avanti":      "AVANTIFEED.NS",
    "kalyan":      "KALYANKJIL.NS",
    "modefence":   "MODEFENCE.NS",
    "vishal":      "VMM.NS",
    "zomato":      "ZOMATO.NS",
    "gold":        "GC=F",
    "silver":      "SI=F",
    "crude":       "CL=F",
    "crude oil":   "CL=F",
    "oil":         "CL=F",
    "nifty":       "^NSEI",
    "sensex":      "^BSESN",
    "nasdaq":      "MON100.NS",
}

INTENT_PATTERNS = {
    "agent":     [
        r"should i (hold|buy|sell|exit|reduce|add)",
        r"(hold|sell|exit|buy|reduce)\??$",
        r"what (should|do) i do",
        r"is it (good|bad|safe|risky) to",
        r"(outlook|view|opinion|thoughts) on",
        r"(good|right|best) time to (buy|sell|hold)",
        r"cut (my )?(losses|position)",
        r"book (profits|gains)",
    ],
    "research":  [
        r"research",
        r"tell me about",
        r"explain",
        r"what is",
        r"analysis of",
        r"fundamentals",
        r"company (info|details|background)",
    ],
    "swing":     [
        r"swing trad",
        r"short.?term",
        r"(best|top) (stocks|setups|picks)",
        r"trending stocks",
        r"momentum stocks",
        r"breakout",
    ],
    "portfolio": [
        r"my portfolio",
        r"my (stocks|holdings|positions)",
        r"portfolio (summary|status|overview)",
        r"how (am i|is my portfolio) doing",
        r"overall (p&l|pnl|performance)",
    ],
    "signals":   [
        r"(any |recent |latest )?(signals|alerts|notifications)",
        r"what fired",
        r"any alerts",
    ],
    "compare":   [
        r"compare",
        r"vs\.?|versus",
        r"better (between|out of|among)",
        r"which (is better|should i)",
    ],
    "fno":       [
        r"f&o|fno|futures|options",
        r"call option|put option",
        r"(weekly|monthly) expiry",
        r"nifty (options|puts|calls)",
    ],
}


def extract_ticker(text: str) -> str | None:
    text_lower = text.lower()
    for alias, ticker in TICKER_ALIASES.items():
        if alias in text_lower:
            return ticker
    # Try to find uppercase ticker-like words
    matches = re.findall(r'\b([A-Z]{2,12}(?:\.NS|\.BO)?)\b', text)
    if matches:
        candidate = matches[0]
        if not candidate.endswith(".NS") and not candidate.endswith(".BO"):
            candidate += ".NS"
        return candidate
    return None


def detect_intent(text: str) -> str:
    text_lower = text.lower()
    for intent, patterns in INTENT_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text_lower):
                return intent
    return "agent"   # default


def route_message(text: str, db: Session) -> str:
    """
    Parse a free-text message and route to the right handler.
    Returns a formatted response string.
    """
    # Route macro/market queries to trading analyst
    if is_market_query(text):
        from app.ai.trading_analyst import analyse_query
        return analyse_query(text, db)
    
    intent = detect_intent(text)
    ticker = extract_ticker(text)

    logger.info(f"NLP: intent={intent} ticker={ticker} text={text[:60]}")

    if intent == "portfolio":
        from app.bot.commands import cmd_portfolio
        return cmd_portfolio(db)

    if intent == "signals":
        from app.bot.commands import cmd_signals
        return cmd_signals(db)

    if intent == "swing":
        return _swing_scan(db)

    if intent == "compare" and ticker:
        tickers = _extract_all_tickers(text)
        if len(tickers) >= 2:
            return _compare_stocks(tickers[0], tickers[1], db)

    if intent == "fno":
        return _fno_guidance(ticker, text, db)

    if intent == "research" and ticker:
        return _research_stock(ticker, text, db)

    if ticker:
        from app.bot.commands import cmd_agent
        return cmd_agent(ticker, text, db)

    # No ticker found — ask clarifying question
    return (
        "I didn't catch which stock you mean. Try:\n\n"
        "• 'Should I hold KPITTECH?'\n"
        "• 'Research Tata Power'\n"
        "• 'Compare Suzlon vs Tata Power'\n"
        "• 'Best swing trade setups'\n"
        "• 'My portfolio'"
    )


def _extract_all_tickers(text: str) -> list:
    found = []
    text_lower = text.lower()
    for alias, ticker in TICKER_ALIASES.items():
        if alias in text_lower and ticker not in found:
            found.append(ticker)
    return found


def _swing_scan(db: Session) -> str:
    from app.data.models import Portfolio, StockPrice
    from app.indicators.engine import compute_indicators, get_latest_signals
    import pandas as pd

    tickers = [r.ticker for r in db.query(Portfolio).all()]
    setups = []

    for ticker in tickers:
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

        # Swing setup: oversold + MACD turning + volume
        score = 0
        reasons = []
        rsi = sig.get("rsi", 50) or 50

        if rsi < 35:
            score += 2
            reasons.append(f"RSI {rsi:.0f} oversold")
        if sig.get("macd_bullish_cross"):
            score += 3
            reasons.append("MACD bullish cross")
        if sig.get("vol_spike") and sig.get("price_above_ema20"):
            score += 2
            reasons.append("volume breakout")
        if sig.get("price_above_ema50") and rsi > 50:
            score += 1
            reasons.append("uptrend + momentum")

        if score >= 3:
            setups.append({
                "ticker": ticker,
                "score":  score,
                "close":  sig.get("close", 0),
                "reasons": ", ".join(reasons),
            })

    if not setups:
        return "No strong swing setups detected right now. Market is consolidating."

    setups.sort(key=lambda x: x["score"], reverse=True)
    lines = ["📈 *Top Swing Trade Setups*\n"]
    for s in setups[:5]:
        lines.append(
            f"🎯 *{s['ticker']}* (score: {s['score']}/8)\n"
            f"   ₹{s['close']:.2f} — {s['reasons']}"
        )
    lines.append("\n_These are technical setups, not buy recommendations._")
    return "\n".join(lines)


def _compare_stocks(ticker1: str, ticker2: str, db: Session) -> str:
    from app.data.models import StockPrice
    from app.indicators.engine import compute_indicators, get_latest_signals
    from app.data.pnl import get_live_pnl
    import pandas as pd

    def get_sig(ticker):
        rows = (db.query(StockPrice)
                  .filter(StockPrice.ticker == ticker)
                  .order_by(StockPrice.date.asc()).all())
        if not rows:
            return {}
        df = pd.DataFrame([{
            "date": r.date, "open": r.open, "high": r.high,
            "low": r.low, "close": r.close, "volume": r.volume,
        } for r in rows]).set_index("date")
        return get_latest_signals(compute_indicators(df))

    s1 = get_sig(ticker1)
    s2 = get_sig(ticker2)
    pnl_rows = get_live_pnl(db)
    p1 = next((r for r in pnl_rows if r["ticker"] == ticker1), {})
    p2 = next((r for r in pnl_rows if r["ticker"] == ticker2), {})

    def score(s, p):
        sc = 0
        if s.get("price_above_ema50"): sc += 2
        rsi = s.get("rsi", 50) or 50
        if 40 < rsi < 65: sc += 2
        if s.get("macd_bullish_cross"): sc += 2
        if s.get("vol_spike") and s.get("price_above_ema20"): sc += 1
        if (p.get("pnl_pct") or 0) > 0: sc += 1
        return sc

    sc1, sc2 = score(s1, p1), score(s2, p2)
    winner = ticker1 if sc1 >= sc2 else ticker2

    def fmt(ticker, s, p, sc):
        rsi = s.get("rsi", 50) or 50
        trend = "Uptrend" if s.get("price_above_ema50") else "Downtrend"
        pnl = p.get("pnl_pct", 0) or 0
        return (
            f"*{ticker}* (score {sc}/8)\n"
            f"  RSI: {rsi:.0f} | {trend}\n"
            f"  P&L: {'+' if pnl >= 0 else ''}{pnl:.1f}%\n"
            f"  Close: ₹{s.get('close', 0):.2f}"
        )

    lines = [
        "⚖️ *Stock Comparison*\n",
        fmt(ticker1, s1, p1, sc1),
        "",
        fmt(ticker2, s2, p2, sc2),
        "",
        f"🏆 *{winner} looks technically stronger right now*",
        "_Based on trend, RSI, MACD and momentum._",
    ]
    return "\n".join(lines)


def _research_stock(ticker: str, question: str, db: Session) -> str:
    from app.data.models import StockPrice
    from app.indicators.engine import compute_indicators, get_latest_signals
    from app.data.pnl import get_live_pnl
    from app.news.fetcher import fetch_news, format_news_for_prompt
    import pandas as pd

    rows = (db.query(StockPrice)
              .filter(StockPrice.ticker == ticker)
              .order_by(StockPrice.date.asc()).all())
    if not rows:
        return f"No data for {ticker}. Try /add {ticker} first."

    df = pd.DataFrame([{
        "date": r.date, "open": r.open, "high": r.high,
        "low": r.low, "close": r.close, "volume": r.volume,
    } for r in rows]).set_index("date")
    sig  = get_latest_signals(compute_indicators(df))
    pnl_rows = get_live_pnl(db)
    pnl  = next((r for r in pnl_rows if r["ticker"] == ticker), {})
    news = format_news_for_prompt(ticker, fetch_news(ticker, max_articles=5))

    if not settings.openai_api_key or settings.openai_api_key == "placeholder":
        return f"Research for {ticker}:\n\n{news}"

    client = OpenAI(api_key=settings.openai_api_key)
    context = (
        f"Stock: {ticker}\n"
        f"Price: ₹{sig.get('close', 0)}\n"
        f"RSI: {sig.get('rsi', 'N/A')}\n"
        f"Trend: {'Uptrend' if sig.get('price_above_ema50') else 'Downtrend'}\n"
        f"P&L: {pnl.get('pnl_pct', 'N/A')}%\n\n"
        f"{news}"
    )
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an Indian equity research analyst. "
                        "Write a concise research note covering: business overview, "
                        "recent developments, technical position, key risks, key opportunities. "
                        "Keep it under 250 words. Use bullet points."
                    ),
                },
                {
                    "role": "user",
                    "content": f"{context}\n\nQuestion: {question}",
                },
            ],
            max_tokens=400,
            temperature=0.3,
        )
        return f"🔬 *Research: {ticker}*\n\n{resp.choices[0].message.content.strip()}"
    except Exception as e:
        return f"Research for {ticker}:\n\n{news}"


def _fno_guidance(ticker: str | None, text: str, db: Session) -> str:
    if not settings.openai_api_key or settings.openai_api_key == "placeholder":
        return (
            "F&O guidance requires OpenAI API key.\n\n"
            "For F&O trading, key things to watch:\n"
            "• Nifty trend and VIX level\n"
            "• Support/resistance levels\n"
            "• Option chain PCR (Put-Call Ratio)\n"
            "• Open interest buildup"
        )

    context = ""
    if ticker:
        from app.data.models import StockPrice
        from app.indicators.engine import compute_indicators, get_latest_signals
        import pandas as pd
        rows = (db.query(StockPrice)
                  .filter(StockPrice.ticker == ticker)
                  .order_by(StockPrice.date.asc()).all())
        if rows:
            df = pd.DataFrame([{
                "date": r.date, "open": r.open, "high": r.high,
                "low": r.low, "close": r.close, "volume": r.volume,
            } for r in rows]).set_index("date")
            sig = get_latest_signals(compute_indicators(df))
            context = (
                f"Stock: {ticker}\n"
                f"Price: ₹{sig.get('close', 0)}\n"
                f"RSI: {sig.get('rsi', 'N/A')}\n"
                f"Trend: {'Uptrend' if sig.get('price_above_ema50') else 'Downtrend'}\n"
                f"EMA20: {sig.get('ema20', 'N/A')} | EMA50: {sig.get('ema50', 'N/A')}\n"
            )

    client = OpenAI(api_key=settings.openai_api_key)
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an F&O trading expert for Indian markets (NSE). "
                        "Give practical, specific F&O trading guidance. "
                        "Include: strategy type (CE/PE buy/sell), approximate strikes, "
                        "expiry preference, max risk. Always mention this is educational."
                    ),
                },
                {
                    "role": "user",
                    "content": f"{context}\nQuestion: {text}",
                },
            ],
            max_tokens=350,
            temperature=0.3,
        )
        return f"📊 *F&O Guidance*\n\n{resp.choices[0].message.content.strip()}"
    except Exception as e:
        return f"F&O analysis failed: {e}"


def analyse_market_event(event: str, db) -> str:
    from app.ai.trading_analyst import analyse_news_event
    return analyse_news_event(event, db)


def general_market_query(query: str, db) -> str:
    from app.ai.trading_analyst import analyse_query
    return analyse_query(query, db)


MARKET_PATTERNS = [
    r"nifty", r"bank nifty", r"sensex", r"vix",
    r"crude|oil price", r"fed|federal reserve|powell",
    r"rbi|repo rate", r"war|geopolit", r"ongc|reliance",
    r"option|ce |pe |futures", r"intraday|swing trade",
    r"market (open|outlook|today|tomorrow)",
    r"(buy|sell) (call|put|ce|pe)",
    r"breakout|breakdown|support|resistance",
]


def is_market_query(text: str) -> bool:
    import re
    text_lower = text.lower()
    return any(re.search(p, text_lower) for p in MARKET_PATTERNS)
