from sqlalchemy import Column, Integer, String, Float, DateTime, UniqueConstraint
from sqlalchemy.sql import func
from app.database import Base


class StockPrice(Base):
    __tablename__ = "stock_prices"

    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String, nullable=False, index=True)
    date = Column(DateTime, nullable=False, index=True)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    volume = Column(Float)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("ticker", "date", name="uq_ticker_date"),
    )

    def __repr__(self):
        return f"<StockPrice {self.ticker} {self.date:%Y-%m-%d} close={self.close}>"


class Portfolio(Base):
    __tablename__ = "portfolio"

    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String, nullable=False, unique=True, index=True)
    shares = Column(Float, nullable=False)
    avg_buy_price = Column(Float, nullable=False)
    notes = Column(String, default="")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<Portfolio {self.ticker} x{self.shares} @ {self.avg_buy_price}>"
