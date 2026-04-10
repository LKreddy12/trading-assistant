"""
Scheduler — runs daily jobs automatically.
Start with: PYTHONPATH=. python app/scheduler.py

Jobs:
  9:00 AM IST  — Market open alert
  9:15–3:15 PM — Intraday scan every 15 min (NIFTY, BANKNIFTY, TCS, Crude)
  Every 30 min — Geopolitical/macro news scan
  9:15 AM IST  — Morning briefing
  3:45 PM IST  — Evening portfolio scan
"""
import logging
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def market_open_alert():
    """Send a market open notification at 9:00 AM."""
    from app.bot.notifier import send_message
    from datetime import datetime
    send_message(
        f"🔔 *Market Open*\n"
        f"NSE/BSE markets are now open.\n"
        f"Watching: NIFTY · BANKNIFTY · SENSEX · TCS · Crude Oil\n"
        f"⏰ {datetime.now().strftime('%d %b %Y  %H:%M IST')}"
    )
    logger.info("Market open alert sent")


def intraday_scan_job():
    """Live intraday scan — runs every 15 min during market hours."""
    from app.scanner.intraday import run_intraday_scan
    logger.info("Running intraday scan...")
    try:
        count = run_intraday_scan()
        logger.info(f"Intraday scan complete — {count} alerts")
    except Exception as e:
        logger.error(f"Intraday scan error: {e}")


def geo_news_job():
    """Geopolitical/macro news scan — runs every 30 min."""
    from app.news.geo_alerts import run_geo_news_scan
    logger.info("Running geo news scan...")
    try:
        count = run_geo_news_scan()
        logger.info(f"Geo news scan complete — {count} alerts")
    except Exception as e:
        logger.error(f"Geo news scan error: {e}")


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

    # ── Market open alert — 9:00 AM IST ─────────────────────────────────
    scheduler.add_job(
        market_open_alert,
        CronTrigger(day_of_week="mon-fri", hour=9, minute=0,
                    timezone="Asia/Kolkata"),
        id="market_open",
        name="Market open alert",
    )

    # ── Morning briefing — 9:15 AM IST ──────────────────────────────────
    scheduler.add_job(
        morning_briefing_job,
        CronTrigger(day_of_week="mon-fri", hour=9, minute=15,
                    timezone="Asia/Kolkata"),
        id="morning_briefing",
        name="Morning briefing",
    )

    # ── Intraday scan — every 15 min, 9:15 AM – 3:15 PM IST ─────────────
    scheduler.add_job(
        intraday_scan_job,
        CronTrigger(
            day_of_week="mon-fri",
            hour="9-15",
            minute="0,15,30,45",
            timezone="Asia/Kolkata",
        ),
        id="intraday_scan",
        name="Intraday scan (every 15 min)",
    )

    # ── Geopolitical news — every 30 min all day ─────────────────────────
    scheduler.add_job(
        geo_news_job,
        CronTrigger(minute="0,30", timezone="Asia/Kolkata"),
        id="geo_news",
        name="Geopolitical news scan",
    )

    # ── Evening portfolio scan — 3:45 PM IST ────────────────────────────
    scheduler.add_job(
        evening_scan_job,
        CronTrigger(day_of_week="mon-fri", hour=15, minute=45,
                    timezone="Asia/Kolkata"),
        id="evening_scan",
        name="Evening scan",
    )

    logger.info("=" * 50)
    logger.info("Trading Assistant Scheduler started")
    logger.info("  9:00 AM  — Market open alert")
    logger.info("  9:15 AM  — Morning briefing")
    logger.info("  9:15–3:15 PM — Intraday scan every 15 min")
    logger.info("  Every 30 min — Geopolitical news")
    logger.info("  3:45 PM  — Evening portfolio scan")
    logger.info("  Watching: NIFTY · BANKNIFTY · SENSEX · TCS · Crude Oil")
    logger.info("=" * 50)

    # Run intraday scan immediately so you see it working
    logger.info("Running intraday scan now for test...")
    intraday_scan_job()

    try:
        scheduler.start()
    except KeyboardInterrupt:
        logger.info("Scheduler stopped")


if __name__ == "__main__":
    main()
