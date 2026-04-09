"""
Agentic AI layer.
Chains multiple reasoning steps to produce structured verdicts.

Steps:
  1. Load technical indicators
  2. Fetch and score news sentiment
  3. Analyse sector context
  4. Synthesise everything into a verdict with confidence score
"""
import logging
from dataclasses import dataclass
from typing import Optional
from openai import OpenAI
from sqlalchemy.orm import Session

from app.config import settings
from app.data.models import StockPrice, Portfolio
from app.data.pnl import get_live_pnl
from app.indicators.engine import compute_indicators, get_latest_signals
from app.news.fetcher import fetch_news, format_news_for_prompt, get_company_name
import pandas as pd

logger = logging.getLogger(__name__)

# Sector peers for context
SECTOR_PEERS = {
    "KPITTECH.NS":   ["LTTS.NS", "TATAELXSI.NS", "PERSISTENT.NS"],
    "HDFCBANK.NS":   ["ICICIBANK.NS", "AXISBANK.NS", "KOTAKBANK.NS"],
    "TATAPOWER.NS":  ["NTPC.NS", "ADANIGREEN.NS", "TORNTPOWER.NS"],
    "TATASTEEL.NS":  ["JSWSTEEL.NS", "SAIL.NS", "HINDALCO.NS"],
    "SUZLON.NS":     ["INOXWIND.NS", "ADANIGREEN.NS"],
    "RVNL.NS":       ["IRFC.NS", "IRCON.NS", "RAILTEL.NS"],
    "BEL.NS":        ["HAL.NS", "MAZDOCK.NS", "COCHINSHIP.NS"],
    "AVANTIFEED.NS": ["WATERBASE.NS", "VENKYS.NS"],
    "ITC.NS":        ["HINDUNILVR.NS", "DABUR.NS", "MARICO.NS"],
    "MOTHERSON.NS":  ["BOSCHLTD.NS", "BHARATFORG.NS", "SUNDRMFAST.NS"],
}


@dataclass
class AgentStep:
    name:    str
    result:  str
    score:   Optional[float] = None   # -1 to +1 sentiment/signal score


@dataclass
class AgentVerdict:
    ticker:          str
    question:        str
    recommendation:  str              # BUY / HOLD / REDUCE / EXIT
    confidence:      int              # 0-100
    reasoning:       str
    stop_loss:       Optional[float]
    target:          Optional[float]
    steps:           list[AgentStep]


def _get_openai_client() -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key)


def _load_indicators(ticker: str, db: Session) -> dict:
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


def _score_technicals(signals: dict, pnl: dict) -> tuple[str, float]:
    score = 0.0
    lines = []

    rsi = signals.get("rsi", 50) or 50
    if rsi < 30:
        score += 0.3
        lines.append(f"RSI {rsi:.1f} — oversold, potential bounce")
    elif rsi > 70:
        score -= 0.3
        lines.append(f"RSI {rsi:.1f} — overbought, caution")
    else:
        lines.append(f"RSI {rsi:.1f} — neutral")

    if signals.get("price_above_ema50"):
        score += 0.2
        lines.append("Price above EMA50 — uptrend")
    else:
        score -= 0.2
        lines.append("Price below EMA50 — downtrend")

    if signals.get("macd_bullish_cross"):
        score += 0.3
        lines.append("MACD bullish crossover — momentum turning up")
    elif signals.get("macd_bearish_cross"):
        score -= 0.3
        lines.append("MACD bearish crossover — momentum turning down")

    if signals.get("vol_spike") and signals.get("price_above_ema20"):
        score += 0.2
        lines.append("Volume spike in uptrend — institutional buying")
    elif signals.get("vol_spike"):
        score -= 0.1
        lines.append("Volume spike in downtrend — possible selling pressure")

    pnl_pct = pnl.get("pnl_pct", 0) or 0
    lines.append(f"Position P&L: {'+' if pnl_pct >= 0 else ''}{pnl_pct:.1f}%")
    if pnl_pct < -30:
        score -= 0.2
        lines.append("Down >30% — significant drawdown")
    elif pnl_pct > 30:
        score += 0.1
        lines.append("Up >30% — consider partial profit booking")

    return "\n".join(lines), round(max(-1, min(1, score)), 2)


def _score_news(ticker: str) -> tuple[str, float]:
    articles = fetch_news(ticker, max_articles=5)
    if not articles:
        return "No recent news found.", 0.0

    if not settings.openai_api_key or settings.openai_api_key == "placeholder":
        return format_news_for_prompt(ticker, articles), 0.0

    headlines = "\n".join([f"- {a['title']}" for a in articles[:5]])
    try:
        client = _get_openai_client()
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{
                "role": "user",
                "content": (
                    f"Rate the sentiment of these news headlines for {get_company_name(ticker)} "
                    f"stock from -1.0 (very bearish) to +1.0 (very bullish). "
                    f"Reply with JSON only: {{\"score\": 0.0, \"summary\": \"one sentence\"}}\n\n"
                    f"{headlines}"
                ),
            }],
            max_tokens=100,
            temperature=0,
        )
        import json
        text = resp.choices[0].message.content.strip()
        text = text.replace("```json", "").replace("```", "").strip()
        data = json.loads(text)
        score   = float(data.get("score", 0))
        summary = data.get("summary", "")
        detail  = format_news_for_prompt(ticker, articles)
        return f"{summary}\n\n{detail}", round(score, 2)
    except Exception as e:
        logger.error(f"News sentiment failed: {e}")
        return format_news_for_prompt(ticker, articles), 0.0


