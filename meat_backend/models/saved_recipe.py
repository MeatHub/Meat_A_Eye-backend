"""saved_recipes 테이블."""
from datetime import datetime
from sqlalchemy import BigInteger, String, Text, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..config.database import Base
from ..config.timezone import now_kst
import enum


class RecipeSource(str, enum.Enum):
    """레시피 출처"""
    AI_RANDOM = "ai_random"  # AI로 아무 고기로 생성
    FRIDGE_RANDOM = "fridge_random"  # 냉장고 기반 랜덤
    FRIDGE_MULTI = "fridge_multi"  # 냉장고 여러 고기로 생성
    PART_SPECIFIC = "part_specific"  # 특정 부위로 생성


class SavedRecipe(Base):
    __tablename__ = "saved_recipes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    member_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("members.id", ondelete="CASCADE"), nullable=False)
    
    # 레시피 정보
    title: Mapped[str] = mapped_column(String(200), nullable=False, comment="레시피 제목")
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="레시피 내용 (마크다운)")
    source: Mapped[RecipeSource] = mapped_column(SQLEnum(RecipeSource, native_enum=False), nullable=False, comment="레시피 출처")
    
    # 사용된 고기 정보 (JSON 문자열로 저장)
    used_meats: Mapped[str | None] = mapped_column(Text, nullable=True, comment="사용된 고기 목록 (JSON)")
    
    # 메타 정보
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_kst)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_kst, onupdate=now_kst)

    member = relationship("Member", back_populates="saved_recipes")
