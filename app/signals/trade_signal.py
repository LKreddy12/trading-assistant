"""
Intraday trade signal generator.
Produces BUY/SELL signals with entry, stop-loss, and target.
Limits to MAX_TRADES_PER_DAY total signals per day.
"""
import logging
from dataclasses import dataclass
from datetime import date
from typing import Optional

logger = logging.getLogger(__name__)

MAX_TRADES_PER_DAY = 5
RISK_REWARD_RATIO  = 2.0   # target = entry ± (risk * 2)
ATR_MULT_SL        = 1.5   # stop-loss = entry ± (ATR * 1.5)

# In-memory trade counter (resets on process restart / daily via scheduler)
_today_count: dict[str, int] = {}   # date_str → count


def _trades_today() -> int:
    today = str(date.today())
    return _today_count.get(today, 0)


def _increment_today():
    today = str(date.today())
    _today_count[today] = _today_count.get(today, 0) + 1


def slots_remaining() -> int:
    return max(0, MAX_TRADES_PER_DAY - _trades_today())


@dataclass
class TradeSignal:
    ticker:     str
    direction:  str          # "BUY" or "SELL"
    entry:      float
    stop_loss:  float
    target:     float
    reason:     str
    rsi:        Optional[float] = None
    macd:       Optional[float] = None
    strength:   str = "MODERATE"   # STRONG / MODERATE / WEAK


def compute_atr(df, period: int = 14) -> float:
    """Average True Range — measures volatility for SL sizing."""
    import pandas as pd
    high = df["high"]
    low  = df["low"]
    close_prev = df["close"].shift(1)
    tr = pd.concat([
        high - low,
        (high - close_prev).abs(),
        (low  - close_prev).abs(),
    ], axis=1).max(axis=1)
    atr = tr.rolling(period).mean().iloc[-1]
    return float(atr) if not pd.isna(atr) else 0.0


def generate_trade_signals(ticker: str, df, signals: dict, prev_signals: dict = None) -> list[TradeSignal]:
    """
    Look at indicator state and generate actionable BUY/SELL trade signals
    with entry, SL, and target. Returns empty list if daily cap is reached.
    """
    if slots_remaining() == 0:
        logger.info(f"Daily trade cap ({MAX_TRADES_PER_DAY}) reached — skipping {ticker}")
        return []

    prev  = prev_signals or {}
    fired = []

    close = signals.get("close", 0)
    rsi   = signals.get("rsi")
    macd  = signals.get("macd")

    if not close or close <= 0:
        return []

    atr = compute_atr(df)
    sl_distance = atr * ATR_MULT_SL if atr > 0 else close * 0.005  # fallback 0.5%

    def make_trade(direction: str, reason: str, strength: str = "MODERATE") -> TradeSignal:
        if direction == "BUY":
            sl     = round(close - sl_distance, 2)
            target = round(close + sl_distance * RISK_REWARD_RATIO, 2)
        else:
            sl     = round(close + sl_distance, 2)
            target = round(close - sl_distance * RISK_REWARD_RATIO, 2)
        return TradeSignal(
            ticker=ticker, direction=direction, entry=close,
            stop_loss=sl, target=target, reason=reason,
            rsi=rsi, macd=macd, strength=strength,
        )

    # ── STRONG BUY conditions ────────────────────────────────────────────
    macd_bullish = signals.get("macd_bullish_cross")
    rsi_ok_buy   = rsi and 30 < rsi < 60          # not overbought
    above_ema50  = signals.get("price_above_ema50")

    if macd_bullish and rsi_ok_buy and above_ema50:
        fired.append(make_trade("BUY", "MACD bullish crossover + above EMA50 + RSI healthy", "STRONG"))

    elif macd_bullish and rsi_ok_buy:
        fired.append(make_trade("BUY", "MACD bullish crossover + RSI not overbought", "MODERATE"))

    # RSI bounce from oversold + price above EMA20
    elif prev.get("rsi_oversold") and rsi and rsi > 32 and signals.get("price_above_ema20"):
        fired.append(make_trade("BUY", f"RSI bouncing from oversold ({rsi:.1f}) above EMA20", "MODERATE"))

    # Breakout above EMA50 with volume
    elif (not prev.get("price_above_ema50") and above_ema50 and signals.get("vol_spike")):
        fired.append(make_trade("BUY", "Breakout above EMA50 on volume spike", "STRONG"))

    # ── STRONG SELL conditions ───────────────────────────────────────────
    macd_bearish = signals.get("macd_bearish_cross")
    rsi_ok_sell  = rsi and rsi > 55               # not oversold
    below_ema50  = not signals.get("price_above_ema50")

    if macd_bearish and rsi_ok_sell and below_ema50:
        fired.append(make_trade("SELL", "MACD bearish crossover + below EMA50 + RSI elevated", "STRONG"))

    elif macd_bearish and rsi_ok_sell:
        fired.append(make_trade("SELL", "MACD bearish crossover + RSI not oversold", "MODERATE"))

    # RSI overbought + death cross forming
    elif signals.get("rsi_overbought") and signals.get("death_cross") and not prev.get("death_cross"):
        fired.append(make_trade("SELL", f"RSI overbought ({rsi:.1f}) + Death cross forming", "STRONG"))

    # Breakdown below EMA50 with volume
    elif (prev.get("price_above_ema50") and below_ema50 and signals.get("vol_spike")):
        fired.append(make_trade("SELL", "Breakdown below EMA50 on volume spike", "STRONG"))

    # Increment counter for each signal fired
    for _ in fired:
        if slots_remaining() > 0:
            _increment_today()
        else:
            fired = fired[:MAX_TRADES_PER_DAY - _trades_today() + len(fired)]
            break

    return fired
