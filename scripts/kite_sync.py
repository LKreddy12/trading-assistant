"""
Sync Zerodha Kite holdings into local DB.
Run after kite_login.py to pull your live portfolio.

Usage:
    python3 scripts/kite_sync.py
    python3 scripts/kite_sync.py --fno     # also show F&O positions
"""
import sys
import argparse
import logging
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import init_db, SessionLocal
from app.data.models import Portfolio
from app.data.kite_client import (
    is_authenticated, get_holdings, get_positions,
    get_fno_positions, get_profile,
)
from app.data.fetcher import fetch_and_store

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def sync_holdings(db) -> list:
    """Pull live holdings from Kite and upsert into portfolio table."""
    holdings = get_holdings()
    if not holdings:
        print("No holdings returned from Kite.")
        return []

    for h in holdings:
        existing = db.query(Portfolio).filter_by(ticker=h["ticker"]).first()
        if existing:
            existing.shares       = h["shares"]
            existing.avg_buy_price = h["avg_buy_price"]
            existing.notes        = "Kite sync"
        else:
            db.add(Portfolio(
                ticker=h["ticker"],
                shares=h["shares"],
                avg_buy_price=h["avg_buy_price"],
                notes="Kite sync",
            ))

    db.commit()
    logger.info(f"Synced {len(holdings)} holdings from Kite")
    return holdings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fno", action="store_true",
                        help="Show F&O positions")
    parser.add_argument("--skip-fetch", action="store_true",
                        help="Don't fetch fresh yfinance prices after sync")
    args = parser.parse_args()

    if not is_authenticated():
        print("Not logged in. Run: python3 scripts/kite_login.py")
        sys.exit(1)

    init_db()
    db = SessionLocal()

    try:
        profile = get_profile()
        print(f"\nSyncing for: {profile.get('user_name')} ({profile.get('user_id')})")

        # Sync holdings
        holdings = sync_holdings(db)

        # Print holdings table
        print(f"\n{'='*70}")
        print(f"{'Ticker':<20} {'Shares':>8} {'Avg Price':>12} {'LTP':>12} {'P&L':>12} {'P&L%':>8}")
        print(f"{'-'*70}")
        total_invested = total_value = 0
        for h in sorted(holdings, key=lambda x: x["pnl_pct"], reverse=True):
            sign = "+" if h["pnl"] >= 0 else ""
            print(f"{h['ticker']:<20} {h['shares']:>8.0f} {h['avg_buy_price']:>12.2f} "
                  f"{h['ltp']:>12.2f} {sign}{h['pnl']:>11.2f} {sign}{h['pnl_pct']:>7.2f}%")
            total_invested += h["invested"]
            total_value    += h["current_value"]

        total_pnl = total_value - total_invested
        total_pct = (total_pnl / total_invested * 100) if total_invested else 0
        sign = "+" if total_pnl >= 0 else ""
        print(f"{'='*70}")
        print(f"{'TOTAL':<20} {'':>8} {'':>12} {'':>12} "
              f"{sign}{total_pnl:>11.2f} {sign}{total_pct:>7.2f}%")
        print(f"{'='*70}\n")

        # Fetch fresh prices for all synced holdings
        if not args.skip_fetch:
            tickers = [h["ticker"] for h in holdings]
            print(f"Fetching latest prices for {len(tickers)} stocks...")
            for ticker in tickers:
                fetch_and_store(ticker, db, period="6mo")
            print("Prices updated.\n")

        # F&O positions
        if args.fno:
            fno = get_fno_positions()
            if not fno:
                print("No active F&O positions.")
            else:
                print(f"\n{'='*60}")
                print("F&O POSITIONS")
                print(f"{'='*60}")
                for p in fno:
                    sign = "+" if p["pnl"] >= 0 else ""
                    print(f"{p['symbol']:<25} {p['product']:<6} "
                          f"Qty: {p['quantity']:>6} "
                          f"P&L: {sign}₹{p['pnl']:.2f}")
                print(f"{'='*60}\n")

    finally:
        db.close()


if __name__ == "__main__":
    main()
