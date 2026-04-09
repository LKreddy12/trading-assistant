"""
Persist computed indicator snapshots to SQLite.
One row per ticker per date — same upsert pattern as stock_prices.
"""
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import Session
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
import pandas as pd

from app.database import Base


class IndicatorSnapshot(Base):
    __tablename__ = "indicator_snapshots"

    id          = Column(Integer, primary_key=True)
    ticker      = Column(String, nullable=False, index=True)
    date        = Column(DateTime, nullable=False)
    close       = Column(Float)
    rsi         = Column(Float)
    macd        = Column(Float)
    macd_signal = Column(Float)
    macd_hist   = Column(Float)
    ema20       = Column(Float)
    ema50       = Column(Float)
    ema200      = Column(Float)
    vol_spike   = Column(Boolean)
    created_at  = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("ticker", "date", name="uq_indicator_ticker_date"),
    )


def save_indicators(ticker: str, df: pd.DataFrame, db: Session) -> int:
    """Save all indicator rows for a ticker. Skips rows where RSI is null."""
    rows = []
    for date, row in df.iterrows():
        if pd.isna(row.get("rsi")):
            continue
        rows.append({
            "ticker":      ticker,
            "date":        date.to_pydatetime(),
            "close":       float(row["close"]),
            "rsi":         float(row["rsi"]) if not pd.isna(row.get("rsi")) else None,
            "macd":        float(row["macd"]) if not pd.isna(row.get("macd")) else None,
            "macd_signal": float(row["macd_signal"]) if not pd.isna(row.get("macd_signal")) else None,
            "macd_hist":   float(row["macd_hist"]) if not pd.isna(row.get("macd_hist")) else None,
            "ema20":       float(row["ema20"]) if not pd.isna(row.get("ema20")) else None,
            "ema50":       float(row["ema50"]) if not pd.isna(row.get("ema50")) else None,
            "ema200":      float(row.get("ema200")) if row.get("ema200") and not pd.isna(row.get("ema200")) else None,
            "vol_spike":   bool(row["vol_spike"]) if not pd.isna(row.get("vol_spike")) else False,
        })

    if not rows:
        return 0

    stmt = sqlite_insert(IndicatorSnapshot).values(rows)
    stmt = stmt.on_conflict_do_nothing(index_elements=["ticker", "date"])
    result = db.execute(stmt)
    db.commit()
    return result.rowcount
