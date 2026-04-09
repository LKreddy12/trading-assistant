from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.data.pnl import get_live_pnl
from app.data.models import Portfolio

router = APIRouter()


@router.get("/")
def get_portfolio(db: Session = Depends(get_db)):
    """All holdings with live P&L."""
    return get_live_pnl(db)


@router.get("/summary")
def get_summary(db: Session = Depends(get_db)):
    """Total invested, current value, overall P&L."""
    rows = get_live_pnl(db)
    invested = sum(r["invested"] for r in rows if r.get("invested"))
    value    = sum(r["current_value"] for r in rows if r.get("current_value"))
    pnl      = value - invested
    pct      = (pnl / invested * 100) if invested else 0
    return {
        "total_invested":     round(invested, 2),
        "total_current_value":round(value, 2),
        "total_pnl":          round(pnl, 2),
        "total_pnl_pct":      round(pct, 2),
        "holdings_count":     len(rows),
    }


@router.get("/{ticker}")
def get_holding(ticker: str, db: Session = Depends(get_db)):
    """Single holding P&L."""
    rows = get_live_pnl(db)
    match = [r for r in rows if r["ticker"].upper() == ticker.upper()]
    if not match:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"{ticker} not in portfolio")
    return match[0]
