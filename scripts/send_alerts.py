"""
Send all unalerted signals from DB to Telegram.
Usage:
    python scripts/send_alerts.py
    python scripts/send_alerts.py --summary   # also sends portfolio summary
    python scripts/send_alerts.py --test      # sends a test message only
"""
import sys, argparse, logging
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import init_db, SessionLocal
from app.signals.store import get_unalerted_signals, mark_alerted
from app.signals.detector import Signal, SignalType, Severity
from app.bot.notifier import send_signals_batch, send_portfolio_summary, send_message
from app.data.pnl import get_live_pnl

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")


def db_row_to_signal(row) -> Signal:
    return Signal(
        ticker=row.ticker,
        signal=SignalType(row.signal),
        severity=Severity(row.severity),
        message=row.message,
        close=row.close or 0,
        rsi=row.rsi,
        macd=row.macd,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", action="store_true",
                        help="Also send portfolio P&L summary")
    parser.add_argument("--test", action="store_true",
                        help="Send a test message to verify bot works")
    args = parser.parse_args()

    init_db()
    db = SessionLocal()

    try:
        if args.test:
            ok = send_message("✅ *Trading Assistant Online*\nTelegram connection working.")
            print("Test message sent ✅" if ok else "Failed ❌ — check token and chat ID")
            return

        # Send portfolio summary first if requested
        if args.summary:
            pnl = get_live_pnl(db)
            ok = send_portfolio_summary(pnl)
            print(f"Portfolio summary {'sent ✅' if ok else 'failed ❌'}")

        # Fetch and send unalerted signals
        unalerted = get_unalerted_signals(db)
        if not unalerted:
            print("No new signals to send.")
            return

        print(f"Sending {len(unalerted)} signal(s) to Telegram...")
        signals = [db_row_to_signal(r) for r in unalerted]
        sent = send_signals_batch(signals)

        if sent:
            ids = [r.id for r in unalerted]
            mark_alerted(ids, db)
            print(f"Sent and marked {len(ids)} signal(s) as alerted ✅")
        else:
            print("Send failed ❌ — check your token and chat ID in .env")

    finally:
        db.close()


if __name__ == "__main__":
    main()
