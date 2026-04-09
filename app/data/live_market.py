"""
Live market data fetcher.
Fetches real-time Nifty, Bank Nifty, VIX, SGX Nifty, global indices.
Uses yfinance — no API key needed.
"""
import logging
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

MARKET_SYMBOLS = {
    "Nifty 50":        "^NSEI",
    "Bank Nifty":      "^NSEBANK",
    "Sensex":          "^BSESN",
    "India VIX":       "^INDIAVIX",
    "Nifty IT":        "^CNXIT",
    "Nifty Auto":      "^CNXAUTO",
    "Nifty Pharma":    "^CNXPHARMA",
    "Nifty Metal":     "^CNXMETAL",
    "Nifty Energy":    "^CNXENERGY",
    "S&P 500":         "^GSPC",
    "Dow Jones":       "^DJI",
    "NASDAQ":          "^IXIC",
    "Nikkei":          "^N225",
    "Hang Seng":       "^HSI",
    "Crude Oil (WTI)": "CL=F",
    "Gold":            "GC=F",
    "Silver":          "SI=F",
    "USD/INR":         "USDINR=X",
    "Dollar Index":    "DX-Y.NYB",
    "US 10Y Bond":     "^TNX",
    "SGX Nifty":       "^NSEI",
}


def get_live_quote(symbol: str) -> dict:
    """Get live quote for a single symbol."""
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="2d", interval="1d")
        if hist.empty:
            return {}
        
        today = hist.iloc[-1]
        prev  = hist.iloc[-2] if len(hist) > 1 else hist.iloc[-1]
        
        close    = float(today["Close"])
        prev_close = float(prev["Close"])
        change   = close - prev_close
        change_pct = (change / prev_close * 100) if prev_close else 0

        return {
            "symbol":      symbol,
            "close":       round(close, 2),
            "open":        round(float(today["Open"]), 2),
            "high":        round(float(today["High"]), 2),
            "low":         round(float(today["Low"]), 2),
            "prev_close":  round(prev_close, 2),
            "change":      round(change, 2),
            "change_pct":  round(change_pct, 2),
            "volume":      int(today["Volume"]),
        }
    except Exception as e:
        logger.error(f"Quote fetch failed for {symbol}: {e}")
        return {}


def get_intraday(symbol: str, period: str = "1d", interval: str = "5m") -> pd.DataFrame:
    """Get intraday OHLCV data."""
    try:
        df = yf.download(symbol, period=period, interval=interval,
                        progress=False, auto_adjust=True)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0].lower() for c in df.columns]
        else:
            df.columns = [c.lower() for c in df.columns]
        return df
    except Exception as e:
        logger.error(f"Intraday fetch failed for {symbol}: {e}")
        return pd.DataFrame()


def get_nifty_levels() -> dict:
    """Get Nifty with key technical levels."""
    try:
        # Get 3 months of daily data for proper level calculation
        df = yf.download("^NSEI", period="3mo", interval="1d",
                        progress=False, auto_adjust=True)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0].lower() for c in df.columns]
        else:
            df.columns = [c.lower() for c in df.columns]

        if df.empty:
            return {}

        current = float(df["close"].iloc[-1])
        prev    = float(df["close"].iloc[-2])
        high_52w = float(df["high"].max())
        low_52w  = float(df["low"].min())

        # Recent swing levels (last 20 days)
        recent = df.tail(20)
        recent_high = float(recent["high"].max())
        recent_low  = float(recent["low"].min())

        # Previous day OHLC
        pd_high  = float(df["high"].iloc[-2])
        pd_low   = float(df["low"].iloc[-2])
        pd_close = float(df["close"].iloc[-2])

        # Fibonacci retracement from recent swing
        swing_range = recent_high - recent_low
        fib_236 = round(recent_high - 0.236 * swing_range, 2)
        fib_382 = round(recent_high - 0.382 * swing_range, 2)
        fib_500 = round(recent_high - 0.500 * swing_range, 2)
        fib_618 = round(recent_high - 0.618 * swing_range, 2)
        fib_786 = round(recent_high - 0.786 * swing_range, 2)

        # Pivot points
        pivot = round((pd_high + pd_low + pd_close) / 3, 2)
        r1    = round((2 * pivot) - pd_low, 2)
        r2    = round(pivot + (pd_high - pd_low), 2)
        s1    = round((2 * pivot) - pd_high, 2)
        s2    = round(pivot - (pd_high - pd_low), 2)

        change     = current - prev
        change_pct = (change / prev * 100) if prev else 0

        return {
            "current":      round(current, 2),
            "change":       round(change, 2),
            "change_pct":   round(change_pct, 2),
            "high_52w":     round(high_52w, 2),
            "low_52w":      round(low_52w, 2),
            "recent_high":  round(recent_high, 2),
            "recent_low":   round(recent_low, 2),
            "pivot":        pivot,
            "resistance_1": r1,
            "resistance_2": r2,
            "support_1":    s1,
            "support_2":    s2,
            "fib_236":      fib_236,
            "fib_382":      fib_382,
            "fib_500":      fib_500,
            "fib_618":      fib_618,
            "fib_786":      fib_786,
            "trend":        "UPTREND" if current > float(df["close"].rolling(20).mean().iloc[-1]) else "DOWNTREND",
        }
    except Exception as e:
        logger.error(f"Nifty levels failed: {e}")
        return {}


