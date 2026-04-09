import csv
import logging
from pathlib import Path
from sqlalchemy.orm import Session
from app.data.models import Portfolio

logger = logging.getLogger(__name__)

TICKER_MAP = {
    "AMBUJACEM":  "AMBUJACEM.NS",
    "AVANTIFEED": "AVANTIFEED.NS",
    "BEL":        "BEL.NS",
    "HDFCBANK":   "HDFCBANK.NS",
    "ITC":        "ITC.NS",
    "KALYANKJIL": "KALYANKJIL.NS",
    "KPITTECH":   "KPITTECH.NS",
    "MAN50ETF":   "MON100.NS",       # Motilal NASDAQ 100 ETF
    "MODEFENCE":  "MODEFENCE.NS",
    "RVNL":       "RVNL.NS",
    "RPOWER":     "RPOWER.NS",
    "MOTHERSON":  "MOTHERSON.NS",
    "SUZLON":     "SUZLON.NS",
    "TATAMOTORS": "TATAMOTORS.NS",   # Standard symbol works
    "TATAPOWER":  "TATAPOWER.NS",
    "TATASTEEL":  "TATASTEEL.NS",
    "VISHALMEGA": "VMM.NS",          # Vishal Mega Mart
}


def to_yfinance_ticker(symbol: str) -> str:
    symbol = symbol.strip().upper()
    if symbol in TICKER_MAP:
        return TICKER_MAP[symbol]
    if "." in symbol:
        return symbol
    return f"{symbol}.NS"


def load_groww_csv(filepath: str, db: Session) -> list:
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"CSV not found: {filepath}")

    loaded = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        reader.fieldnames = [
            h.strip().lower().replace(" ", "_") for h in reader.fieldnames
        ]
        for row in reader:
            raw_symbol = (row.get("symbol") or row.get("stock_symbol") or "").strip()
            if not raw_symbol or raw_symbol.lower() in ("symbol", "total", ""):
                continue

            ticker = to_yfinance_ticker(raw_symbol)
            try:
                shares = float(row.get("quantity") or row.get("shares") or 0)
                avg_price = float(
                    row.get("average_cost_price")
                    or row.get("avg_cost")
                    or row.get("buy_price")
                    or 0
                )
            except (ValueError, TypeError):
                logger.warning(f"Could not parse numbers for {raw_symbol}, skipping")
                continue

            if shares <= 0 or avg_price <= 0:
                continue

            existing = db.query(Portfolio).filter_by(ticker=ticker).first()
            if existing:
                existing.shares = shares
                existing.avg_buy_price = avg_price
                existing.notes = f"Groww import: {raw_symbol}"
            else:
                db.add(Portfolio(
                    ticker=ticker,
                    shares=shares,
                    avg_buy_price=avg_price,
                    notes=f"Groww import: {raw_symbol}",
                ))

            loaded.append({"ticker": ticker, "shares": shares, "avg_buy_price": avg_price})

    db.commit()
    logger.info(f"Loaded {len(loaded)} holdings from {filepath}")
    return loaded
