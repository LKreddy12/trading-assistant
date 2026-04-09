"""
Signal detector — takes indicator output and fires named signals.
No DB access here. Pure logic on the signals dict from get_latest_signals().
"""
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class SignalType(str, Enum):
    RSI_OVERSOLD       = "RSI_OVERSOLD"
    RSI_OVERBOUGHT     = "RSI_OVERBOUGHT"
    MACD_BULLISH_CROSS = "MACD_BULLISH_CROSS"
    MACD_BEARISH_CROSS = "MACD_BEARISH_CROSS"
    GOLDEN_CROSS       = "GOLDEN_CROSS"
    DEATH_CROSS        = "DEATH_CROSS"
    VOLUME_SPIKE       = "VOLUME_SPIKE"
    BREAKOUT_UP        = "BREAKOUT_UP"
    BREAKOUT_DOWN      = "BREAKOUT_DOWN"
    TREND_REVERSAL_UP  = "TREND_REVERSAL_UP"
    TREND_REVERSAL_DN  = "TREND_REVERSAL_DN"


class Severity(str, Enum):
    INFO    = "INFO"
    WARNING = "WARNING"
    ALERT   = "ALERT"


@dataclass
class Signal:
    ticker:   str
    signal:   SignalType
    severity: Severity
    message:  str
    close:    float
    rsi:      Optional[float] = None
    macd:     Optional[float] = None


def detect_signals(ticker: str, signals: dict, prev_signals: dict = None) -> list[Signal]:
    """
    Compare latest indicator snapshot to previous.
    Returns list of Signal objects — empty if nothing noteworthy.

    signals      — output of get_latest_signals() for today
    prev_signals — output of get_latest_signals() for yesterday (optional)
    """
    fired = []
    prev = prev_signals or {}

    close = signals.get("close", 0)
    rsi   = signals.get("rsi")
    macd  = signals.get("macd")

    # ── RSI signals ──────────────────────────────────────
    if signals.get("rsi_oversold"):
        fired.append(Signal(
            ticker=ticker, signal=SignalType.RSI_OVERSOLD,
            severity=Severity.ALERT,
            message=f"RSI {rsi:.1f} — oversold territory. Potential bounce zone.",
            close=close, rsi=rsi, macd=macd,
        ))

    if signals.get("rsi_overbought"):
        fired.append(Signal(
            ticker=ticker, signal=SignalType.RSI_OVERBOUGHT,
            severity=Severity.WARNING,
            message=f"RSI {rsi:.1f} — overbought. Watch for pullback.",
            close=close, rsi=rsi, macd=macd,
        ))

    # ── MACD crossover signals ────────────────────────────
    if signals.get("macd_bullish_cross"):
        fired.append(Signal(
            ticker=ticker, signal=SignalType.MACD_BULLISH_CROSS,
            severity=Severity.ALERT,
            message=f"MACD bullish crossover at ₹{close:.2f}. Momentum turning up.",
            close=close, rsi=rsi, macd=macd,
        ))

    if signals.get("macd_bearish_cross"):
        fired.append(Signal(
            ticker=ticker, signal=SignalType.MACD_BEARISH_CROSS,
            severity=Severity.WARNING,
            message=f"MACD bearish crossover at ₹{close:.2f}. Momentum turning down.",
            close=close, rsi=rsi, macd=macd,
        ))

    # ── EMA crossover signals ─────────────────────────────
    if signals.get("golden_cross") and not prev.get("golden_cross"):
        fired.append(Signal(
            ticker=ticker, signal=SignalType.GOLDEN_CROSS,
            severity=Severity.ALERT,
            message=f"Golden cross — EMA50 crossed above EMA200. Long-term bullish.",
            close=close, rsi=rsi, macd=macd,
        ))

    if signals.get("death_cross") and not prev.get("death_cross"):
        fired.append(Signal(
            ticker=ticker, signal=SignalType.DEATH_CROSS,
            severity=Severity.ALERT,
            message=f"Death cross — EMA50 crossed below EMA200. Long-term bearish.",
            close=close, rsi=rsi, macd=macd,
        ))

    # ── Volume spike ──────────────────────────────────────
    if signals.get("vol_spike"):
        direction = "with uptrend" if signals.get("price_above_ema20") else "in downtrend"
        severity  = Severity.ALERT if signals.get("price_above_ema20") else Severity.WARNING
        fired.append(Signal(
            ticker=ticker, signal=SignalType.VOLUME_SPIKE,
            severity=severity,
            message=f"Volume spike {direction} at ₹{close:.2f}. Big move possible.",
            close=close, rsi=rsi, macd=macd,
        ))

    # ── Breakout detection ────────────────────────────────
    # Price crossed above EMA50 from below (prev was below, now above)
    was_below_ema50 = prev.get("price_above_ema50") is False
    now_above_ema50 = signals.get("price_above_ema50") is True
    if was_below_ema50 and now_above_ema50:
        fired.append(Signal(
            ticker=ticker, signal=SignalType.BREAKOUT_UP,
            severity=Severity.ALERT,
            message=f"Breakout — price crossed above EMA50 at ₹{close:.2f}.",
            close=close, rsi=rsi, macd=macd,
        ))

    # Price crossed below EMA50 from above
    was_above_ema50 = prev.get("price_above_ema50") is True
    now_below_ema50 = signals.get("price_above_ema50") is False
    if was_above_ema50 and now_below_ema50:
        fired.append(Signal(
            ticker=ticker, signal=SignalType.BREAKOUT_DOWN,
            severity=Severity.WARNING,
            message=f"Breakdown — price crossed below EMA50 at ₹{close:.2f}.",
            close=close, rsi=rsi, macd=macd,
        ))

    # ── Trend reversal ────────────────────────────────────
    # RSI was oversold yesterday, now recovering
    if prev.get("rsi_oversold") and rsi and rsi > 30:
        fired.append(Signal(
            ticker=ticker, signal=SignalType.TREND_REVERSAL_UP,
            severity=Severity.ALERT,
            message=f"RSI recovering from oversold — RSI now {rsi:.1f}. Reversal possible.",
            close=close, rsi=rsi, macd=macd,
        ))

    return fired