def _get_sector_context(ticker: str, db: Session) -> tuple[str, float]:
    peers = SECTOR_PEERS.get(ticker, [])
    if not peers:
        return "No sector peers configured for this stock.", 0.0

    peer_signals = []
    for peer in peers[:3]:
        sig = _load_indicators(peer, db)
        if sig:
            trend = "up" if sig.get("price_above_ema50") else "down"
            rsi   = sig.get("rsi", 50) or 50
            peer_signals.append(f"{peer}: RSI {rsi:.0f}, {trend}trend")

    if not peer_signals:
        return "Peer data not available — fetch peer prices first.", 0.0

    bullish_peers = sum(
        1 for p in peers[:3]
        if _load_indicators(p, db).get("price_above_ema50")
    )
    score = (bullish_peers / len(peers[:3])) * 2 - 1

    summary = f"Sector peers ({', '.join(peers[:3])}):\n"
    summary += "\n".join(peer_signals)
    if bullish_peers == 0:
        summary += "\n→ Entire sector in downtrend — headwinds likely"
    elif bullish_peers == len(peers[:3]):
        summary += "\n→ Sector broadly bullish — tailwinds present"
    else:
        summary += "\n→ Mixed sector signals"

    return summary, round(score, 2)


def _final_verdict(
    ticker: str,
    question: str,
    pnl: dict,
    steps: list[AgentStep],
    close: float,
) -> tuple[str, int, str, Optional[float], Optional[float]]:
    total_score = sum(s.score for s in steps if s.score is not None)
    avg_score   = total_score / max(len([s for s in steps if s.score is not None]), 1)

    steps_text = "\n\n".join([
        f"STEP {i+1} — {s.name}:\n{s.result}"
        for i, s in enumerate(steps)
    ])

    pnl_pct = pnl.get("pnl_pct", 0) or 0

    if not settings.openai_api_key or settings.openai_api_key == "placeholder":
        if avg_score > 0.3:
            rec, conf = "HOLD", 65
        elif avg_score > 0:
            rec, conf = "HOLD", 50
        elif avg_score > -0.3:
            rec, conf = "REDUCE", 55
        else:
            rec, conf = "EXIT", 70
        reasoning = (
            f"Technical score: {avg_score:.2f}. "
            f"Position at {'+' if pnl_pct >= 0 else ''}{pnl_pct:.1f}%."
        )
        stop_loss = round(close * 0.93, 2)
        target    = round(close * 1.10, 2) if rec in ("BUY", "HOLD") else None
        return rec, conf, reasoning, stop_loss, target

    try:
        client = _get_openai_client()
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a senior Indian equity analyst. "
                        "Give a structured verdict based on the analysis steps provided. "
                        "Be direct and specific. Consider the investor's current P&L position."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Stock: {ticker}\n"
                        f"Current price: ₹{close}\n"
                        f"Investor P&L: {'+' if pnl_pct >= 0 else ''}{pnl_pct:.1f}%\n"
                        f"Question: {question}\n\n"
                        f"Analysis steps:\n{steps_text}\n\n"
                        f"Composite signal score: {avg_score:.2f} (-1=bearish, +1=bullish)\n\n"
                        f"Reply with JSON only:\n"
                        f'{{"recommendation": "BUY|HOLD|REDUCE|EXIT", '
                        f'"confidence": 0-100, '
                        f'"reasoning": "2-3 sentences", '
                        f'"stop_loss": price_or_null, '
                        f'"target": price_or_null}}'
                    ),
                },
            ],
            max_tokens=250,
            temperature=0.2,
        )
        import json
        text = resp.choices[0].message.content.strip()
        text = text.replace("```json", "").replace("```", "").strip()
        data = json.loads(text)
        return (
            data.get("recommendation", "HOLD"),
            int(data.get("confidence", 50)),
            data.get("reasoning", ""),
            data.get("stop_loss"),
            data.get("target"),
        )
    except Exception as e:
        logger.error(f"Final verdict OpenAI call failed: {e}")
        rec = "HOLD" if avg_score >= 0 else "REDUCE"
        return rec, 50, f"Signal score: {avg_score:.2f}", round(close * 0.93, 2), None


def run_agent(ticker: str, question: str, db: Session) -> AgentVerdict:
    """
    Full agentic reasoning pipeline.
    Returns a structured AgentVerdict.
    """
    ticker = ticker.strip().upper()
    if "." not in ticker and "=" not in ticker and "^" not in ticker:
        ticker = ticker + ".NS"

    logger.info(f"Agent starting for {ticker}: {question}")
    steps = []

    # Step 1 — Technical analysis
    signals = _load_indicators(ticker, db)
    pnl_rows = get_live_pnl(db)
    pnl = next((r for r in pnl_rows if r["ticker"] == ticker), {})
    close = signals.get("close", 0) or 0

    if signals:
        tech_text, tech_score = _score_technicals(signals, pnl)
        steps.append(AgentStep(
            name="Technical indicators",
            result=tech_text,
            score=tech_score,
        ))
    else:
        steps.append(AgentStep(
            name="Technical indicators",
            result="No price data found in DB. Run /scan first.",
            score=0,
        ))

    # Step 2 — News sentiment
    news_text, news_score = _score_news(ticker)
    steps.append(AgentStep(
        name="News sentiment",
        result=news_text,
        score=news_score,
    ))

    # Step 3 — Sector context
    sector_text, sector_score = _get_sector_context(ticker, db)
    steps.append(AgentStep(
        name="Sector context",
        result=sector_text,
        score=sector_score,
    ))

    # Step 4 — Final verdict
    rec, conf, reasoning, stop_loss, target = _final_verdict(
        ticker, question, pnl, steps, close
    )

    return AgentVerdict(
        ticker=ticker,
        question=question,
        recommendation=rec,
        confidence=conf,
        reasoning=reasoning,
        stop_loss=stop_loss,
        target=target,
        steps=steps,
    )
