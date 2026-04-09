import sys, argparse, logging
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import init_db, SessionLocal
from app.data.portfolio_loader import load_groww_csv
from app.data.fetcher import fetch_watchlist
from app.data.pnl import get_live_pnl, print_pnl_table

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default="portfolio/holdings.csv")
    parser.add_argument("--skip-fetch", action="store_true")
    args = parser.parse_args()

    init_db()
    db = SessionLocal()

    try:
        print(f"\nLoading portfolio from: {args.csv}")
        holdings = load_groww_csv(args.csv, db)
        print(f"Loaded {len(holdings)} holdings")

        if not args.skip_fetch:
            tickers = [h["ticker"] for h in holdings]
            print(f"Fetching latest prices for {len(tickers)} stocks...")
            fetch_watchlist(tickers, db, period="6mo")

        results = get_live_pnl(db)
        print_pnl_table(results)
    finally:
        db.close()

if __name__ == "__main__":
    main()
