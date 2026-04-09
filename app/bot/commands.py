import logging
import pandas as pd
from sqlalchemy.orm import Session
from app.data.pnl import get_live_pnl
from app.signals.store import get_recent_signals
from app.data.models import StockPrice, Portfolio
from app.indicators.engine import compute_indicators, get_latest_signals
from app.news.fetcher import fetch_news, format_news_for_prompt
from app.ai.analyst import ask_about_stock, ask_portfolio_question

logger = logging.getLogger(__name__)


def cmd_portfolio(db: Session) -> str:
    rows = get_live_pnl(db)
    if not rows:
        return "No holdings found."
    total_invested = sum(r["invested"] for r in rows if r.get("invested"))
    total_value    = sum(r["current_value"] for r in rows if r.get("current_value"))
    total_pnl      = total_value - total_invested
    total_pct      = (total_pnl / total_invested * 100) if total_invested else 0
    sign           = "+" if total_pnl >= 0 else ""
    emoji          = "🟢" if total_pnl >= 0 else "🔴"
    lines = [
        f"📊 *Portfolio — {len(rows)} stocks*",
        f"",
        f"Invested : ₹{total_invested:,.0f}",
        f"Value    : ₹{total_value:,.0f}",
        f"P&L      : {emoji} {sign}₹{total_pnl:,.0f} ({sign}{total_pct:.1f}%)",
        f"",
    ]
    for r in sorted(rows, key=lambda x: x.get("pnl_pct") or 0, reverse=True):
        if r.get("pnl_pct") is None:
            continue
        e = "🟢" if r["pnl_pct"] >= 0 else "🔴"
        s = "+" if r["pnl_pct"] >= 0 else ""
        lines.append(f"{e} {r['ticker']} {s}{r['pnl_pct']:.1f}%")
    return "\n".join(lines)


def cmd_signals(db: Session, limit: int = 10) -> str:
    rows = get_recent_signals(db, limit=limit)
    if not rows:
        return "No signals in the last scan."
    icon = {"ALERT": "🚨", "WARNING": "⚠️", "INFO": "ℹ️"}
    lines = [f"🔔 *Recent Signals*", ""]
    for r in rows:
        ts = str(r.fired_at)[:10]
        lines.append(f"{icon.get(r.severity, '•')} {r.ticker} — {r.signal}")
        lines.append(f"   {r.message}")
        lines.append(f"   {ts}")
        lines.append("")
    return "\n".join(lines)


def cmd_top(db: Session) -> str:
    rows = get_live_pnl(db)
    valid = [r for r in rows if r.get("pnl_pct") is not None]
    if not valid:
        return "No price data available."
    sorted_rows = sorted(valid, key=lambda x: x["pnl_pct"], reverse=True)
    lines = ["📈 *Top Performers*", ""]
    for r in sorted_rows[:3]:
        s = "+" if r["pnl_pct"] >= 0 else ""
        lines.append(f"🟢 {r['ticker']}: {s}{r['pnl_pct']:.1f}% | ₹{r['ltp']:.2f}")
    lines += ["", "📉 *Worst Performers*", ""]
    for r in sorted_rows[-3:]:
        lines.append(f"🔴 {r['ticker']}: {r['pnl_pct']:.1f}% | ₹{r['ltp']:.2f}")
    return "\n".join(lines)


def cmd_ask(ticker: str, question: str, db: Session) -> str:
    ticker = ticker.upper()
    if not ticker.endswith(".NS") and not ticker.endswith(".BO"):
        ticker = ticker + ".NS"
    rows = (db.query(StockPrice)
              .filter(StockPrice.ticker == ticker)
              .order_by(StockPrice.date.asc()).all())
    if not rows:
        return f"No data found for {ticker}."
    df = pd.DataFrame([{
        "date": r.date, "open": r.open, "high": r.high,
        "low": r.low, "close": r.close, "volume": r.volume,
    } for r in rows]).set_index("date")
    signals  = get_latest_signals(compute_indicators(df))
    pnl_rows = get_live_pnl(db)
    pnl      = next((r for r in pnl_rows if r["ticker"] == ticker), {})
    articles = fetch_news(ticker)
    news     = format_news_for_prompt(ticker, articles)
    answer   = ask_about_stock(ticker, question, signals, pnl, news)
    return f"🤖 *{ticker}*\n_{question}_\n\n{answer}"


