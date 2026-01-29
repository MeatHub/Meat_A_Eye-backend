"""DASH-02 / MY-01~02: 프로필, 활동 히트맵, 소비 패턴 통계."""
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession

from ...config.database import get_db
from ...models.member import Member
from ...models.recognition_log import RecognitionLog
from ...models.fridge_item import FridgeItem
from ...schemas.stats import ConsumptionStatsResponse, ConsumptionStatsItem
from ...middleware.jwt import get_current_user

router = APIRouter()


class ProfileResponse(BaseModel):
    nickname: str
    isGuest: bool
    email: str | None = None


@router.get(
    "/profile",
    response_model=ProfileResponse,
    summary="DASH-02 / MY 프로필 (닉네임, 활동 등급 요약)",
)
async def my_profile(
    db: Annotated[AsyncSession, Depends(get_db)],
    member: Annotated[Member, Depends(get_current_user)],
):
    # 게스트 여부는 이메일이 guest_로 시작하는지로 판단
    is_guest = member.email.startswith("guest_") if member.email else False
    return ProfileResponse(
        nickname=member.nickname,
        isGuest=is_guest,
        email=member.email,
    )


@router.get(
    "/grass",
    summary="MY-02 활동 히트맵 (일자별 인식 이력)",
)
async def my_grass(
    db: Annotated[AsyncSession, Depends(get_db)],
    member: Annotated[Member, Depends(get_current_user)],
):
    q = (
        select(func.date(RecognitionLog.created_at).label("d"), func.count(RecognitionLog.id).label("c"))
        .where(RecognitionLog.member_id == member.id)
        .group_by(func.date(RecognitionLog.created_at))
    )
    result = await db.execute(q)
    rows = result.all()
    return {"items": [{"date": str(r.d), "count": r.c} for r in rows]}


@router.get(
    "/consumption-stats",
    response_model=ConsumptionStatsResponse,
    summary="고기 소비 패턴 통계 (날짜별 stored/consumed 그래프용)",
)
async def consumption_stats(
    db: Annotated[AsyncSession, Depends(get_db)],
    member: Annotated[Member, Depends(get_current_user)],
):
    """날짜별 보관(stored) 및 소비(consumed) 통계."""
    # 날짜별로 stored와 consumed 개수 집계
    q = (
        select(
            FridgeItem.storage_date.label("d"),
            func.sum(case((FridgeItem.status == "consumed", 1), else_=0)).label("consumed"),
            func.sum(case((FridgeItem.status == "stored", 1), else_=0)).label("stored"),
        )
        .where(FridgeItem.member_id == member.id)
        .group_by(FridgeItem.storage_date)
        .order_by(FridgeItem.storage_date.desc())
    )
    result = await db.execute(q)
    rows = result.all()

    items = [
        ConsumptionStatsItem(
            date=r.d,
            consumedCount=int(r.consumed or 0),
            storedCount=int(r.stored or 0),
        )
        for r in rows
    ]

    # 전체 합계
    total_q = (
        select(
            func.sum(case((FridgeItem.status == "consumed", 1), else_=0)).label("total_consumed"),
            func.sum(case((FridgeItem.status == "stored", 1), else_=0)).label("total_stored"),
        )
        .where(FridgeItem.member_id == member.id)
    )
    total_result = await db.execute(total_q)
    total_row = total_result.first()
    total_consumed = int(total_row.total_consumed or 0) if total_row else 0
    total_stored = int(total_row.total_stored or 0) if total_row else 0

    return ConsumptionStatsResponse(
        items=items,
        totalConsumed=total_consumed,
        totalStored=total_stored,
    )
