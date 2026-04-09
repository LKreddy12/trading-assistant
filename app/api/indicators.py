from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.data.models import StockPrice, Portfolio
from app.indicators.engine import compute_indicators, get_latest_signals
import pandas as pd

router = APIRouter()


def _load_ohlcv(ticker: str, db: Session) -> pd.DataFrame:
    rows = (db.query(StockPrice)
              .filter(StockPrice.ticker == ticker)
              .order_by(StockPrice.date.asc())
              .all())
    if not rows:
        return pd.DataFrame()
    data = [{"date": r.date, "open": r.open, "high": r.high,
              "low": r.low, "close": r.close, "volume": r.volume}
            for r in rows]
    return pd.DataFrame(data).set_index("date")


@router.get("/{ticker}")
def get_indicators(ticker: str, db: Session = Depends(get_db)):
    """Latest indicator snapshot for a ticker."""
    df = _load_ohlcv(ticker.upper(), db)
    if df.empty:
        raise HTTPException(status_code=404, detail=f"No data for {ticker}")
    df = compute_indicators(df)
    signals = get_latest_signals(df)
    signals["ticker"] = ticker.upper()
    return signals


@router.get("/")
def all_indicators(db: Session = Depends(get_db)):
    """Latest indicators for every stock in portfolio."""
    tickers = [r.ticker for r in db.query(Portfolio).all()]
    results = []
    for ticker in tickers:
        df = _load_ohlcv(ticker, db)
        if df.empty:
            continue
        df = compute_indicators(df)
        sig = get_latest_signals(df)
        sig["ticker"] = ticker
        results.append(sig)
    return results
