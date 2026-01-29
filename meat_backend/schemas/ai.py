"""AI 분석 API 스키마."""
from enum import Enum

from pydantic import BaseModel


class AIMode(str, Enum):
    ocr = "ocr"
    vision = "vision"


class NutritionInfo(BaseModel):
    calories: int | None = None
    protein: float | None = None
    fat: float | None = None
    carbohydrate: float | None = None


class PriceInfo(BaseModel):
    currentPrice: int = 0
    priceUnit: str = "100g"
    priceTrend: str = "flat"
    priceDate: str | None = None
    priceSource: str = "fallback"


class AIAnalyzeResponse(BaseModel):
    partName: str | None = None
    confidence: float | None = None
    historyNo: str | None = None
    raw: dict | None = None
    nutrition: NutritionInfo | None = None  # 영양정보
    price: PriceInfo | None = None  # 가격정보
