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
    FridgeItemFromTraceabilityAdd,
    FridgeAlertUpdate,
    FridgeStatusUpdate,
    FridgeItemUpdate,
)
from ...models.web_notification import WebNotification
from ...middleware.jwt import get_current_user, get_current_user_optional

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
    member: Annotated[Member | None, Depends(get_current_user_optional)],
    status_filter: str | None = Query(None, alias="status"),
):
    # 게스트 사용자도 접근 가능하지만, 빈 리스트 반환
    if not member:
        print("=" * 50)
        print(f"🚨 [API INFO] Endpoint: /api/v1/fridge/list")
        print(f"🚨 [DETAILS]: 게스트 모드 또는 인증 없음, 빈 리스트 반환")
        print("=" * 50)
        return FridgeListResponse(items=[])
    
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
        # meat_info_id가 None이면 "부위 선택" 상태
        if r.meat_info_id is None or not r.meat_info:
            base_name = "부위 선택"
            meat_info_id = 0
        else:
            base_name = r.meat_info.part_name
            meat_info_id = r.meat_info_id
        # 사용자가 수정한 이름(custom_name) 우선, 없으면 부위명 (레시피 LLM 전달용)
        name = (r.custom_name or base_name).strip() or base_name
        d = _d_day(r.expiry_date)
        items.append(
            FridgeItemResponse(
                id=r.id,
                name=name,
                dDay=d,
                imgUrl=None,
                status=r.status,
                expiryDate=r.expiry_date,
                traceNumber=r.trace_number,
                customName=r.custom_name,
                desiredConsumptionDate=r.desired_consumption_date,
                grade=r.grade,  # 이력정보에서 가져온 등급
                meatInfoId=meat_info_id,  # NULL이면 0으로 변환
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
    try:
        if body.expiry_date < body.storage_date:
            print("=" * 50)
            print(f"🚨 [REAL ERROR] Endpoint: /api/v1/fridge/item")
            print(f"🚨 [DETAILS]: 날짜 검증 실패 - 만료일({body.expiry_date}) < 보관일({body.storage_date})")
            print("=" * 50)
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="만료일은 보관일 이후여야 합니다")
        meat = await db.get(MeatInfo, body.meatId)
        if not meat:
            print("=" * 50)
            print(f"🚨 [REAL ERROR] Endpoint: /api/v1/fridge/item")
            print(f"🚨 [DETAILS]: meat_info 없음 (meatId: {body.meatId})")
            print("=" * 50)
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="meat_info 없음")
    except HTTPException:
        raise
    except Exception as e:
        print("=" * 50)
        print(f"🚨 [REAL ERROR] Endpoint: /api/v1/fridge/item")
        print(f"🚨 [DETAILS]: 냉장고 추가 실패 - {type(e).__name__}: {str(e)}")
        print("=" * 50)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"냉장고 추가 실패: {str(e)}")
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