def cmd_scan(db: Session) -> str:
    from app.data.fetcher import fetch_and_store
    from app.indicators.store import save_indicators
    from app.signals.detector import detect_signals
    from app.signals.store import save_signals
    tickers = [r.ticker for r in db.query(Portfolio).all()]
    fired_count = 0
    for ticker in tickers:
        fetch_and_store(ticker, db, period="5d")
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
        fired = detect_signals(ticker, today, prev)
        if fired:
            save_signals(fired, db)
            fired_count += len(fired)
    return f"✅ Scan complete — {len(tickers)} stocks checked, {fired_count} new signal(s) fired."


def cmd_add(ticker: str, shares: float, avg_price: float, db: Session) -> str:
    from app.data.watchlist import add_to_watchlist, validate_ticker
    ticker = ticker.upper()
    # Auto-append .NS if no suffix and not a futures symbol
    if "." not in ticker and "=" not in ticker and "^" not in ticker:
        info = validate_ticker(ticker + ".NS")
        if info["valid"]:
            ticker = ticker + ".NS"
        else:
            info2 = validate_ticker(ticker + ".BO")
            if info2["valid"]:
                ticker = ticker + ".BO"
    result = add_to_watchlist(ticker, shares, avg_price, db)


def cmd_addcat(category: str, db: Session) -> str:
    from app.data.watchlist import add_category
    results = add_category(category, db)
    lines = [f"📦 *Adding category: {category}*\n"]
    for r in results:
        if r.get("success"):
            lines.append(f"✅ {r['ticker']} — {r.get('name', '')}")
        else:
            lines.append(f"❌ {r.get('error', 'failed')}")
    return "\n".join(lines)


def cmd_analytics(db: Session) -> str:
    from app.analytics.portfolio import get_portfolio_analytics
    a = get_portfolio_analytics(db)
    if "error" in a:
        return a["error"]
    s = a["summary"]
    sign = "+" if s["total_pnl"] >= 0 else ""
    emoji = "🟢" if s["total_pnl"] >= 0 else "🔴"
    lines = [
        f"📊 *Portfolio Analytics*\n",
        f"{emoji} P&L: {sign}₹{s['total_pnl']:,.0f} ({sign}{s['total_pnl_pct']:.1f}%)",
        f"Win rate : {s['win_rate_pct']:.0f}% ({s['winners_count']}W / {s['losers_count']}L)",
        f"Top-3 concentration: {s['concentration_top3_pct']:.0f}%\n",
        f"🏆 *Top 3*",
    ]
    for r in a["top_performers"][:3]:
        lines.append(f"  🟢 {r['ticker']}: +{r['pnl_pct']:.1f}%")
    lines.append(f"\n⚠️ *High risk*")
    if a["high_risk_positions"]:
        for r in a["high_risk_positions"]:
            lines.append(f"  🔴 {r['ticker']}: {r['pnl_pct']:.1f}% — {r['note']}")
    else:
        lines.append("  None — all positions within acceptable range")
    return "\n".join(lines)


def cmd_agent(ticker: str, question: str, db: Session) -> str:
    from app.ai.agent import run_agent
    verdict = run_agent(ticker, question, db)

    rec_emoji = {
        "BUY":    "🟢",
        "HOLD":   "🔵",
        "REDUCE": "🟡",
        "EXIT":   "🔴",
    }.get(verdict.recommendation, "⚪")

    lines = [
        f"🤖 *Agent Analysis — {verdict.ticker}*",
        f"_{verdict.question}_\n",
        f"{'─' * 30}",
        f"*Step 1 — Technicals*",
        f"{verdict.steps[0].result if verdict.steps else 'N/A'}",
        f"\n*Step 2 — News*",
        f"{verdict.steps[1].result[:300] if len(verdict.steps) > 1 else 'N/A'}",
        f"\n*Step 3 — Sector*",
        f"{verdict.steps[2].result if len(verdict.steps) > 2 else 'N/A'}",
        f"\n{'─' * 30}",
        f"{rec_emoji} *Verdict: {verdict.recommendation}*",
        f"Confidence: {verdict.confidence}%",
        f"\n{verdict.reasoning}",
    ]
    if verdict.stop_loss:
        lines.append(f"\nStop loss : ₹{verdict.stop_loss}")
    if verdict.target:
        lines.append(f"Target    : ₹{verdict.target}")

    return "\n".join(lines)


