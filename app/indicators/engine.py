"""
Indicator engine using the 'ta' library (Python 3.10 compatible).
Computes RSI, MACD, EMA, volume spike on OHLCV DataFrame.
"""
import pandas as pd
import ta
import logging

logger = logging.getLogger(__name__)

RSI_PERIOD        = 14
MACD_FAST         = 12
MACD_SLOW         = 26
MACD_SIGNAL       = 9
EMA_SHORT         = 20
EMA_MID           = 50
EMA_LONG          = 200
VOLUME_SPIKE_MULT = 1.5


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    if len(df) < 30:
        logger.warning(f"Only {len(df)} rows — not enough for indicators")
        return df

    df = df.copy()

    # RSI
    df["rsi"] = ta.momentum.RSIIndicator(
        close=df["close"], window=RSI_PERIOD
    ).rsi()

    # MACD
    macd_obj = ta.trend.MACD(
        close=df["close"],
        window_fast=MACD_FAST,
        window_slow=MACD_SLOW,
        window_sign=MACD_SIGNAL,
    )
    df["macd"]        = macd_obj.macd()
    df["macd_signal"] = macd_obj.macd_signal()
    df["macd_hist"]   = macd_obj.macd_diff()

    # EMAs
    df["ema20"]  = ta.trend.EMAIndicator(close=df["close"], window=EMA_SHORT).ema_indicator()
    df["ema50"]  = ta.trend.EMAIndicator(close=df["close"], window=EMA_MID).ema_indicator()
    df["ema200"] = ta.trend.EMAIndicator(close=df["close"], window=EMA_LONG).ema_indicator()

    # Volume spike
    df["vol_avg20"] = df["volume"].rolling(20).mean()
    df["vol_spike"] = df["volume"] > (df["vol_avg20"] * VOLUME_SPIKE_MULT)

    return df


def get_latest_signals(df: pd.DataFrame) -> dict:
    if df.empty or len(df) < 2:
        return {}

    row  = df.iloc[-1]
    prev = df.iloc[-2]

    def safe(val):
        try:
            v = float(val)
            return None if pd.isna(v) else v
        except (TypeError, ValueError):
            return None

    close      = safe(row["close"])
    rsi        = safe(row.get("rsi"))
    macd       = safe(row.get("macd"))
    macd_sig   = safe(row.get("macd_signal"))
    macd_hist  = safe(row.get("macd_hist"))
    ema20      = safe(row.get("ema20"))
    ema50      = safe(row.get("ema50"))
    ema200     = safe(row.get("ema200"))
    vol_spike  = bool(row.get("vol_spike", False))

    prev_macd  = safe(prev.get("macd")) or 0
    prev_msig  = safe(prev.get("macd_signal")) or 0

    return {
        "close":              close,
        "rsi":                round(rsi, 2) if rsi else None,
        "macd":               round(macd, 4) if macd else None,
        "macd_signal":        round(macd_sig, 4) if macd_sig else None,
        "macd_hist":          round(macd_hist, 4) if macd_hist else None,
        "ema20":              round(ema20, 2) if ema20 else None,
        "ema50":              round(ema50, 2) if ema50 else None,
        "ema200":             round(ema200, 2) if ema200 else None,
        "vol_spike":          vol_spike,
        "rsi_oversold":       rsi < 30 if rsi else None,
        "rsi_overbought":     rsi > 70 if rsi else None,
        "macd_bullish_cross": (prev_macd < prev_msig) and (macd > macd_sig) if (macd and macd_sig) else False,
        "macd_bearish_cross": (prev_macd > prev_msig) and (macd < macd_sig) if (macd and macd_sig) else False,
        "price_above_ema20":  close > ema20 if (close and ema20) else None,
        "price_above_ema50":  close > ema50 if (close and ema50) else None,
        "price_above_ema200": close > ema200 if (close and ema200) else None,
        "golden_cross":       (ema50 > ema200) if (ema50 and ema200) else None,
        "death_cross":        (ema50 < ema200) if (ema50 and ema200) else None,
    }
