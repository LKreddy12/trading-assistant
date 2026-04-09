from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.data.models import StockPrice, Portfolio
from app.data.pnl import get_live_pnl
from app.indicators.engine import compute_indicators, get_latest_signals
from app.news.fetcher import fetch_news, format_news_for_prompt
from app.ai.analyst import ask_about_stock, ask_portfolio_question
import pandas as pd

router = APIRouter()


class AskRequest(BaseModel):
    question: str


def _load_and_compute(ticker: str, db: Session) -> dict:
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


@router.post("/{ticker}")
def ask_stock(ticker: str, body: AskRequest, db: Session = Depends(get_db)):
    """Ask any question about a specific stock."""
    ticker = ticker.upper()

    signals = _load_and_compute(ticker, db)
    if not signals:
        raise HTTPException(status_code=404, detail=f"No data for {ticker}")

    pnl_rows = get_live_pnl(db)
    pnl = next((r for r in pnl_rows if r["ticker"] == ticker), {})

    articles = fetch_news(ticker)
    news_text = format_news_for_prompt(ticker, articles)

    answer = ask_about_stock(ticker, body.question, signals, pnl, news_text)
    return {
        "ticker":   ticker,
        "question": body.question,
        "answer":   answer,
        "context": {
            "rsi":      signals.get("rsi"),
            "trend":    "uptrend" if signals.get("price_above_ema50") else "downtrend",
            "pnl_pct":  pnl.get("pnl_pct"),
        },
    }


@router.post("/")
def ask_portfolio(body: AskRequest, db: Session = Depends(get_db)):
    """Ask a broad question about your whole portfolio."""
    pnl_rows = get_live_pnl(db)

    lines = ["=== PORTFOLIO OVERVIEW ===\n"]
    total_invested = total_value = 0

    for r in pnl_rows:
        if r.get("current_value"):
            total_invested += r["invested"]
            total_value    += r["current_value"]
            sign = "+" if r["pnl_pct"] >= 0 else ""
            lines.append(
                f"{r['ticker']}: ₹{r['ltp']} | "
                f"P&L: {sign}{r['pnl_pct']:.1f}% | "
                f"Trend: {'UP' if r.get('pnl_pct',0) > 0 else 'DOWN'}"
            )

    total_pnl = total_value - total_invested
    total_pct = (total_pnl / total_invested * 100) if total_invested else 0
    lines.append(f"\nTotal P&L: ₹{total_pnl:.2f} ({total_pct:.2f}%)")

    answer = ask_portfolio_question(body.question, "\n".join(lines))
    return {"question": body.question, "answer": answer}
