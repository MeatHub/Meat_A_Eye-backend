from .auth import (
    RegisterRequest,
    RegisterResponse,
    LoginRequest,
    LoginResponse,
    GuestRequest,
    GuestResponse,
    WebPushSubscribeRequest,
    WebPushSubscribeResponse,
)
from .meat import MeatPriceResponse, MeatInfoResponse
from .fridge import FridgeListResponse, FridgeItemAdd, FridgeItemResponse, FridgeAlertUpdate
from .ai import AIMode, AIAnalyzeResponse
from .stats import ConsumptionStatsResponse, ConsumptionStatsItem

__all__ = [
    "RegisterRequest",
    "RegisterResponse",
    "LoginRequest",
    "LoginResponse",
    "GuestRequest",
    "GuestResponse",
    "WebPushSubscribeRequest",
    "WebPushSubscribeResponse",
    "MeatPriceResponse",
    "MeatInfoResponse",
    "FridgeListResponse",
    "FridgeItemAdd",
    "FridgeItemResponse",
    "FridgeAlertUpdate",
    "AIMode",
    "AIAnalyzeResponse",
    "ConsumptionStatsResponse",
    "ConsumptionStatsItem",
]