def get_full_market_snapshot() -> dict:
    """Get complete market snapshot — all indices, commodities, global."""
    snapshot = {}

    # Indian indices
    for name, symbol in {
        "Nifty 50":   "^NSEI",
        "Bank Nifty": "^NSEBANK",
        "Sensex":     "^BSESN",
        "India VIX":  "^INDIAVIX",
    }.items():
        q = get_live_quote(symbol)
        if q:
            snapshot[name] = q

    # Global markets
    for name, symbol in {
        "S&P 500": "^GSPC",
        "NASDAQ":  "^IXIC",
        "Nikkei":  "^N225",
        "Dow":     "^DJI",
    }.items():
        q = get_live_quote(symbol)
        if q:
            snapshot[name] = q

    # Commodities
    for name, symbol in {
        "Crude Oil": "CL=F",
        "Gold":      "GC=F",
        "Silver":    "SI=F",
    }.items():
        q = get_live_quote(symbol)
        if q:
            snapshot[name] = q

    # Currency
    q = get_live_quote("USDINR=X")
    if q:
        snapshot["USD/INR"] = q

    return snapshot


def format_market_snapshot(snapshot: dict) -> str:
    """Format market snapshot into readable string for AI context."""
    lines = ["=== LIVE MARKET DATA ==="]

    sections = {
        "INDIAN INDICES": ["Nifty 50", "Bank Nifty", "Sensex", "India VIX"],
        "GLOBAL":         ["S&P 500", "NASDAQ", "Dow", "Nikkei"],
        "COMMODITIES":    ["Crude Oil", "Gold", "Silver"],
        "CURRENCY":       ["USD/INR"],
    }

    for section, keys in sections.items():
        lines.append(f"\n{section}:")
        for key in keys:
            if key in snapshot:
                q = snapshot[key]
                sign = "+" if q["change_pct"] >= 0 else ""
                lines.append(
                    f"  {key}: {q['close']:,.2f} "
                    f"({sign}{q['change_pct']:.2f}%) "
                    f"H:{q['high']:,.2f} L:{q['low']:,.2f}"
                )

    return "\n".join(lines)


def format_nifty_levels(levels: dict) -> str:
    """Format Nifty levels for AI context."""
    if not levels:
        return "Nifty levels unavailable"

    sign = "+" if levels["change_pct"] >= 0 else ""
    return f"""
=== NIFTY 50 LIVE LEVELS ===
Current : {levels['current']:,.2f} ({sign}{levels['change_pct']:.2f}%)
Trend   : {levels['trend']}

KEY LEVELS:
  Resistance 2 : {levels['resistance_2']:,.2f}
  Resistance 1 : {levels['resistance_1']:,.2f}
  Pivot        : {levels['pivot']:,.2f}
  Support 1    : {levels['support_1']:,.2f}
  Support 2    : {levels['support_2']:,.2f}

FIBONACCI LEVELS:
  23.6% : {levels['fib_236']:,.2f}
  38.2% : {levels['fib_382']:,.2f}
  50.0% : {levels['fib_500']:,.2f}
  61.8% : {levels['fib_618']:,.2f}
  78.6% : {levels['fib_786']:,.2f}

RANGE:
  Recent High  : {levels['recent_high']:,.2f}
  Recent Low   : {levels['recent_low']:,.2f}
  52W High     : {levels['high_52w']:,.2f}
  52W Low      : {levels['low_52w']:,.2f}
"""
