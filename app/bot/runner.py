import logging
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes,
)
from telegram.constants import ParseMode
from app.config import settings
from app.database import init_db, SessionLocal
from app.bot.commands import (
    cmd_portfolio, cmd_signals, cmd_top, cmd_ask, cmd_scan,
    cmd_add, cmd_addcat, cmd_analytics, cmd_agent,
    cmd_kite_sync, cmd_fno, cmd_watchlist, cmd_market,
    cmd_trade_agent, cmd_morning_briefing,
)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Trading Assistant — War Room Mode*\n\n"
        "*Portfolio:*\n"
        "/portfolio — P&L summary\n"
        "/analytics — risk & allocation\n"
        "/sync — sync from Zerodha Kite\n"
        "/fno — F&O positions\n\n"
        "*Analysis:*\n"
        "/watchlist — morning key levels\n"
        "/scan — signal scan\n"
        "/agent TICKER question\n"
        "/market question\n\n"
        "*Management:*\n"
        "/add TICKER [shares] [price]\n"
        "/addcat gold|silver|oil|nifty\n"
        "/top — best & worst\n"
        "/signals — recent alerts\n\n"
        "*Or just type naturally:*\n"
        "_how is nifty looking today?_\n"
        "_should I hold kpittech?_\n"
        "_crude oil is rising, what trades?_\n"
        "_check ONGC with fibonacci_\n"
        "_what is my portfolio status?_",
        parse_mode=ParseMode.MARKDOWN,
    )


async def portfolio(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        msg = cmd_portfolio(db)
    finally:
        db.close()
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def signals(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        msg = cmd_signals(db)
    finally:
        db.close()
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def top(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        msg = cmd_top(db)
    finally:
        db.close()
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def scan(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Scanning all stocks...")
    db = SessionLocal()
    try:
        msg = cmd_scan(db)
    finally:
        db.close()
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def ask(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    args = ctx.args
    if not args or len(args) < 2:
        await update.message.reply_text(
            "Usage: /ask TICKER question"
        )
        return
    ticker   = args[0]
    question = " ".join(args[1:])
    await update.message.reply_text(f"Analysing {ticker.upper()}...")
    db = SessionLocal()
    try:
        msg = cmd_ask(ticker, question, db)
    finally:
        db.close()
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def add_stock(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    args = ctx.args
    if not args:
        await update.message.reply_text(
            "Usage: /add TICKER [shares] [avg\\_price]",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    ticker    = args[0]
    shares    = float(args[1]) if len(args) > 1 else 0
    avg_price = float(args[2]) if len(args) > 2 else 0
    await update.message.reply_text(f"Adding {ticker.upper()}...")
    db = SessionLocal()
    try:
        msg = cmd_add(ticker, shares, avg_price, db)
    finally:
        db.close()
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def add_category_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    args = ctx.args
    if not args:
        await update.message.reply_text(
            "Usage: /addcat CATEGORY\n"
            "Available: gold, silver, oil, copper, nifty, sensex, nasdaq"
        )
        return
    await update.message.reply_text(f"Adding {args[0]}...")
    db = SessionLocal()
    try:
        msg = cmd_addcat(args[0], db)
    finally:
        db.close()
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def analytics(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        msg = cmd_analytics(db)
    finally:
        db.close()
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def agent_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    args = ctx.args
    if not args or len(args) < 2:
        await update.message.reply_text(
            "Usage: /agent TICKER question"
        )
        return
    ticker   = args[0]
    question = " ".join(args[1:])
    await update.message.reply_text(f"🤖 Analysing {ticker.upper()}...")
    db = SessionLocal()
    try:
        msg = cmd_agent(ticker, question, db)
    finally:
        db.close()
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def kite_sync(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Syncing with Zerodha Kite...")
    db = SessionLocal()
    try:
        msg = cmd_kite_sync(db)
    finally:
        db.close()
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def fno_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        msg = cmd_fno(db)
    finally:
        db.close()
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def watchlist_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Generating watchlist and key levels...")
    db = SessionLocal()
    try:
        msg = cmd_watchlist(db)
    finally:
        db.close()
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def market_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    args = ctx.args
    if not args:
        await update.message.reply_text(
            "Usage: /market your question\n"
            "Example: /market crude oil rising, what trades?"
        )
        return
    query = " ".join(args)
    await update.message.reply_text("Analysing...")
    db = SessionLocal()
    try:
        msg = cmd_market(query, db)
    finally:
        db.close()
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def briefing_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Generating morning briefing...")
    db = SessionLocal()
    try:
        msg = cmd_morning_briefing(db)
    finally:
        db.close()
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def handle_free_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """All free text goes to the full trading agent."""
    text = update.message.text.strip()
    if not text or text.startswith("/"):
        return
    await update.message.reply_text("🤔 Thinking...")
    db = SessionLocal()
    try:
        msg = cmd_trade_agent(text, db)
    except Exception as e:
        msg = f"Error: {e}"
    finally:
        db.close()
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def unknown(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Unknown command. Type /start to see all commands."
    )


def run():
    init_db()
    app = Application.builder().token(settings.telegram_bot_token).build()
    app.add_handler(CommandHandler("start",     start))
    app.add_handler(CommandHandler("portfolio", portfolio))
    app.add_handler(CommandHandler("signals",   signals))
    app.add_handler(CommandHandler("top",       top))
    app.add_handler(CommandHandler("scan",      scan))
    app.add_handler(CommandHandler("ask",       ask))
    app.add_handler(CommandHandler("add",       add_stock))
    app.add_handler(CommandHandler("addcat",    add_category_cmd))
    app.add_handler(CommandHandler("analytics", analytics))
    app.add_handler(CommandHandler("agent",     agent_cmd))
    app.add_handler(CommandHandler("sync",      kite_sync))
    app.add_handler(CommandHandler("fno",       fno_cmd))
    app.add_handler(CommandHandler("watchlist", watchlist_cmd))
    app.add_handler(CommandHandler("market",    market_cmd))
    app.add_handler(CommandHandler("briefing",  briefing_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_free_text))
    app.add_handler(MessageHandler(filters.COMMAND, unknown))
    logger.info("Bot started — war room mode active")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    run()
