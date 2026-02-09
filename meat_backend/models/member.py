"""members 테이블."""
from datetime import datetime
from sqlalchemy import BigInteger, String, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..config.database import Base


class Member(Base):
    __tablename__ = "members"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password: Mapped[str] = mapped_column(String(255), nullable=False)
    nickname: Mapped[str] = mapped_column(String(50), nullable=False)
    web_push_subscription: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_guest: Mapped[bool] = mapped_column(default=False, nullable=False)
    guest_id: Mapped[str | None] = mapped_column(String(36), nullable=True, unique=True)  # UUID
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    recognition_logs = relationship("RecognitionLog", back_populates="member", cascade="all, delete-orphan")
    fridge_items = relationship("FridgeItem", back_populates="member", cascade="all, delete-orphan")
    web_notifications = relationship("WebNotification", back_populates="member", cascade="all, delete-orphan")
    saved_recipes = relationship("SavedRecipe", back_populates="member", cascade="all, delete-orphan")
