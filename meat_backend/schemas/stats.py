"""소비 패턴 통계 API 스키마."""
from datetime import date
from pydantic import BaseModel


class ConsumptionStatsItem(BaseModel):
    date: date
    consumedCount: int
    storedCount: int


class ConsumptionStatsResponse(BaseModel):
    items: list[ConsumptionStatsItem]
    totalConsumed: int
    totalStored: int
