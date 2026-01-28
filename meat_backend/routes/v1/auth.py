"""AUTH-01~04: 회원가입, 로그인, 게스트 체험, 웹 푸시 구독."""
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...config.database import get_db
from ...models.member import Member
from ...models.web_push_subscription import WebPushSubscription
from ...schemas.auth import (
    RegisterRequest,
    RegisterResponse,
    LoginRequest,
    LoginResponse,
    GuestRequest,
    GuestResponse,
    WebPushSubscribeRequest,
    WebPushSubscribeResponse,
)
from ...middleware.jwt import (
    get_current_user,
    hash_password,
    verify_password,
    create_access_token,
)

router = APIRouter()


@router.post(
    "/register",
    response_model=RegisterResponse,
    summary="AUTH-01 회원가입",
    responses={
        400: {"description": "이메일 형식 오류"},
        409: {"description": "중복된 이메일"},
    },
)
async def register(
    body: RegisterRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(Member).where(Member.email == body.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="중복된 이메일")
    member = Member(
        email=body.email,
        password=hash_password(body.password),
        nickname=body.nickname,
    )
    db.add(member)
    await db.flush()
    await db.refresh(member)
    token = create_access_token(member.id, is_guest=False)
    return RegisterResponse(userId=member.id, token=token)


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="AUTH-02 로그인",
    responses={
        401: {"description": "비밀번호 불일치"},
        404: {"description": "계정 없음"},
    },
)
async def login(
    body: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(Member).where(Member.email == body.email))
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="계정 없음")
    if not verify_password(body.password, member.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="비밀번호 불일치")
    await db.flush()
    token = create_access_token(member.id, is_guest=False)
    return LoginResponse(token=token, nickname=member.nickname, isGuest=False)


@router.post(
    "/guest",
    response_model=GuestResponse,
    summary="AUTH-03 게스트 체험 (임시 이메일 생성)",
    responses={500: {"description": "세션 생성 실패"}},
)
async def guest(
    body: GuestRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    # email/password가 NOT NULL이므로 임시 이메일 생성
    import uuid
    nickname = body.nickname or f"Guest_{body.browserSessionId[:8]}"
    temp_email = f"guest_{uuid.uuid4().hex[:12]}@temp.meathub"
    temp_password = hash_password(uuid.uuid4().hex)
    member = Member(
        email=temp_email,
        password=temp_password,
        nickname=nickname,
    )
    db.add(member)
    await db.flush()
    await db.refresh(member)
    token = create_access_token(member.id, is_guest=True)
    return GuestResponse(token=token, isGuest=True, nickname=member.nickname)


@router.post(
    "/web-push",
    response_model=WebPushSubscribeResponse,
    summary="AUTH-04 웹 푸시 구독 저장",
    responses={
        400: {"description": "구독 정보(Keys) 누락"},
        401: {"description": "유효하지 않은 토큰"},
    },
)
async def web_push_subscribe(
    body: WebPushSubscribeRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    member: Annotated[Member, Depends(get_current_user)],
):
    if not body.keys or not body.keys.p256dh or not body.keys.auth:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="구독 정보(Keys) 누락")
    sub = WebPushSubscription(
        member_id=member.id,
        endpoint=body.endpoint,
        p256dh_key=body.keys.p256dh,
        auth_key=body.keys.auth,
    )
    db.add(sub)
    await db.flush()
    return WebPushSubscribeResponse(success=True, savedAt=datetime.utcnow())
