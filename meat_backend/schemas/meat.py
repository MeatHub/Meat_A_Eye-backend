"""육류 시세/정보 API 스키마."""
from pydantic import BaseModel


class MeatPriceResponse(BaseModel):
    currentPrice: int
    unit: str = "100g"
    trend: str  # "up" | "down" | "flat"


class MeatInfoResponse(BaseModel):
    name: str
    calories: int | None
    protein: float | None
    fat: float | None
    recipes: list[str] = []
    storageGuide: str | None = None
