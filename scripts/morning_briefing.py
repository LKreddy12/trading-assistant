"""
Morning briefing — sends full account-aware market briefing to Telegram.
Run at 9:15am or call via scheduler.
"""
import sys, logging
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import init_db, SessionLocal
from app.bot.notifier import send_message
from app.ai.trading_agent import morning_briefing

logging.basicConfig(level=logging.WARNING)

def main():
    init_db()
    db = SessionLocal()
    try:
        print("Generating morning briefing...")
        briefing = morning_briefing(db)
        send_message(briefing)
        print("Morning briefing sent ✅")
        print("\n" + briefing)
    finally:
        db.close()

if __name__ == "__main__":
    main()
