"""AI 분석 API 스키마."""
from enum import Enum

from pydantic import BaseModel


class AIMode(str, Enum):
    ocr = "ocr"
    vision = "vision"


class AIAnalyzeResponse(BaseModel):
    partName: str | None = None
    confidence: float | None = None
    historyNo: str | None = None
    raw: dict | None = None
