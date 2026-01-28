"""JWT 검증 및 게스트 토큰 — localStorage / HttpOnly Cookie 선택 대비."""
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, OAuth2PasswordBearer
from jose import JWTError, jwt
import bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config.settings import settings
from ..config.database import get_db
from ..models.member import Member

security = HTTPBearer(auto_error=False)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def _truncate_to_72_bytes(password: str) -> bytes:
    """비밀번호를 UTF-8 바이트로 변환하고 72바이트로 제한."""
    password_bytes = password.encode('utf-8')
    if len(password_bytes) > 72:
        password_bytes = password_bytes[:72]
        # UTF-8 문자 경계 유지: 마지막 바이트가 continuation byte면 제거
        while len(password_bytes) > 0 and (password_bytes[-1] & 0xC0) == 0x80:
            password_bytes = password_bytes[:-1]
    return password_bytes


def hash_password(password: str) -> str:
    """bcrypt로 비밀번호 해싱 (72바이트 제한 자동 처리)."""
    password_bytes = _truncate_to_72_bytes(password)
    hashed = bcrypt.hashpw(password_bytes, bcrypt.gensalt())
    return hashed.decode('utf-8')


def verify_password(plain: str, hashed: str) -> bool:
    """bcrypt로 비밀번호 검증."""
    try:
        password_bytes = _truncate_to_72_bytes(plain)
        hashed_bytes = hashed.encode('utf-8')
        return bcrypt.checkpw(password_bytes, hashed_bytes)
    except Exception:
        return False


def create_access_token(
    subject: str | int,
    *,
    is_guest: bool = False,
    expires_delta: timedelta | None = None,
) -> str:
    if expires_delta is None:
        delta = (
            timedelta(minutes=settings.jwt_guest_expire_minutes)
            if is_guest
            else timedelta(minutes=settings.jwt_access_expire_minutes)
        )
    else:
        delta = expires_delta
    expire = datetime.utcnow() + delta
    to_encode = {
        "sub": str(subject),
        "exp": expire,
        "iat": datetime.utcnow(),
        "is_guest": is_guest,
    }
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None


async def _get_member_from_token(
    credentials: HTTPAuthorizationCredentials | None,
    db: AsyncSession,
) -> Member | None:
    if not credentials or not credentials.credentials:
        return None
    payload = decode_token(credentials.credentials)
    if not payload or "sub" not in payload:
        return None
    member_id = int(payload["sub"])
    result = await db.execute(select(Member).where(Member.id == member_id))
    member = result.scalar_one_or_none()
    if not member:
        return None
    return member


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Member:
    """인증 필수. 토큰 없거나 만료 시 401."""
    member = await _get_member_from_token(credentials, db)
    if not member:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 토큰 또는 만료됨 (리프레시 필요)",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return member


async def get_current_user_optional(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Member | None:
    """인증 선택. 토큰 없으면 None, 있으면 멤버 반환."""
    return await _get_member_from_token(credentials, db)
