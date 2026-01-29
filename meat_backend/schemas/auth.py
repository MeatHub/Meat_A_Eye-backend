"""인증 API 스키마."""
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=1000)  # 입력 최대 1000자, bcrypt는 72바이트로 자동 잘림
    nickname: str = Field(..., min_length=1, max_length=50)


class RegisterResponse(BaseModel):
    userId: int
    token: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    token: str
    nickname: str
    isGuest: bool = False


class GuestRequest(BaseModel):
    browserSessionId: str = Field(..., description="uuid_v4 from localStorage")
    nickname: str | None = Field(None, max_length=50)


class GuestResponse(BaseModel):
    token: str
    isGuest: bool = True
    nickname: str | None = None


class WebPushKeys(BaseModel):
    p256dh: str
    auth: str


class WebPushSubscribeRequest(BaseModel):
    endpoint: str
    keys: WebPushKeys


class WebPushSubscribeResponse(BaseModel):
    success: bool = True
    savedAt: datetime
