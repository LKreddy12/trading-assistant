from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.signals.store import get_recent_signals, FiredSignal

router = APIRouter()


@router.get("/")
def list_signals(
    limit: int = Query(default=20, le=100),
    ticker: str = Query(default=None),
    db: Session = Depends(get_db),
):
    """Recent signals, optionally filtered by ticker."""
    q = db.query(FiredSignal).order_by(FiredSignal.fired_at.desc())
    if ticker:
        q = q.filter(FiredSignal.ticker == ticker.upper())
    rows = q.limit(limit).all()
    return [
        {
            "id":        r.id,
            "ticker":    r.ticker,
            "signal":    r.signal,
            "severity":  r.severity,
            "message":   r.message,
            "close":     r.close,
            "rsi":       r.rsi,
            "macd":      r.macd,
            "alerted":   r.alerted,
            "fired_at":  str(r.fired_at),
        }
        for r in rows
    ]


@router.get("/unalerted")
def unalerted_signals(db: Session = Depends(get_db)):
    """Signals not yet sent to Telegram."""
    from app.signals.store import get_unalerted_signals
    rows = get_unalerted_signals(db)
    return [{"id": r.id, "ticker": r.ticker, "signal": r.signal,
             "message": r.message, "fired_at": str(r.fired_at)} for r in rows]
