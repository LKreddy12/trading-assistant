"""
Live intraday scanner — runs every 15 minutes during market hours.
Fetches 5-min candles, computes indicators, detects signals,
generates trade signals with entry/SL/target, sends to Telegram.
"""
import logging
from datetime import datetime, date

import pandas as pd
import yfinance as yf

from app.indicators.engine import compute_indicators, get_latest_signals
from app.signals.detector import detect_signals, Signal, SignalType, Severity
from app.signals.trade_signal import generate_trade_signals, TradeSignal, slots_remaining
from app.bot.notifier import send_message, send_signals_batch

logger = logging.getLogger(__name__)

# yfinance tickers for each instrument
INTRADAY_WATCHLIST = {
    "NIFTY 50":  "^NSEI",
    "BANKNIFTY": "^NSEBANK",
    "SENSEX":    "^BSESN",
    "TCS":       "TCS.NS",
    "CRUDE OIL": "CL=F",
}

# Track last signal state per ticker to detect crossovers correctly
_prev_signals: dict[str, dict] = {}

# Track signals already sent today to avoid duplicates
_sent_today: dict[str, set] = {}   # ticker → set of signal keys


def _sent_key(ticker: str, signal_type: str) -> str:
    return f"{date.today()}:{ticker}:{signal_type}"


def _already_sent(ticker: str, signal_type: str) -> bool:
    return _sent_key(ticker, signal_type) in _sent_today.get(ticker, set())


def _mark_sent(ticker: str, signal_type: str):
    _sent_today.setdefault(ticker, set()).add(_sent_key(ticker, signal_type))


def fetch_intraday_df(ticker_symbol: str, interval: str = "5m", period: str = "5d") -> pd.DataFrame:
    """Download intraday OHLCV from yfinance."""
    try:
        df = yf.download(ticker_symbol, interval=interval, period=period,
                         progress=False, auto_adjust=True)
        if df.empty:
            return pd.DataFrame()
        df = df.rename(columns={
            "Open": "open", "High": "high", "Low": "low",
            "Close": "close", "Volume": "volume",
        })
        # Handle MultiIndex columns (yfinance quirk)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0).str.lower()
        df = df[["open", "high", "low", "close", "volume"]].dropna()
        return df
    except Exception as e:
        logger.error(f"Failed to fetch {ticker_symbol}: {e}")
        return pd.DataFrame()


def format_trade_signal_message(ts: TradeSignal) -> str:
    """Format a trade signal with entry/SL/target for Telegram."""
    direction_icon = "🟢 BUY" if ts.direction == "BUY" else "🔴 SELL"
    strength_icon  = {"STRONG": "🔥", "MODERATE": "⚡", "WEAK": "💤"}.get(ts.strength, "")

    pnl_risk   = round(abs(ts.entry - ts.stop_loss), 2)
    pnl_reward = round(abs(ts.target - ts.entry), 2)

    lines = [
        f"📊 *TRADE SIGNAL — {ts.ticker}*",
        f"",
        f"{direction_icon}  {strength_icon} {ts.strength}",
        f"",
        f"💰 Entry    : ₹{ts.entry:,.2f}",
        f"🛑 Stop Loss: ₹{ts.stop_loss:,.2f}  (risk ₹{pnl_risk:,.2f})",
        f"🎯 Target   : ₹{ts.target:,.2f}  (reward ₹{pnl_reward:,.2f})",
        f"",
        f"📌 Reason: {ts.reason}",
    ]
    if ts.rsi:
        lines.append(f"📈 RSI: {ts.rsi:.1f}")
    if ts.macd:
        lines.append(f"〽️ MACD: {ts.macd:.4f}")
    lines.append(f"\n⏰ {datetime.now().strftime('%d %b %Y  %H:%M IST')}")
    return "\n".join(lines)


def run_intraday_scan():
    """Main scan — call this every 15 minutes during market hours."""
    logger.info(f"Intraday scan started — {datetime.now().strftime('%H:%M')}")
    logger.info(f"Trade slots remaining today: {slots_remaining()}")

    all_indicator_signals: list[Signal]   = []
    all_trade_signals:     list[TradeSignal] = []

    for name, symbol in INTRADAY_WATCHLIST.items():
        try:
            df = fetch_intraday_df(symbol)
            if df.empty or len(df) < 30:
                logger.warning(f"{name}: not enough data ({len(df)} rows)")
                continue

            df      = compute_indicators(df)
            current = get_latest_signals(df)
            prev    = _prev_signals.get(name, {})

            # Detect indicator signals (RSI, MACD crossovers, etc.)
            ind_sigs = detect_signals(name, current, prev)
            for s in ind_sigs:
                if not _already_sent(name, s.signal.value):
                    all_indicator_signals.append(s)
                    _mark_sent(name, s.signal.value)

            # Generate trade signals with entry/SL/target
            if slots_remaining() > 0:
                trade_sigs = generate_trade_signals(name, df, current, prev)
                for ts in trade_sigs:
                    trade_key = f"TRADE_{ts.direction}"
                    if not _already_sent(name, trade_key):
                        all_trade_signals.append(ts)
                        _mark_sent(name, trade_key)

            _prev_signals[name] = current
            logger.info(f"{name}: {len(ind_sigs)} indicator signals, {len(trade_sigs) if slots_remaining() >= 0 else 0} trade signals")

        except Exception as e:
            logger.error(f"Error scanning {name} ({symbol}): {e}")

    # Send indicator alerts
    if all_indicator_signals:
        send_signals_batch(all_indicator_signals)

    # Send trade signals (each as its own message so they're clear)
    for ts in all_trade_signals:
        send_message(format_trade_signal_message(ts))

    total = len(all_indicator_signals) + len(all_trade_signals)
    logger.info(f"Scan complete — {total} alerts sent")
    return total
