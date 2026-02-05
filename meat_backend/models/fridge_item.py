"""fridge_items 테이블."""
from datetime import date
from sqlalchemy import BigInteger, Integer, Date, String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..config.database import Base


class FridgeItem(Base):
    __tablename__ = "fridge_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    member_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("members.id", ondelete="CASCADE"), nullable=False)
    meat_info_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("meat_info.id"), nullable=True)
    storage_date: Mapped[date] = mapped_column(Date, nullable=False)
    expiry_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="stored")
    # 축산물 이력제 정보
    slaughter_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment="도축일자")
    grade: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="등급")
    trace_number: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="이력번호")
    origin: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="원산지")
    company_name: Mapped[str | None] = mapped_column(String(200), nullable=True, comment="업체명")
    # 사용자 커스터마이징
    custom_name: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="사용자 지정 고기 이름")
    desired_consumption_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment="희망 섭취기간")

    member = relationship("Member", back_populates="fridge_items")
    meat_info = relationship("MeatInfo", back_populates="fridge_items")
    web_notifications = relationship("WebNotification", back_populates="fridge_item")
