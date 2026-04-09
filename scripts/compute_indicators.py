"""
Fetch OHLCV from DB, compute indicators, save back to DB.
Then print a full signal summary for every stock in portfolio.

Usage:
    python scripts/compute_indicators.py
    python scripts/compute_indicators.py --ticker BEL.NS
"""
import sys, argparse, logging
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
from sqlalchemy import text

from app.database import init_db, SessionLocal
from app.data.models import StockPrice, Portfolio
from app.indicators.engine import compute_indicators, get_latest_signals
from app.indicators.store import save_indicators

logging.basicConfig(
    level=logging.WARNING,          # suppress info noise
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)


def load_ohlcv_from_db(ticker: str, db) -> pd.DataFrame:
    rows = (
        db.query(StockPrice)
        .filter(StockPrice.ticker == ticker)
        .order_by(StockPrice.date.asc())
        .all()
    )
    if not rows:
        return pd.DataFrame()

    data = [{
        "date":   r.date,
        "open":   r.open,
        "high":   r.high,
        "low":    r.low,
        "close":  r.close,
        "volume": r.volume,
    } for r in rows]

    df = pd.DataFrame(data).set_index("date")
    return df


def signal_icon(value: bool | None) -> str:
    if value is True:  return "✅"
    if value is False: return "❌"
    return "—"


def print_signal_table(ticker: str, signals: dict):
    c     = signals.get("close", 0)
    rsi   = signals.get("rsi", 0)
    macd  = signals.get("macd", 0)
    msig  = signals.get("macd_signal", 0)

    # Momentum summary word
    if rsi < 30:   momentum = "OVERSOLD 🟢"
    elif rsi > 70: momentum = "OVERBOUGHT 🔴"
    elif rsi > 55: momentum = "BULLISH"
    elif rsi < 45: momentum = "BEARISH"
    else:          momentum = "NEUTRAL"

    trend = "UPTREND" if signals.get("price_above_ema50") else "DOWNTREND"
    if signals.get("golden_cross"):  trend += " + GOLDEN CROSS 🌟"
    if signals.get("death_cross"):   trend += " + DEATH CROSS ☠️"

    print(f"\n{'─'*58}")
    print(f"  {ticker}")
    print(f"{'─'*58}")
    print(f"  Close       : ₹{c:>10.2f}")
    print(f"  RSI (14)    : {rsi:>10.2f}    {momentum}")
    print(f"  MACD        : {macd:>10.4f}   Signal: {msig:.4f}")
    print(f"  EMA 20/50   : {signals.get('ema20',0):.2f} / {signals.get('ema50',0):.2f}")
    print(f"  EMA 200     : {signals.get('ema200') or 'N/A (need 200 days)'}")
    print(f"  Trend       : {trend}")
    print(f"  Vol spike   : {signal_icon(signals.get('vol_spike'))}")
    print(f"  MACD cross  : Bull {signal_icon(signals.get('macd_bullish_cross'))}  "
          f"Bear {signal_icon(signals.get('macd_bearish_cross'))}")
    print(f"  RSI oversold: {signal_icon(signals.get('rsi_oversold'))}  "
          f"Overbought: {signal_icon(signals.get('rsi_overbought'))}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", default=None, help="Single ticker, e.g. BEL.NS")
    args = parser.parse_args()

    init_db()

    # Register IndicatorSnapshot table
    from app.indicators.store import IndicatorSnapshot
    from app.database import Base, engine
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        if args.ticker:
            tickers = [args.ticker]
        else:
            tickers = [r.ticker for r in db.query(Portfolio).all()]

        print(f"\n{'='*58}")
        print(f"  TECHNICAL INDICATOR REPORT — {len(tickers)} stocks")
        print(f"{'='*58}")

        all_signals = []

        for ticker in tickers:
            df = load_ohlcv_from_db(ticker, db)
            if df.empty:
                print(f"\n  {ticker} — no price data in DB, skipping")
                continue

            df = compute_indicators(df)
            save_indicators(ticker, df, db)
            signals = get_latest_signals(df)
            signals["ticker"] = ticker
            all_signals.append(signals)
            print_signal_table(ticker, signals)

        # ── summary table ────────────────────────────────
        print(f"\n\n{'='*58}")
        print("  QUICK SUMMARY")
        print(f"{'='*58}")
        print(f"  {'Ticker':<18} {'RSI':>6} {'Trend':<12} {'MACD':>8}  Signals")
        print(f"  {'─'*54}")
        for s in all_signals:
            flags = []
            if s.get("rsi_oversold"):       flags.append("OVERSOLD")
            if s.get("rsi_overbought"):      flags.append("OVERBOUGHT")
            if s.get("macd_bullish_cross"):  flags.append("MACD↑")
            if s.get("macd_bearish_cross"):  flags.append("MACD↓")
            if s.get("vol_spike"):           flags.append("VOL!")
            if s.get("golden_cross"):        flags.append("GOLDEN✨")
            if s.get("death_cross"):         flags.append("DEATH☠️")
            trend = "UP" if s.get("price_above_ema50") else "DOWN"
            print(f"  {s['ticker']:<18} {s.get('rsi',0):>6.1f} {trend:<12} "
                  f"{s.get('macd',0):>8.3f}  {', '.join(flags) or '—'}")
        print(f"{'='*58}\n")

    finally:
        db.close()


if __name__ == "__main__":
    main()
