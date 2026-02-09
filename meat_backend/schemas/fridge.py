"""냉장고 API 스키마."""
from datetime import date
from pydantic import BaseModel, Field


class FridgeItemResponse(BaseModel):
    id: int
    name: str
    dDay: int
    imgUrl: str | None = None
    status: str = "stored"
    expiryDate: date | None = None
    traceNumber: str | None = None
    customName: str | None = None  # 사용자 지정 이름 (있으면 name에 반영, 레시피 LLM 전달용)
    desiredConsumptionDate: date | None = None
    grade: str | None = None  # 이력정보에서 가져온 등급
    meatInfoId: int  # 현재 선택된 고기 부위 ID


class FridgeListResponse(BaseModel):
    items: list[FridgeItemResponse]


class FridgeItemAdd(BaseModel):
    meatId: int
    storageDate: date = Field(..., description="YYYY-MM-DD")
    expiryDate: date = Field(..., description="YYYY-MM-DD")


class FridgeItemFromTraceabilityAdd(BaseModel):
    """이력 조회 결과로 냉장고 추가 (partName 또는 meatId로 meat_info 결정)."""
    partName: str | None = Field(None, description="부위명(수입축산물 품목 등). 없으면 수입육 기본값 사용")
    meatId: int | None = Field(None, description="meat_info ID. partName 없을 때 사용")
    storageDate: date = Field(..., description="YYYY-MM-DD 보관일")
    expiryDate: date = Field(..., description="YYYY-MM-DD 유통기한(권장)")
    traceNumber: str | None = None
    slaughterDate: date | None = None
    origin: str | None = None
    companyName: str | None = None


class FridgeAlertUpdate(BaseModel):
    alertBefore: int | None = None
    useWebPush: bool | None = None


class FridgeStatusUpdate(BaseModel):
    status: str  # "stored" | "consumed"


class FridgeItemUpdate(BaseModel):
    meatInfoId: int | None = None  # 고기 부위 변경
    customName: str | None = None  # 사용자 지정 이름 (레시피 LLM에 전달됨)
    desiredConsumptionDate: date | None = None
