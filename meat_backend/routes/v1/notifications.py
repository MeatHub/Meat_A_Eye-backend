"""웹 푸시 알림 상태 관리 API."""
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ...config.database import get_db
from ...models.member import Member
from ...models.web_notification import WebNotification
from ...middleware.jwt import get_current_user

router = APIRouter()


class NotificationResponse(BaseModel):
    id: int
    notificationType: str
    title: str
    body: str
    scheduledAt: datetime
    sentAt: datetime | None
    status: str
    fridgeItemId: int | None = None


class NotificationListResponse(BaseModel):
    items: list[NotificationResponse]
    pendingCount: int
    sentCount: int


@router.get(
    "/list",
    response_model=NotificationListResponse,
    summary="알림 목록 조회 (상태별 필터링)",
)
async def notification_list(
    db: Annotated[AsyncSession, Depends(get_db)],
    member: Annotated[Member, Depends(get_current_user)],
    status_filter: str | None = Query(None, alias="status"),
):
    """웹 푸시 알림 목록 (pending, sent, failed 필터 가능)."""
    q = select(WebNotification).where(WebNotification.member_id == member.id)
    if status_filter and status_filter in ("pending", "sent", "failed"):
        q = q.where(WebNotification.status == status_filter)
    q = q.order_by(WebNotification.scheduled_at.asc())
    result = await db.execute(q)
    rows = result.scalars().all()

    items = [
        NotificationResponse(
            id=r.id,
            notificationType=r.notification_type,
            title=r.title,
            body=r.body,
            scheduledAt=r.scheduled_at,
            sentAt=r.sent_at,
            status=r.status,
            fridgeItemId=r.fridge_item_id,
        )
        for r in rows
    ]

    # 통계
    stats_q = (
        select(
            WebNotification.status,
            func.count(WebNotification.id).label("cnt"),
        )
        .where(WebNotification.member_id == member.id)
        .group_by(WebNotification.status)
    )
    stats_result = await db.execute(stats_q)
    stats_rows = stats_result.all()
    pending_count = sum(r.cnt for r in stats_rows if r.status == "pending")
    sent_count = sum(r.cnt for r in stats_rows if r.status == "sent")

    return NotificationListResponse(
        items=items,
        pendingCount=pending_count,
        sentCount=sent_count,
    )
