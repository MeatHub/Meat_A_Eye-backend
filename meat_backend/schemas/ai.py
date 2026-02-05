"""AI 분석 API 스키마."""
from enum import Enum

from pydantic import BaseModel, Field


class AIMode(str, Enum):
    ocr = "ocr"
    vision = "vision"


class NutritionInfo(BaseModel):
    calories: int | None = None
    protein: float | None = None
    fat: float | None = None
    carbohydrate: float | None = None
    source: str = "api"  # "api" | "cache" | "error"
    grade: str | None = None  # 등급 정보 (예: "1++등급", "1+등급", "1등급", "2등급", "3등급", "일반")


class NutritionInfoBySubpart(BaseModel):
    """세부부위별 영양정보"""
    subpart: str  # 예: "토시살", "참갈비", "기본"
    nutrition: NutritionInfo


class NutritionInfoByGrade(BaseModel):
    """등급별 영양정보"""
    grade: str
    nutrition: NutritionInfo  # 기본값 (첫 번째 세부부위)
    bySubpart: list[NutritionInfoBySubpart] = Field(default_factory=list)  # 세부부위별 영양정보


class GradePrice(BaseModel):
    grade: str
    price: int
    unit: str = "100g"
    priceDate: str | None = None
    trend: str = "flat"


class PriceInfo(BaseModel):
    currentPrice: int = 0
    priceUnit: str = "100g"
    priceTrend: str = "flat"
    priceDate: str | None = None
    priceSource: str = "fallback"
    gradePrices: list[GradePrice] = Field(default_factory=list)


class TraceabilityInfo(BaseModel):
    """이력제 상세 (실제 사이트와 동일 4개 섹션 구성용)."""
    # 기본정보
    historyNo: str | None = None
    blNo: str | None = None  # 선하증권번호
    partName: str | None = None  # 수입축산물 품목
    # 원산지정보
    origin: str | None = None  # 원산지(국가)
    # 수입이력정보
    slaughterDate: str | None = None  # 도축일자 (단일)
    slaughterDateFrom: str | None = None
    slaughterDateTo: str | None = None  # 수출국 도축일자 범위
    processingDateFrom: str | None = None
    processingDateTo: str | None = None  # 수출국 가공일자
    exporter: str | None = None  # 수출업체 (butchNm/senderNm)
    importer: str | None = None  # 수입업체 (receiverNm)
    importDate: str | None = None  # 수입연월일 (applyDt)
    partCode: str | None = None  # 부위(코드) regnNm/regnCode
    companyName: str | None = None  # 가공업체(prcssNm)
    # 유통기한·냉장고 연동
    recommendedExpiry: str | None = None  # 유통기한(권장) limitToDt/limitFromDt
    limitFromDt: str | None = None
    limitToDt: str | None = None
    # 냉동전환정보
    refrigCnvrsAt: str | None = None  # 냉동전환 여부 Y/N
    refrigDistbPdBeginDe: str | None = None
    refrigDistbPdEndDe: str | None = None  # 냉장소비기한
    # 기타
    birth_date: str | None = None
    grade: str | None = None
    source: str = "api"
    server_maintenance: bool = False


class AIAnalyzeResponse(BaseModel):
    partName: str | None = None
    confidence: float | None = None
    historyNo: str | None = None
    heatmap_image: str | None = None  # Grad-CAM base64 (data:image/jpeg;base64,...)
    raw: dict | None = None
    nutrition: NutritionInfo | None = None
    nutritionByGrade: list[NutritionInfoByGrade] | None = None  # 등급별 영양정보
    price: PriceInfo | None = None
    traceability: TraceabilityInfo | None = None
