"""
Persist fired signals to SQLite.
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean
from sqlalchemy.sql import func
from sqlalchemy.orm import Session
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.database import Base
from app.signals.detector import Signal


class FiredSignal(Base):
    __tablename__ = "fired_signals"

    id         = Column(Integer, primary_key=True)
    ticker     = Column(String, nullable=False, index=True)
    signal     = Column(String, nullable=False)
    severity   = Column(String, nullable=False)
    message    = Column(String)
    close      = Column(Float)
    rsi        = Column(Float)
    macd       = Column(Float)
    alerted    = Column(Boolean, default=False)  # True after Telegram sent
    fired_at   = Column(DateTime, server_default=func.now())


def save_signals(signals: list[Signal], db: Session) -> int:
    if not signals:
        return 0

    rows = [{
        "ticker":   s.ticker,
        "signal":   s.signal.value,
        "severity": s.severity.value,
        "message":  s.message,
        "close":    s.close,
        "rsi":      s.rsi,
        "macd":     s.macd,
        "alerted":  False,
    } for s in signals]

    result = db.execute(
        FiredSignal.__table__.insert(), rows
    )
    db.commit()
    return len(rows)


def get_recent_signals(db: Session, limit: int = 50) -> list:
    return (
        db.query(FiredSignal)
        .order_by(FiredSignal.fired_at.desc())
        .limit(limit)
        .all()
    )


def get_unalerted_signals(db: Session) -> list:
    return (
        db.query(FiredSignal)
        .filter(FiredSignal.alerted == False)
        .order_by(FiredSignal.fired_at.desc())
        .all()
    )


def mark_alerted(signal_ids: list[int], db: Session):
    db.query(FiredSignal).filter(
        FiredSignal.id.in_(signal_ids)
    ).update({"alerted": True}, synchronize_session=False)
    db.commit()
