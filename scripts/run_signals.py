"""
Full pipeline: fetch prices → compute indicators → detect signals → save → print.
This is the script that will run daily via scheduler (Day 9).

Usage:
    python scripts/run_signals.py
    python scripts/run_signals.py --ticker TATAPOWER.NS
"""
import sys, argparse, logging
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
from app.database import init_db, SessionLocal, Base, engine
from app.data.models import Portfolio, StockPrice
from app.data.fetcher import fetch_and_store
from app.indicators.engine import compute_indicators, get_latest_signals
from app.indicators.store import IndicatorSnapshot, save_indicators
from app.signals.detector import detect_signals
from app.signals.store import FiredSignal, save_signals, get_recent_signals

logging.basicConfig(level=logging.WARNING,
                    format="%(asctime)s [%(levelname)s] %(message)s")

SEVERITY_ICON = {"ALERT": "🚨", "WARNING": "⚠️ ", "INFO": "ℹ️ "}


def load_ohlcv(ticker: str, db) -> pd.DataFrame:
    rows = (db.query(StockPrice)
              .filter(StockPrice.ticker == ticker)
              .order_by(StockPrice.date.asc())
              .all())
    if not rows:
        return pd.DataFrame()
    data = [{"date": r.date, "open": r.open, "high": r.high,
              "low": r.low, "close": r.close, "volume": r.volume}
            for r in rows]
    return pd.DataFrame(data).set_index("date")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", default=None)
    parser.add_argument("--skip-fetch", action="store_true",
                        help="Use cached DB prices, don't call yfinance")
    args = parser.parse_args()

    init_db()
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        tickers = ([args.ticker] if args.ticker
                   else [r.ticker for r in db.query(Portfolio).all()])

        print(f"\n{'='*60}")
        print(f"  SIGNAL SCAN — {len(tickers)} stocks")
        print(f"{'='*60}")

        all_fired = []

        for ticker in tickers:
            # 1 — fetch fresh prices
            if not args.skip_fetch:
                fetch_and_store(ticker, db, period="6mo")

            # 2 — load full OHLCV from DB
            df = load_ohlcv(ticker, db)
            if df.empty:
                continue

            # 3 — compute indicators on full history
            df = compute_indicators(df)
            save_indicators(ticker, df, db)

            # 4 — get signals for today and yesterday
            today_sig = get_latest_signals(df)
            prev_sig  = get_latest_signals(df.iloc[:-1]) if len(df) > 1 else {}

            # 5 — detect what fired
            fired = detect_signals(ticker, today_sig, prev_sig)
            if fired:
                save_signals(fired, db)
                all_fired.extend(fired)

        # ── print results ─────────────────────────────────
        if not all_fired:
            print("\n  No signals fired today. Market is quiet.")
        else:
            print(f"\n  {len(all_fired)} signal(s) fired:\n")
            for s in all_fired:
                icon = SEVERITY_ICON.get(s.severity.value, "•")
                print(f"  {icon} [{s.severity.value}] {s.ticker}")
                print(f"       {s.message}")
                if s.rsi:
                    print(f"       RSI: {s.rsi:.1f}  Close: ₹{s.close:.2f}")
                print()

        # ── recent signal history ─────────────────────────
        print(f"{'─'*60}")
        print("  RECENT SIGNAL HISTORY (last 20)")
        print(f"{'─'*60}")
        recent = get_recent_signals(db, limit=20)
        if not recent:
            print("  No signals in DB yet.")
        else:
            for r in recent:
                icon = SEVERITY_ICON.get(r.severity, "•")
                ts = str(r.fired_at)[:16]
                print(f"  {icon} {ts}  {r.ticker:<18} {r.signal}")
        print(f"{'='*60}\n")

    finally:
        db.close()


if __name__ == "__main__":
    main()
