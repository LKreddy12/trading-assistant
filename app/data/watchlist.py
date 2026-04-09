"""
Dynamic watchlist manager.
Add/remove any ticker at runtime — stocks, ETFs, gold, commodities.
"""
import logging
import yfinance as yf
from sqlalchemy.orm import Session
from app.data.models import Portfolio
from app.data.fetcher import fetch_and_store

logger = logging.getLogger(__name__)

# Pre-built asset categories for quick add
ASSET_CATEGORIES = {
    "gold": [
        ("GOLDBEES.NS",  "Gold BeES ETF",        "gold"),
        ("GC=F",         "Gold Futures (USD)",    "gold"),
    ],
    "silver": [
        ("SILVERBEES.NS","Silver BeES ETF",       "silver"),
        ("SI=F",         "Silver Futures (USD)",  "silver"),
    ],
    "oil": [
        ("CL=F",         "Crude Oil WTI",         "commodity"),
    ],
    "copper": [
        ("HG=F",         "Copper Futures",        "commodity"),
    ],
    "nifty": [
        ("^NSEI",        "Nifty 50 Index",        "index"),
        ("NIFTYBEES.NS", "Nifty BeES ETF",        "index"),
    ],
    "sensex": [
        ("^BSESN",       "BSE Sensex",            "index"),
    ],
    "nasdaq": [
        ("MON100.NS",    "Motilal NASDAQ 100",    "etf"),
        ("^IXIC",        "NASDAQ Composite",      "index"),
    ],
}


def validate_ticker(ticker: str) -> dict:
    """
    Check if a ticker is valid on Yahoo Finance.
    Returns dict with name, sector, current price or error.
    """
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="5d")
        if hist.empty:
            return {"valid": False, "error": "No price data found"}
        info = t.info or {}
        return {
            "valid":    True,
            "ticker":   ticker,
            "name":     info.get("longName") or info.get("shortName") or ticker,
            "sector":   info.get("sector", "Unknown"),
            "price":    round(float(hist["Close"].iloc[-1]), 2),
            "currency": info.get("currency", "INR"),
        }
    except Exception as e:
        return {"valid": False, "error": str(e)}


def add_to_watchlist(
    ticker: str,
    shares: float,
    avg_buy_price: float,
    db: Session,
    notes: str = "",
) -> dict:
    """
    Add a ticker to portfolio + immediately fetch its price history.
    Works for stocks, ETFs, gold futures, indices — anything yfinance supports.
    """
    ticker = ticker.strip().upper()

    # Validate first
    info = validate_ticker(ticker)
    if not info["valid"]:
        return {"success": False, "error": info["error"]}

    # Add to portfolio table
    existing = db.query(Portfolio).filter_by(ticker=ticker).first()
    if existing:
        existing.shares = shares
        existing.avg_buy_price = avg_buy_price
        existing.notes = notes or existing.notes
        action = "updated"
    else:
        db.add(Portfolio(
            ticker=ticker,
            shares=shares,
            avg_buy_price=avg_buy_price,
            notes=notes or f"Added: {info.get('name', ticker)}",
        ))
        action = "added"
    db.commit()

    # Fetch 6 months of price history immediately
    result = fetch_and_store(ticker, db, period="6mo")

    return {
        "success":    True,
        "action":     action,
        "ticker":     ticker,
        "name":       info.get("name"),
        "price":      info.get("price"),
        "rows_fetched": result.get("rows_fetched", 0),
    }


def remove_from_watchlist(ticker: str, db: Session) -> dict:
    ticker = ticker.strip().upper()
    existing = db.query(Portfolio).filter_by(ticker=ticker).first()
    if not existing:
        return {"success": False, "error": f"{ticker} not in portfolio"}
    db.delete(existing)
    db.commit()
    return {"success": True, "ticker": ticker}


def add_category(category: str, db: Session) -> list:
    """Add a whole category at once e.g. 'gold', 'oil', 'nifty'."""
    category = category.lower()
    if category not in ASSET_CATEGORIES:
        available = ", ".join(ASSET_CATEGORIES.keys())
        return [{"success": False,
                 "error": f"Unknown category. Available: {available}"}]

    results = []
    for ticker, name, notes in ASSET_CATEGORIES[category]:
        result = add_to_watchlist(ticker, 0, 0, db, notes=notes)
        results.append(result)
    return results


def search_nse_ticker(query: str) -> list:
    """
    Search for NSE tickers by company name.
    Returns list of possible matches.
    """
    # Try common variations
    query = query.strip().upper()
    candidates = [
        query + ".NS",
        query + ".BO",
        query,
    ]
    results = []
    for ticker in candidates:
        info = validate_ticker(ticker)
        if info["valid"]:
            results.append(info)
    return results
