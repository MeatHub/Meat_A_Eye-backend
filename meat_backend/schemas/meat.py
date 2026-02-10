"""육류 시세/정보 API 스키마."""
from pydantic import BaseModel, Field


class MeatPriceResponse(BaseModel):
    currentPrice: int
    unit: str = "100g"
    trend: str  # "up" | "down" | "flat"


class MeatInfoResponse(BaseModel):
    id: int | None = None  # 목록 조회 시 필요
    name: str
    displayName: str | None = None  # UI용 한글 표시명 (예: 소/안심, 돼지/삼겹살)
    category: str | None = None  # beef/pork
    calories: int | None
    protein: float | None
    fat: float | None
    recipes: list[str] = []
    storageGuide: str | None = None


class GradePrice(BaseModel):
    grade: str
    price: int
    unit: str = "100g"
    priceDate: str | None = None
    trend: str = "flat"


class MeatInfoByPartNameResponse(BaseModel):
    """부위명으로 조회한 통합 정보."""
    partName: str
    displayName: str | None = None  # UI용 한글 표시명
    calories: int | None
    protein: float | None
    fat: float | None
    carbohydrate: float | None
    currentPrice: int
    priceUnit: str = "100g"
    priceTrend: str  # "up" | "down" | "flat"
    priceDate: str | None
    priceSource: str  # "api" | "cache" | "fallback" | "unavailable"
    gradePrices: list[GradePrice] = Field(default_factory=list)
    storageGuide: str | None = None