@router.post(
    "/item-from-traceability",
    summary="FRIDGE-02b 이력 조회 결과로 냉장고 추가",
    responses={
        400: {"description": "날짜/meat_info 오류"},
        401: {"description": "로그인 필요"},
    },
)
async def fridge_add_from_traceability(
    body: FridgeItemFromTraceabilityAdd,
    db: Annotated[AsyncSession, Depends(get_db)],
    member: Annotated[Member, Depends(get_current_user)],
):
    if body.expiryDate < body.storageDate:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="만료일은 보관일 이후여야 합니다",
        )
    meat = None
    if body.meatId:
        meat = await db.get(MeatInfo, body.meatId)
    if not meat and body.partName:
        # 1. part_name으로 정확히 매칭 시도
        p = (body.partName or "").strip()
        result = await db.execute(
            select(MeatInfo).where(MeatInfo.part_name == p).limit(1)
        )
        meat = result.scalar_one_or_none()
        
        # 2. 정확히 매칭되지 않으면 부분 매칭 시도
        if not meat:
            result = await db.execute(
                select(MeatInfo)
                .where(MeatInfo.part_name.like(f"%{p}%"))
                .order_by(MeatInfo.id)
                .limit(1)
            )
            meat = result.scalar_one_or_none()
    
    # meat_info를 찾지 못해도 냉장고 아이템 추가 (meat_info_id는 None으로 설정)
    # 프론트엔드에서 meatInfoId가 0이면 "부위 선택" 표시
    meat_info_id = meat.id if meat else None
    slaughter_date = body.slaughterDate
    item = FridgeItem(
        member_id=member.id,
        meat_info_id=meat_info_id,  # None 허용
        storage_date=body.storageDate,
        expiry_date=body.expiryDate,
        status="stored",
        slaughter_date=slaughter_date,
        trace_number=body.traceNumber,
        origin=body.origin,
        company_name=body.companyName,
    )
    db.add(item)
    await db.flush()
    await db.refresh(item)
    
    # 알림 생성 (meat_info가 없으면 "고기"로 표시)
    item_name = meat.part_name if meat else "고기"
    alert_time = datetime.combine(body.expiryDate, datetime.min.time().replace(hour=9))
    notif = WebNotification(
        member_id=member.id,
        fridge_item_id=item.id,
        notification_type="expiry_alert",
        title=f"{item_name} 유통기한 임박",
        body=f"{item_name}의 유통기한이 {body.expiryDate}입니다.",
        scheduled_at=alert_time,
        status="pending",
    )
    db.add(notif)
    await db.flush()
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


@router.patch(
    "/{item_id}",
    summary="FRIDGE-04 냉장고 아이템 수정 (고기 부위, 희망 섭취기간)",
    responses={
        404: {"description": "아이템 없음"},
        403: {"description": "접근 권한 없음"},
        422: {"description": "meat_info 없음"},
    },
)
async def fridge_update(
    item_id: int,
    body: FridgeItemUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    member: Annotated[Member, Depends(get_current_user)],
):
    item = await db.get(FridgeItem, item_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="아이템 없음")
    if item.member_id != member.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="접근 권한 없음")
    
    # 고기 부위 변경
    if body.meatInfoId is not None:
        if body.meatInfoId == 0:
            # 0이면 부위 미선택 (NULL로 설정)
            item.meat_info_id = None
        else:
            meat = await db.get(MeatInfo, body.meatInfoId)
            if not meat:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="meat_info 없음"
                )
            item.meat_info_id = body.meatInfoId
    
    # 사용자 지정 이름 변경
    if body.customName is not None:
        item.custom_name = body.customName.strip() or None
    
    # 희망 섭취기간 변경
    if body.desiredConsumptionDate is not None:
        item.desired_consumption_date = body.desiredConsumptionDate
    
    await db.flush()
    await db.refresh(item)
    await db.refresh(item, ["meat_info"])
    
    # 업데이트된 정보 반환 (표시 이름 = custom_name 우선)
    if item.meat_info_id is None or not item.meat_info:
        base_name = "부위 선택"
        meat_info_id = 0
    else:
        base_name = item.meat_info.part_name
        meat_info_id = item.meat_info_id
    name = (item.custom_name or base_name).strip() or base_name
    return {
        "success": True,
        "id": item.id,
        "meatInfoId": meat_info_id,
        "customName": item.custom_name,
        "desiredConsumptionDate": item.desired_consumption_date,
        "name": name,
    }


@router.delete(
    "/{item_id}",
    summary="냉장고 아이템 삭제",
    responses={
        404: {"description": "아이템 없음"},
        403: {"description": "접근 권한 없음"},
    },
)
async def fridge_delete(
    item_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    member: Annotated[Member, Depends(get_current_user)],
):
    item = await db.get(FridgeItem, item_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="아이템 없음")
    if item.member_id != member.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="접근 권한 없음")
    await db.delete(item)
    await db.flush()
    return {"success": True, "message": "아이템이 삭제되었습니다"}
