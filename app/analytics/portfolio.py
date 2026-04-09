"""
Portfolio analytics — P&L breakdown, risk metrics, sector allocation.
"""
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.data.pnl import get_live_pnl
from app.data.models import Portfolio, StockPrice
from app.indicators.engine import compute_indicators, get_latest_signals
import pandas as pd


def get_portfolio_analytics(db: Session) -> dict:
    rows = get_live_pnl(db)
    valid = [r for r in rows if r.get("current_value") and r.get("pnl_pct") is not None]

    if not valid:
        return {"error": "No price data available"}

    total_invested = sum(r["invested"] for r in valid)
    total_value    = sum(r["current_value"] for r in valid)
    total_pnl      = total_value - total_invested
    total_pct      = (total_pnl / total_invested * 100) if total_invested else 0

    sorted_rows = sorted(valid, key=lambda x: x["pnl_pct"], reverse=True)

    # Winners and losers
    winners = [r for r in valid if r["pnl_pct"] > 0]
    losers  = [r for r in valid if r["pnl_pct"] < 0]

    # Concentration — top 3 holdings by value
    by_value = sorted(valid, key=lambda x: x["current_value"], reverse=True)
    top3_value = sum(r["current_value"] for r in by_value[:3])
    concentration = (top3_value / total_value * 100) if total_value else 0

    # Best single-day potential (largest volume spike stocks)
    risk_stocks = [r for r in valid if r["pnl_pct"] < -30]

    return {
        "summary": {
            "total_invested":      round(total_invested, 2),
            "total_value":         round(total_value, 2),
            "total_pnl":           round(total_pnl, 2),
            "total_pnl_pct":       round(total_pct, 2),
            "winners_count":       len(winners),
            "losers_count":        len(losers),
            "win_rate_pct":        round(len(winners) / len(valid) * 100, 1),
            "concentration_top3_pct": round(concentration, 1),
        },
        "top_performers": [
            {
                "ticker":    r["ticker"],
                "pnl_pct":   r["pnl_pct"],
                "pnl":       r["pnl"],
                "ltp":       r["ltp"],
            }
            for r in sorted_rows[:5]
        ],
        "worst_performers": [
            {
                "ticker":    r["ticker"],
                "pnl_pct":   r["pnl_pct"],
                "pnl":       r["pnl"],
                "ltp":       r["ltp"],
            }
            for r in sorted_rows[-5:]
        ],
        "high_risk_positions": [
            {
                "ticker":  r["ticker"],
                "pnl_pct": r["pnl_pct"],
                "invested": r["invested"],
                "note":    "Down >30% — review stop loss",
            }
            for r in risk_stocks
        ],
        "allocation": [
            {
                "ticker":  r["ticker"],
                "value":   round(r["current_value"], 2),
                "weight_pct": round(r["current_value"] / total_value * 100, 1),
            }
            for r in by_value
        ],
    }
