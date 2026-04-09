"""
AI analyst — uses OpenAI to answer natural language questions
about stocks using real indicator + news + portfolio context.
"""
import logging
from openai import OpenAI
from app.config import settings

logger = logging.getLogger(__name__)
client = None


def get_client() -> OpenAI:
    global client
    if client is None:
        client = OpenAI(api_key=settings.openai_api_key)
    return client


def build_stock_context(
    ticker: str,
    signals: dict,
    pnl: dict,
    news_text: str,
) -> str:
    """Build the context block fed to the AI."""
    lines = [
        f"=== STOCK: {ticker} ===",
        f"",
        f"PRICE & P&L:",
        f"  Current price : ₹{signals.get('close', 'N/A')}",
        f"  Avg buy price : ₹{pnl.get('avg_buy_price', 'N/A')}",
        f"  Shares held   : {pnl.get('shares', 'N/A')}",
        f"  Invested      : ₹{pnl.get('invested', 'N/A')}",
        f"  Current value : ₹{pnl.get('current_value', 'N/A')}",
        f"  Unrealised P&L: ₹{pnl.get('pnl', 'N/A')} ({pnl.get('pnl_pct', 'N/A')}%)",
        f"",
        f"TECHNICAL INDICATORS:",
        f"  RSI (14)      : {signals.get('rsi', 'N/A')}",
        f"  MACD          : {signals.get('macd', 'N/A')}",
        f"  MACD Signal   : {signals.get('macd_signal', 'N/A')}",
        f"  EMA 20        : {signals.get('ema20', 'N/A')}",
        f"  EMA 50        : {signals.get('ema50', 'N/A')}",
        f"  EMA 200       : {signals.get('ema200', 'N/A')}",
        f"  Trend         : {'UPTREND' if signals.get('price_above_ema50') else 'DOWNTREND'}",
        f"  Volume spike  : {signals.get('vol_spike', False)}",
        f"",
        f"ACTIVE SIGNALS:",
        f"  RSI oversold      : {signals.get('rsi_oversold')}",
        f"  RSI overbought    : {signals.get('rsi_overbought')}",
        f"  MACD bullish cross: {signals.get('macd_bullish_cross')}",
        f"  MACD bearish cross: {signals.get('macd_bearish_cross')}",
        f"  Golden cross      : {signals.get('golden_cross')}",
        f"  Death cross       : {signals.get('death_cross')}",
        f"",
        news_text,
    ]
    return "\n".join(lines)


SYSTEM_PROMPT = """You are a professional stock market analyst specializing in Indian equities (NSE/BSE).
You give clear, concise, actionable advice based on technical indicators, price action and news.
Always mention: current trend, key risk, key opportunity, and a clear recommendation.
Keep responses under 200 words. Be direct — no disclaimers about consulting a financial advisor.
Format: use bullet points for clarity."""


def ask_about_stock(
    ticker: str,
    question: str,
    signals: dict,
    pnl: dict,
    news_text: str,
) -> str:
    """Ask OpenAI a question about a specific stock with full context."""
    if not settings.openai_api_key or settings.openai_api_key == "placeholder":
        return _fallback_analysis(ticker, signals, pnl)

    context = build_stock_context(ticker, signals, pnl, news_text)

    try:
        response = get_client().chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": f"{context}\n\nQuestion: {question}"},
            ],
            max_tokens=300,
            temperature=0.3,
        )
        return response.choices[0].message.content.strip()

    except Exception as e:
        logger.error(f"OpenAI call failed: {e}")
        return _fallback_analysis(ticker, signals, pnl)


def ask_portfolio_question(question: str, portfolio_context: str) -> str:
    """Ask a broad question about the full portfolio."""
    if not settings.openai_api_key or settings.openai_api_key == "placeholder":
        return "OpenAI API key not configured. Add OPENAI_API_KEY to .env"

    try:
        response = get_client().chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": f"{portfolio_context}\n\nQuestion: {question}"},
            ],
            max_tokens=400,
            temperature=0.3,
        )
        return response.choices[0].message.content.strip()

    except Exception as e:
        logger.error(f"OpenAI call failed: {e}")
        return f"AI analysis unavailable: {e}"


def _fallback_analysis(ticker: str, signals: dict, pnl: dict) -> str:
    """Rule-based fallback when OpenAI is not configured."""
    rsi   = signals.get("rsi", 50)
    trend = "uptrend" if signals.get("price_above_ema50") else "downtrend"
    pnl_pct = pnl.get("pnl_pct", 0) or 0
    pnl_str = f"+{pnl_pct:.1f}%" if pnl_pct >= 0 else f"{pnl_pct:.1f}%"

    lines = [f"**{ticker} Analysis** (rule-based, no OpenAI key)", ""]

    if signals.get("rsi_oversold"):
        lines.append("• RSI oversold — potential bounce zone, watch for reversal confirmation")
    elif signals.get("rsi_overbought"):
        lines.append("• RSI overbought — consider taking partial profits")
    else:
        lines.append(f"• RSI {rsi:.1f} — neutral momentum")

    lines.append(f"• Currently in {trend}")
    lines.append(f"• Your position: {pnl_str} unrealised P&L")

    if signals.get("macd_bullish_cross"):
        lines.append("• MACD bullish crossover — momentum turning positive")
    elif signals.get("macd_bearish_cross"):
        lines.append("• MACD bearish crossover — momentum turning negative")

    if pnl_pct < -20:
        lines.append("• Position down >20% — review stop loss levels")
    elif pnl_pct > 50:
        lines.append("• Position up >50% — consider booking partial profits")

    return "\n".join(lines)
