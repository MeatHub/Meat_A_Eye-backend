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


class FridgeListResponse(BaseModel):
    items: list[FridgeItemResponse]


class FridgeItemAdd(BaseModel):
    meatId: int
    storageDate: date = Field(..., description="YYYY-MM-DD")
    expiryDate: date = Field(..., description="YYYY-MM-DD")


class FridgeAlertUpdate(BaseModel):
    alertBefore: int | None = None
    useWebPush: bool | None = None


class FridgeStatusUpdate(BaseModel):
    status: str  # "stored" | "consumed"
