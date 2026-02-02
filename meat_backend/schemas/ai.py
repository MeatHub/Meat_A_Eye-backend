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


class TraceabilityInfo(BaseModel):
    birth_date: str | None = None
    slaughterDate: str | None = None
    grade: str | None = None
    origin: str | None = None
    partName: str | None = None
    companyName: str | None = None
    historyNo: str | None = None
    source: str = "fallback"


class AIAnalyzeResponse(BaseModel):
    partName: str | None = None
    confidence: float | None = None
    historyNo: str | None = None
    heatmap_image: str | None = None  # Grad-CAM base64 (data:image/jpeg;base64,...)
    raw: dict | None = None
    nutrition: NutritionInfo | None = None
    price: PriceInfo | None = None
    traceability: TraceabilityInfo | None = None
