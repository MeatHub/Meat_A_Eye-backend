"""AI-01: 육류 AI 분석 요청 (multipart image, ocr/vision)."""
import logging
from datetime import date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, status, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...config.database import get_db
from ...models.member import Member
from ...models.recognition_log import RecognitionLog
from ...models.fridge_item import FridgeItem
from ...models.meat_info import MeatInfo
from ...models.web_notification import WebNotification
from ...schemas.ai import AIAnalyzeResponse, AIMode
from ...services.ai_proxy import AIProxyService
from ...middleware.jwt import get_current_user

router = APIRouter()
ai_proxy = AIProxyService()

MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5MB
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}

logger = logging.getLogger(__name__)


@router.post(
    "/analyze",
    response_model=AIAnalyzeResponse,
    summary="AI-01 육류 AI 분석 요청 (인식일 +3일 자동 냉장고 추가)",
    responses={
        413: {"description": "파일 크기 초과 (5MB 제한)"},
        415: {"description": "지원하지 않는 이미지 포맷"},
        422: {"description": "인식 실패 (재촬영 요망)"},
    },
)
async def ai_analyze(
    image: UploadFile = File(..., alias="image"),
    options: str | None = Form(None),
    auto_add_fridge: bool = Form(True, description="인식 후 자동으로 냉장고에 추가"),
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    member: Annotated[Member, Depends(get_current_user)] = ...,
):
    """AI 분석 후 인식일 기준 +3일로 자동 냉장고 추가."""
    ct = (image.content_type or "").lower()
    if ct and ct not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="지원하지 않는 이미지 포맷 (jpeg/png/webp)")
    try:
        raw = await image.read()
    except Exception as e:
        logger.exception("Image read error: %s", e)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="이미지 읽기 실패")
    if len(raw) > MAX_IMAGE_SIZE:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="파일 크기 초과 (5MB 제한)")

    mode = "vision"
    if options:
        try:
            import json
            opts = json.loads(options) if isinstance(options, str) else options
            t = opts.get("type", "vision")
            if t in ("ocr", "vision"):
                mode = t
        except Exception:
            pass

    filename = image.filename or "image.jpg"
    out = await ai_proxy.analyze(raw, filename=filename, mode=mode)
    if out.get("error"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="인식 실패 (재촬영 요망)")

    part_name = out.get("partName")
    confidence = out.get("confidence", 0.0)

    # recognition_logs에 저장
    recognition_date = datetime.utcnow()
    log = RecognitionLog(
        member_id=member.id,
        image_url=filename,  # 실제로는 업로드된 이미지 URL이어야 함
        part_name=part_name or "unknown",
        confidence_score=confidence,
        browser_agent=None,  # Request에서 가져올 수 있음
    )
    db.add(log)
    await db.flush()

    fridge_item_id = None
    # part_name이 있고 auto_add_fridge가 True면 자동으로 냉장고에 추가 (인식일 +3일)
    if part_name and auto_add_fridge and member:
        meat_result = await db.execute(select(MeatInfo).where(MeatInfo.part_name == part_name).limit(1))
        meat = meat_result.scalar_one_or_none()
        if meat:
            recognition_date_only = recognition_date.date()
            expiry_date = recognition_date_only + timedelta(days=3)  # 인식일 +3일
            fridge_item = FridgeItem(
                member_id=member.id,
                meat_info_id=meat.id,
                storage_date=recognition_date_only,
                expiry_date=expiry_date,
                status="stored",
            )
            db.add(fridge_item)
            await db.flush()
            await db.refresh(fridge_item)
            fridge_item_id = fridge_item.id

            # 유통기한 알림 예약 (3일 후 09:00)
            alert_time = datetime.combine(expiry_date, datetime.min.time().replace(hour=9))
            notification = WebNotification(
                member_id=member.id,
                fridge_item_id=fridge_item_id,
                notification_type="expiry_alert",
                title=f"{part_name} 유통기한 임박",
                body=f"{part_name}의 유통기한이 {expiry_date}입니다.",
                scheduled_at=alert_time,
                status="pending",
            )
            db.add(notification)
            await db.flush()

    return AIAnalyzeResponse(
        partName=part_name,
        confidence=confidence,
        historyNo=out.get("historyNo"),
        raw=out.get("raw"),
    )
