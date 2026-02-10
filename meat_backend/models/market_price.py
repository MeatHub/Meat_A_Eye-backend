"""market_prices, market_price_history (KAMIS 히스토리/대시보드)."""
from datetime import date, datetime
from sqlalchemy import BigInteger, String, Integer, Date, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from ..config.database import Base
from ..config.timezone import now_kst


class MarketPrice(Base):
    __tablename__ = "market_prices"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    part_name: Mapped[str] = mapped_column(String(100), nullable=False)
    current_price: Mapped[int] = mapped_column(Integer, nullable=False)
    price_date: Mapped[date] = mapped_column(Date, nullable=False)
    region: Mapped[str] = mapped_column(String(50), nullable=False)
    grade_code: Mapped[str] = mapped_column(String(10), nullable=False, default="")


class MarketPriceHistory(Base):
    __tablename__ = "market_price_history"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    part_name: Mapped[str] = mapped_column(String(100), nullable=False)
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    price_date: Mapped[date] = mapped_column(Date, nullable=False)
    region: Mapped[str] = mapped_column(String(50), nullable=False)
    source: Mapped[str | None] = mapped_column(String(50), nullable=True, default="KAMIS")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_kst)
