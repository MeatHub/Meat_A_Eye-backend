"""FRIDGE-01~03: 냉장고 목록(D-Day 정렬), 아이템 추가, 알림 수정."""
from datetime import date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from ...config.database import get_db
from ...models.member import Member
from ...models.fridge_item import FridgeItem
from ...models.meat_info import MeatInfo
from ...schemas.fridge import (
    FridgeListResponse,
    FridgeItemResponse,
    FridgeItemAdd,
    FridgeAlertUpdate,
    FridgeStatusUpdate,
)
from ...middleware.jwt import get_current_user

router = APIRouter()


def _d_day(expiry: date) -> int:
    """오늘 기준 D-Day. 과거면 음수."""
    today = date.today()
    return (expiry - today).days


@router.get(
    "/list",
    response_model=FridgeListResponse,
    summary="FRIDGE-01 냉장고 목록 (유통기한 임박 최상단)",
    responses={
        401: {"description": "토큰 만료 (리프레시 필요)"},
        403: {"description": "접근 권한 없음"},
    },
)
async def fridge_list(
    db: Annotated[AsyncSession, Depends(get_db)],
    member: Annotated[Member, Depends(get_current_user)],
    status_filter: str | None = Query(None, alias="status"),
):
    q = (
        select(FridgeItem)
        .where(FridgeItem.member_id == member.id)
        .options(selectinload(FridgeItem.meat_info))
    )
    if status_filter and status_filter in ("stored", "consumed"):
        q = q.where(FridgeItem.status == status_filter)
    q = q.order_by(FridgeItem.expiry_date.asc())
    result = await db.execute(q)
    rows = result.scalars().all()
    items = []
    for r in rows:
        name = r.meat_info.part_name if r.meat_info else "알 수 없음"
        d = _d_day(r.expiry_date)
        items.append(
            FridgeItemResponse(
                id=r.id,
                name=name,
                dDay=d,
                imgUrl=None,
                status=r.status,
                expiryDate=r.expiry_date,
            )
        )
    # 유통기한 임박(D-Day 작은 것) 우선 → 이미 expiry_date asc로 정렬됨
    return FridgeListResponse(items=items)


@router.post(
    "/item",
    summary="FRIDGE-02 냉장고 아이템 추가",
    responses={
        400: {"description": "날짜 포맷 오류 (YYYY-MM-DD)"},
        422: {"description": "데이터 무결성 위반"},
    },
)
async def fridge_add(
    body: FridgeItemAdd,
    db: Annotated[AsyncSession, Depends(get_db)],
    member: Annotated[Member, Depends(get_current_user)],
):
    if body.expiry_date < body.storage_date:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="만료일은 보관일 이후여야 합니다")
    meat = await db.get(MeatInfo, body.meatId)
    if not meat:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="meat_info 없음")
    item = FridgeItem(
        member_id=member.id,
        meat_info_id=body.meatId,
        storage_date=body.storageDate,
        expiry_date=body.expiryDate,
        status="stored",
    )
    db.add(item)
    await db.flush()
    await db.refresh(item)
    return {"id": item.id, "status": "stored", "alertScheduled": True}


@router.patch(
    "/{item_id}/alert",
    summary="FRIDGE-03 소비기한 알림 수정 (현재 스키마에서는 미지원)",
    responses={
        501: {"description": "Not Implemented - alert_before 컬럼이 없습니다"},
    },
)
async def fridge_alert_update(
    item_id: int,
    body: FridgeAlertUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    member: Annotated[Member, Depends(get_current_user)],
):
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="현재 DB 스키마에는 alert_before, use_web_push 컬럼이 없습니다.",
    )


@router.patch(
    "/{item_id}/status",
    summary="보관 기록 관리 — status=consumed (고기 소비 패턴 그래프용)",
)
async def fridge_status_update(
    item_id: int,
    body: FridgeStatusUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    member: Annotated[Member, Depends(get_current_user)],
):
    if body.status not in ("stored", "consumed"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="status: stored | consumed")
    item = await db.get(FridgeItem, item_id)
    if not item or item.member_id != member.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="아이템 없음")
    item.status = body.status
    await db.flush()
    return {"success": True, "status": item.status}
