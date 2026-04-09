import logging
from typing import List, Optional

import pandas as pd
import yfinance as yf
from sqlalchemy.orm import Session
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.data.models import StockPrice

logger = logging.getLogger(__name__)


def fetch_ohlcv(ticker: str, period: str = "6mo", interval: str = "1d") -> Optional[pd.DataFrame]:
    try:
        df = yf.download(
            ticker,
            period=period,
            interval=interval,
            auto_adjust=True,
            progress=False,
            threads=False,
        )
        if df.empty:
            logger.warning(f"No data returned for {ticker}")
            return None

        # New yfinance returns MultiIndex columns like ('Close', 'RELIANCE.NS')
        # Flatten them to simple lowercase strings
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [col[0].lower() for col in df.columns]
        else:
            df.columns = [col.lower() for col in df.columns]

        # Keep only OHLCV columns
        needed = ["open", "high", "low", "close", "volume"]
        missing = [c for c in needed if c not in df.columns]
        if missing:
            logger.error(f"Missing columns for {ticker}: {missing}. Got: {df.columns.tolist()}")
            return None

        df = df[needed].copy()
        df.index = pd.to_datetime(df.index).tz_localize(None)
        df.dropna(subset=["close"], inplace=True)

        logger.info(f"Fetched {len(df)} rows for {ticker}")
        return df

    except Exception as e:
        logger.error(f"fetch_ohlcv failed for {ticker}: {e}")
        return None


def store_ohlcv(ticker: str, df: pd.DataFrame, db: Session) -> int:
    rows = []
    for date, row in df.iterrows():
        rows.append({
            "ticker": ticker,
            "date": date.to_pydatetime(),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row["volume"]),
        })

    if not rows:
        return 0

    stmt = sqlite_insert(StockPrice).values(rows)
    stmt = stmt.on_conflict_do_nothing(index_elements=["ticker", "date"])
    result = db.execute(stmt)
    db.commit()
    return result.rowcount


def fetch_and_store(ticker: str, db: Session, period: str = "6mo") -> dict:
    df = fetch_ohlcv(ticker, period=period)
    if df is None:
        return {"ticker": ticker, "status": "error", "rows_fetched": 0, "rows_inserted": 0, "latest_close": 0}

    inserted = store_ohlcv(ticker, df, db)
    latest = df.iloc[-1]
    return {
        "ticker": ticker,
        "status": "ok",
        "rows_fetched": len(df),
        "rows_inserted": inserted,
        "latest_close": round(float(latest["close"]), 2),
        "latest_date": df.index[-1].strftime("%Y-%m-%d"),
    }


def fetch_watchlist(tickers: List[str], db: Session, period: str = "6mo") -> List[dict]:
    results = []
    for ticker in tickers:
        results.append(fetch_and_store(ticker, db, period=period))
    return results
