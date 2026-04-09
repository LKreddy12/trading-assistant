from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database import get_db
from app.data.watchlist import (
    add_to_watchlist, remove_from_watchlist,
    add_category, search_nse_ticker, validate_ticker
)

router = APIRouter()


class AddTickerRequest(BaseModel):
    ticker: str
    shares: float = 0
    avg_buy_price: float = 0
    notes: str = ""


class AddCategoryRequest(BaseModel):
    category: str


@router.post("/add")
def add_ticker(body: AddTickerRequest, db: Session = Depends(get_db)):
    """Add any ticker to portfolio — stock, ETF, gold, commodity."""
    result = add_to_watchlist(
        body.ticker, body.shares, body.avg_buy_price, db, body.notes
    )
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.delete("/remove/{ticker}")
def remove_ticker(ticker: str, db: Session = Depends(get_db)):
    result = remove_from_watchlist(ticker, db)
    if not result["success"]:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.post("/add-category")
def add_asset_category(body: AddCategoryRequest, db: Session = Depends(get_db)):
    """Add a full category: gold, silver, oil, copper, nifty, sensex, nasdaq."""
    return add_category(body.category, db)


@router.get("/search/{query}")
def search_ticker(query: str):
    """Search for a ticker by company name or symbol."""
    results = search_nse_ticker(query)
    if not results:
        return {"query": query, "matches": [],
                "hint": f"Try {query}.NS or {query}.BO"}
    return {"query": query, "matches": results}


@router.get("/validate/{ticker}")
def validate(ticker: str):
    """Check if a ticker is valid before adding."""
    return validate_ticker(ticker)
