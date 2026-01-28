"""fridge_items 테이블."""
from datetime import date
from sqlalchemy import BigInteger, Integer, Date, String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..config.database import Base


class FridgeItem(Base):
    __tablename__ = "fridge_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    member_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("members.id", ondelete="CASCADE"), nullable=False)
    meat_info_id: Mapped[int] = mapped_column(Integer, ForeignKey("meat_info.id"), nullable=False)
    storage_date: Mapped[date] = mapped_column(Date, nullable=False)
    expiry_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="stored")

    member = relationship("Member", back_populates="fridge_items")
    meat_info = relationship("MeatInfo", back_populates="fridge_items")
    web_notifications = relationship("WebNotification", back_populates="fridge_item")
