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


class MeatInfoByPartNameResponse(BaseModel):
    """부위명으로 조회한 통합 정보."""
    partName: str
    calories: int | None
    protein: float | None
    fat: float | None
    carbohydrate: float | None
    currentPrice: int
    priceUnit: str = "100g"
    priceTrend: str  # "up" | "down" | "flat"
    priceDate: str | None
    priceSource: str  # "api" | "cache" | "fallback"
    storageGuide: str | None = None
