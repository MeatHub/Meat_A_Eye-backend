"""meat_info 테이블."""
from sqlalchemy import Integer, String, Text, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..config.database import Base


class MeatInfo(Base):
    __tablename__ = "meat_info"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    part_name: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    calories: Mapped[int | None] = mapped_column(Integer, nullable=True)
    protein: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    fat: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    storage_guide: Mapped[str | None] = mapped_column(Text, nullable=True)

    fridge_items = relationship("FridgeItem", back_populates="meat_info")
