from pydantic_settings import BaseSettings
from pydantic import Field
from typing import List


class Settings(BaseSettings):
    openai_api_key: str = Field(default="", env="OPENAI_API_KEY")
    telegram_bot_token: str = Field(default="", env="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str = Field(default="", env="TELEGRAM_CHAT_ID")
    news_api_key: str = Field(default="", env="NEWS_API_KEY")
    db_path: str = Field(default="data/trading.db", env="DB_PATH")
    watchlist_raw: str = Field(
        default="RELIANCE.NS,TCS.NS,INFY.NS", env="WATCHLIST"
    )
    kite_api_key: str = Field(default="", env="KITE_API_KEY")
    kite_api_secret: str = Field(default="", env="KITE_API_SECRET")
    kite_access_token: str = Field(default="", env="KITE_ACCESS_TOKEN")

    @property
    def watchlist(self) -> List[str]:
        return [s.strip() for s in self.watchlist_raw.split(",") if s.strip()]

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