def cmd_kite_sync(db) -> str:
    from app.data.kite_client import is_authenticated, get_holdings, get_profile
    from app.data.models import Portfolio
    from app.data.fetcher import fetch_and_store

    if not is_authenticated():
        return (
            "❌ Not connected to Kite.\n\n"
            "Run this on your computer:\n"
            "`python3 scripts/kite_login.py`\n\n"
            "Then try /sync again."
        )

    profile = get_profile()
    holdings = get_holdings()
    if not holdings:
        return "No holdings found in your Kite account."

    for h in holdings:
        existing = db.query(Portfolio).filter_by(ticker=h["ticker"]).first()
        if existing:
            existing.shares        = h["shares"]
            existing.avg_buy_price = h["avg_buy_price"]
            existing.notes         = "Kite sync"
        else:
            db.add(Portfolio(
                ticker=h["ticker"],
                shares=h["shares"],
                avg_buy_price=h["avg_buy_price"],
                notes="Kite sync",
            ))
    db.commit()

    total_pnl = sum(h["pnl"] for h in holdings)
    sign  = "+" if total_pnl >= 0 else ""
    emoji = "🟢" if total_pnl >= 0 else "🔴"

    lines = [
        f"✅ *Kite Sync Complete*",
        f"Account: {profile.get('user_name')}",
        f"Holdings: {len(holdings)} stocks",
        f"Today's P&L: {emoji} {sign}₹{total_pnl:,.2f}",
        f"",
        f"Top movers:",
    ]
    for h in sorted(holdings, key=lambda x: x["pnl_pct"], reverse=True)[:3]:
        s = "+" if h["pnl_pct"] >= 0 else ""
        lines.append(f"  🟢 {h['ticker']}: {s}{h['pnl_pct']:.1f}%")

    return "\n".join(lines)


def cmd_fno(db) -> str:
    from app.data.kite_client import is_authenticated, get_fno_positions

    if not is_authenticated():
        return "❌ Not connected to Kite. Run `python3 scripts/kite_login.py` first."

    positions = get_fno_positions()
    if not positions:
        return "No active F&O positions."

    total_pnl = sum(p["pnl"] for p in positions)
    sign  = "+" if total_pnl >= 0 else ""
    emoji = "🟢" if total_pnl >= 0 else "🔴"

    lines = [
        f"📊 *F&O Positions*",
        f"Total P&L: {emoji} {sign}₹{total_pnl:,.2f}\n",
    ]
    for p in positions:
        s = "+" if p["pnl"] >= 0 else ""
        e = "🟢" if p["pnl"] >= 0 else "🔴"
        lines.append(
            f"{e} *{p['symbol']}*\n"
            f"   {p['product']} | Qty: {p['quantity']} | "
            f"Avg: ₹{p['avg_price']:.2f}\n"
            f"   LTP: ₹{p['ltp']:.2f} | P&L: {s}₹{p['pnl']:.2f}"
        )
    return "\n".join(lines)


def cmd_watchlist(db) -> str:
    from app.ai.trading_analyst import generate_morning_watchlist
    return generate_morning_watchlist(db)


def cmd_market(query: str, db) -> str:
    from app.ai.trading_analyst import analyse_query
    return analyse_query(query, db)


def cmd_trade_agent(query: str, db) -> str:
    """Full account-aware trading agent."""
    from app.ai.trading_agent import run as agent_run
    return agent_run(query, db)


def cmd_morning_briefing(db) -> str:
    """Morning briefing with full account context."""
    from app.ai.trading_agent import morning_briefing
    return morning_briefing(db)
