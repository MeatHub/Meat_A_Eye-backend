"""recipe_bookmarks 테이블 - 레시피 즐겨찾기."""
from datetime import datetime
from sqlalchemy import BigInteger, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..config.database import Base
from ..config.timezone import now_kst


class RecipeBookmark(Base):
    __tablename__ = "recipe_bookmarks"
    __table_args__ = (UniqueConstraint("member_id", "saved_recipe_id", name="uq_recipe_bookmark_member_recipe"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    member_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("members.id", ondelete="CASCADE"), nullable=False)
    saved_recipe_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("saved_recipes.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_kst)

    member = relationship("Member", back_populates="recipe_bookmarks")
    saved_recipe = relationship("SavedRecipe", back_populates="bookmarks")
