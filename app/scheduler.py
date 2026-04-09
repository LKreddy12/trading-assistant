"""
Scheduler — runs daily jobs automatically.
Start with: PYTHONPATH=. python3 app/scheduler.py
"""
import logging
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def morning_briefing_job():
    from scripts.morning_briefing import main
    logger.info("Running morning briefing...")
    main()


def evening_scan_job():
    """3:45pm scan — after market close."""
    import sys
    sys.path.insert(0, ".")
    from app.database import init_db, SessionLocal
    from app.data.models import Portfolio, StockPrice
    from app.data.fetcher import fetch_and_store
    from app.indicators.engine import compute_indicators, get_latest_signals
    from app.indicators.store import save_indicators
    from app.signals.detector import detect_signals
    from app.signals.store import save_signals, get_unalerted_signals, mark_alerted
    from app.signals.detector import Signal, SignalType, Severity
    from app.bot.notifier import send_signals_batch, send_message
    import pandas as pd

    logger.info("Running evening scan...")
    init_db()
    db = SessionLocal()
    try:
        tickers = [r.ticker for r in db.query(Portfolio).all()]
        fired = []
        for ticker in tickers:
            fetch_and_store(ticker, db, period="6mo")
            rows = (db.query(StockPrice)
                      .filter(StockPrice.ticker == ticker)
                      .order_by(StockPrice.date.asc()).all())
            if not rows:
                continue
            df = pd.DataFrame([{
                "date": r.date, "open": r.open, "high": r.high,
                "low": r.low, "close": r.close, "volume": r.volume,
            } for r in rows]).set_index("date")
            df    = compute_indicators(df)
            save_indicators(ticker, df, db)
            today = get_latest_signals(df)
            prev  = get_latest_signals(df.iloc[:-1]) if len(df) > 1 else {}
            sigs  = detect_signals(ticker, today, prev)
            if sigs:
                save_signals(sigs, db)
                fired.extend(sigs)

        if fired:
            from app.signals.store import get_unalerted_signals, mark_alerted
            unalerted = get_unalerted_signals(db)
            if unalerted:
                signals = [Signal(
                    ticker=r.ticker,
                    signal=SignalType(r.signal),
                    severity=Severity(r.severity),
                    message=r.message,
                    close=r.close or 0,
                    rsi=r.rsi,
                    macd=r.macd,
                ) for r in unalerted]
                send_signals_batch(signals)
                mark_alerted([r.id for r in unalerted], db)
            logger.info(f"Evening scan: {len(fired)} signals sent")
        else:
            logger.info("Evening scan: no new signals")

    finally:
        db.close()


def main():
    scheduler = BlockingScheduler(timezone="Asia/Kolkata")

    # Morning briefing at 9:15am IST (before market opens at 9:30)
    scheduler.add_job(
        morning_briefing_job,
        CronTrigger(day_of_week="mon-fri", hour=9, minute=15,
                    timezone="Asia/Kolkata"),
        id="morning_briefing",
        name="Morning briefing",
    )

    # Evening scan at 3:45pm IST (after market closes at 3:30)
    scheduler.add_job(
        evening_scan_job,
        CronTrigger(day_of_week="mon-fri", hour=15, minute=45,
                    timezone="Asia/Kolkata"),
        id="evening_scan",
        name="Evening scan",
    )

    logger.info("Scheduler started")
    logger.info("Morning briefing: 9:15am IST weekdays")
    logger.info("Evening scan: 3:45pm IST weekdays")

    # Run morning briefing immediately for testing
    logger.info("Running morning briefing now for test...")
    morning_briefing_job()

    try:
        scheduler.start()
    except KeyboardInterrupt:
        logger.info("Scheduler stopped")


if __name__ == "__main__":
    main()
