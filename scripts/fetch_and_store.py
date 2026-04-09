import sys, logging
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings
from app.database import init_db, SessionLocal
from app.data.fetcher import fetch_watchlist

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)

def main():
    init_db()
    db = SessionLocal()
    try:
        results = fetch_watchlist(settings.watchlist, db, period="6mo")
    finally:
        db.close()

    print("\n" + "=" * 62)
    print(f"{'Ticker':<18} {'Status':<8} {'Fetched':>8} {'Inserted':>9} {'Close':>10}")
    print("-" * 62)
    for r in results:
        if r["status"] == "ok":
            print(f"{r['ticker']:<18} ok       {r['rows_fetched']:>8} "
                  f"{r['rows_inserted']:>9} {r['latest_close']:>10.2f}")
        else:
            print(f"{r['ticker']:<18} ERROR")
    print("=" * 62)

if __name__ == "__main__":
    main()
