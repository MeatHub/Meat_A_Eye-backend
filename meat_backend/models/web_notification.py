"""web_notifications — 웹 푸시 알림 상태 관리."""
from datetime import datetime
from sqlalchemy import BigInteger, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..config.database import Base
from ..config.timezone import now_kst


class WebNotification(Base):
    __tablename__ = "web_notifications"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    member_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("members.id", ondelete="CASCADE"), nullable=False)
    fridge_item_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("fridge_items.id", ondelete="SET NULL"), nullable=True)
    notification_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_kst)

    member = relationship("Member", back_populates="web_notifications")
    fridge_item = relationship("FridgeItem", back_populates="web_notifications")
