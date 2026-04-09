"""
Telegram alert sender.
Sends formatted messages for fired signals.
No polling, no webhook — push only for now (Day 7 adds interactive commands).
"""
import logging
import asyncio
from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError

from app.config import settings
from app.signals.detector import Signal, Severity

logger = logging.getLogger(__name__)

SEVERITY_ICON = {
    "ALERT":   "🚨",
    "WARNING": "⚠️",
    "INFO":    "ℹ️",
}


def format_signal_message(signal: Signal) -> str:
    icon = SEVERITY_ICON.get(signal.severity.value, "•")
    lines = [
        f"{icon} *{signal.ticker}* — {signal.signal.value}",
        f"",
        f"📌 {signal.message}",
        f"💰 Close: ₹{signal.close:.2f}",
    ]
    if signal.rsi:
        lines.append(f"📊 RSI: {signal.rsi:.1f}")
    if signal.macd:
        lines.append(f"📈 MACD: {signal.macd:.4f}")
    return "\n".join(lines)


def format_portfolio_summary(pnl_rows: list) -> str:
    total_invested = sum(r["invested"] for r in pnl_rows if r.get("invested"))
    total_value    = sum(r["current_value"] for r in pnl_rows if r.get("current_value"))
    total_pnl      = total_value - total_invested
    total_pct      = (total_pnl / total_invested * 100) if total_invested else 0

    sign = "+" if total_pnl >= 0 else ""
    emoji = "🟢" if total_pnl >= 0 else "🔴"

    lines = [
        f"📊 *Portfolio Summary*",
        f"",
        f"Invested : ₹{total_invested:,.2f}",
        f"Value    : ₹{total_value:,.2f}",
        f"P&L      : {emoji} {sign}₹{total_pnl:,.2f} ({sign}{total_pct:.2f}%)",
        f"",
        f"*Top movers:*",
    ]

    sorted_rows = sorted(
        [r for r in pnl_rows if r.get("pnl_pct") is not None],
        key=lambda x: x["pnl_pct"],
        reverse=True,
    )

    for r in sorted_rows[:3]:
        sign = "+" if r["pnl_pct"] >= 0 else ""
        lines.append(f"  🟢 {r['ticker']}: {sign}{r['pnl_pct']:.1f}%")

    for r in sorted_rows[-3:]:
        if r["pnl_pct"] < 0:
            lines.append(f"  🔴 {r['ticker']}: {r['pnl_pct']:.1f}%")

    return "\n".join(lines)


async def _send(message: str):
    bot = Bot(token=settings.telegram_bot_token)
    await bot.send_message(
        chat_id=settings.telegram_chat_id,
        text=message,
        parse_mode=ParseMode.MARKDOWN,
    )


def send_message(message: str) -> bool:
    """Synchronous wrapper — safe to call from anywhere."""
    if not settings.telegram_bot_token or settings.telegram_bot_token == "placeholder":
        logger.warning("Telegram not configured — skipping send")
        return False
    try:
        asyncio.run(_send(message))
        logger.info("Telegram message sent")
        return True
    except TelegramError as e:
        logger.error(f"Telegram error: {e}")
        return False


def send_signal(signal: Signal) -> bool:
    return send_message(format_signal_message(signal))


def send_signals_batch(signals: list[Signal]) -> int:
    """Send all signals. Returns count of successful sends."""
    if not signals:
        return 0

    # Group into one message if <= 5 signals, else send summary
    if len(signals) <= 5:
        sent = 0
        for s in signals:
            if send_signal(s):
                sent += 1
        return sent
    else:
        # Send a digest
        lines = [f"🔔 *Signal Digest — {len(signals)} alerts*\n"]
        for s in signals:
            icon = SEVERITY_ICON.get(s.severity.value, "•")
            lines.append(f"{icon} *{s.ticker}*: {s.signal.value} @ ₹{s.close:.2f}")
        return 1 if send_message("\n".join(lines)) else 0


def send_portfolio_summary(pnl_rows: list) -> bool:
    return send_message(format_portfolio_summary(pnl_rows))
