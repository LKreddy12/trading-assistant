"""
Quick test — run this after filling in your .env to verify Telegram works.
Usage: python test_telegram.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.config import settings
from app.bot.notifier import send_message

def test():
    print(f"Bot token : {'SET' if settings.telegram_bot_token and settings.telegram_bot_token != 'PASTE_YOUR_BOT_TOKEN_HERE' else 'NOT SET ❌'}")
    print(f"Chat ID   : {'SET' if settings.telegram_chat_id and settings.telegram_chat_id != 'PASTE_YOUR_CHAT_ID_HERE' else 'NOT SET ❌'}")

    if not settings.telegram_bot_token or settings.telegram_bot_token == "PASTE_YOUR_BOT_TOKEN_HERE":
        print("\nFill in .env first, then run again.")
        return

    print("\nSending test message to Telegram...")
    ok = send_message(
        "✅ *Trading Assistant Connected!*\n\n"
        "Your live alert system is working.\n"
        "Watching: NIFTY · BANKNIFTY · SENSEX · TCS · Crude Oil\n\n"
        "Trade signals will arrive here during market hours (9:15 AM – 3:30 PM IST)"
    )
    if ok:
        print("✅ Message sent! Check your Telegram.")
    else:
        print("❌ Failed. Check your token and chat ID.")

if __name__ == "__main__":
    test()
