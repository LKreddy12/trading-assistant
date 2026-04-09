"""
Zerodha Kite integration.
Handles login, token management, portfolio sync, F&O positions.
"""
import logging
import os
from pathlib import Path
from kiteconnect import KiteConnect
from app.config import settings

logger = logging.getLogger(__name__)

TOKEN_FILE = Path("data/kite_token.txt")


def get_kite() -> KiteConnect:
    """Return an authenticated KiteConnect instance."""
    kite = KiteConnect(api_key=settings.kite_api_key)
    token = _load_token()
    if token:
        kite.set_access_token(token)
    return kite


def _load_token() -> str | None:
    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text().strip()
    if settings.kite_access_token:
        return settings.kite_access_token
    return None


def _save_token(token: str):
    TOKEN_FILE.parent.mkdir(exist_ok=True)
    TOKEN_FILE.write_text(token)
    logger.info("Kite access token saved")


def get_login_url() -> str:
    kite = KiteConnect(api_key=settings.kite_api_key)
    return kite.login_url()


def complete_login(request_token: str) -> str:
    """
    Exchange request token for access token.
    Call this once after redirect from Kite login.
    Returns access token.
    """
    kite = KiteConnect(api_key=settings.kite_api_key)
    data = kite.generate_session(request_token, api_secret=settings.kite_api_secret)
    access_token = data["access_token"]
    _save_token(access_token)
    logger.info(f"Kite login successful for {data.get('user_name', 'user')}")
    return access_token


def is_authenticated() -> bool:
    token = _load_token()
    if not token:
        return False
    try:
        kite = get_kite()
        kite.profile()
        return True
    except Exception:
        return False


def get_profile() -> dict:
    return get_kite().profile()


def get_holdings() -> list:
    """
    Fetch all equity holdings from Kite.
    Returns list of holdings with quantity, avg price, current value etc.
    """
    try:
        holdings = get_kite().holdings()
        return [
            {
                "ticker":         h["tradingsymbol"] + ".NS",
                "shares":         h["quantity"],
                "avg_buy_price":  h["average_price"],
                "ltp":            h["last_price"],
                "current_value":  h["quantity"] * h["last_price"],
                "invested":       h["quantity"] * h["average_price"],
                "pnl":            h["pnl"],
                "pnl_pct":        round((h["pnl"] / (h["quantity"] * h["average_price"])) * 100, 2)
                                  if h["average_price"] > 0 else 0,
                "exchange":       h["exchange"],
                "isin":           h.get("isin", ""),
            }
            for h in holdings
            if h["quantity"] > 0
        ]
    except Exception as e:
        logger.error(f"Failed to fetch holdings: {e}")
        return []


def get_positions() -> dict:
    """
    Fetch current day + net F&O and equity positions.
    """
    try:
        pos = get_kite().positions()
        return {
            "day": pos.get("day", []),
            "net": pos.get("net", []),
        }
    except Exception as e:
        logger.error(f"Failed to fetch positions: {e}")
        return {"day": [], "net": []}


def get_fno_positions() -> list:
    """Filter only F&O positions from net positions."""
    positions = get_positions()
    fno = []
    for p in positions.get("net", []):
        if p.get("product") in ("NRML", "MIS") and p.get("quantity") != 0:
            fno.append({
                "symbol":       p["tradingsymbol"],
                "exchange":     p["exchange"],
                "product":      p["product"],
                "quantity":     p["quantity"],
                "avg_price":    p["average_price"],
                "ltp":          p["last_price"],
                "pnl":          p["pnl"],
                "instrument":   p.get("instrument_token"),
            })
    return fno


def get_orders() -> list:
    """Recent order history."""
    try:
        return get_kite().orders()
    except Exception as e:
        logger.error(f"Failed to fetch orders: {e}")
        return []


def get_quote(symbols: list) -> dict:
    """
    Get live quotes for a list of symbols.
    symbols format: ["NSE:RELIANCE", "NSE:TCS", "MCX:GOLDM25JANFUT"]
    """
    try:
        return get_kite().quote(symbols)
    except Exception as e:
        logger.error(f"Quote fetch failed: {e}")
        return {}
