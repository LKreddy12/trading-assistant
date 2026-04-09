from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.analytics.portfolio import get_portfolio_analytics

router = APIRouter()


@router.get("/")
def portfolio_analytics(db: Session = Depends(get_db)):
    """Full portfolio analytics — P&L, risk, allocation, top/worst."""
    return get_portfolio_analytics(db)
