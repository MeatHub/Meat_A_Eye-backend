"""프론트엔드 호환을 위한 /api 엔드포인트 (Next.js)."""
import logging
from typing import Annotated
from datetime import datetime, timedelta, date

from fastapi import APIRouter, Depends, File, Form, HTTPException, status, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config.database import get_db
from ..config.settings import settings
from ..models.member import Member
from ..models.recognition_log import RecognitionLog
from ..models.fridge_item import FridgeItem
from ..models.meat_info import MeatInfo
from ..models.web_notification import WebNotification
from ..schemas.ai import AIAnalyzeResponse, NutritionInfo, PriceInfo
from ..services.ai_proxy import AIProxyService
from ..services.traceability import fetch_traceability
from ..services.nutrition_service import NutritionService
from ..services.price_service import PriceService
from ..middleware.jwt import get_current_user, get_current_user_optional

nutrition_service = NutritionService()
price_service = PriceService()

router = APIRouter()
ai_proxy = AIProxyService()

MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5MB
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}

logger = logging.getLogger(__name__)

# Mock 응답 모드 (환경 변수로 제어)
USE_MOCK_RESPONSE = settings.debug  # 개발 모드에서만 Mock 사용


def get_mock_response() -> dict:
    """Mock API 응답 (AI 서버가 없을 때 사용)."""
    return {
        "partName": "Beef_Ribeye",
        "confidence": 0.95,
        "historyNo": "TRACE123456789",
        "raw": {
            "status": "success",
            "data": {
                "category": "Beef_Ribeye",
                "probability": 95.0,
                "is_valid": True
            }
        }
    }


@router.post(
    "/analyze",
    response_model=AIAnalyzeResponse,
    summary="AI 이미지 분석 (프론트엔드 호환 엔드포인트)",
    responses={
        413: {"description": "파일 크기 초과 (5MB 제한)"},
        415: {"description": "지원하지 않는 이미지 포맷"},
        422: {"description": "인식 실패 (재촬영 요망)"},
    },
)
async def api_analyze(
    image: UploadFile = File(..., alias="image"),
    mode: str = Form("vision", description="vision 또는 ocr"),
    auto_add_fridge: bool = Form(True, description="인식 후 자동으로 냉장고에 추가"),
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    member: Annotated[Member | None, Depends(get_current_user_optional)] = None,
):
    """
    AI 이미지 분석 엔드포인트 (프론트엔드 호환).
    
    - 인증이 없어도 사용 가능 (게스트 모드)
    - Mock 응답 모드 지원 (개발 환경)
    """
    # Mock 응답 모드 (개발 환경)
    if USE_MOCK_RESPONSE and not settings.ai_server_url:
        logger.info("Mock 응답 모드 사용")
        mock_data = get_mock_response()
        return AIAnalyzeResponse(
            partName=mock_data["partName"],
            confidence=mock_data["confidence"],
            historyNo=mock_data["historyNo"],
            raw=mock_data["raw"],
        )
    
    # 이미지 검증
    ct = (image.content_type or "").lower()
    if ct and ct not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="지원하지 않는 이미지 포맷 (jpeg/png/webp)"
        )
    
    try:
        raw = await image.read()
    except Exception as e:
        logger.exception("Image read error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="이미지 읽기 실패"
        )
    
    if len(raw) > MAX_IMAGE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="파일 크기 초과 (5MB 제한)"
        )

    # mode 검증
    if mode not in ("vision", "ocr"):
        mode = "vision"

    filename = image.filename or "image.jpg"
    
    # AI 서버 호출
    out = await ai_proxy.analyze(raw, filename=filename, mode=mode)
    
    if out.get("error"):
        # Mock 응답으로 폴백 (개발 환경)
        if USE_MOCK_RESPONSE:
            logger.warning(f"AI 서버 오류, Mock 응답 사용: {out.get('error')}")
            mock_data = get_mock_response()
            out = {
                "partName": mock_data["partName"],
                "confidence": mock_data["confidence"],
                "historyNo": mock_data["historyNo"],
                "raw": mock_data["raw"],
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"인식 실패: {out.get('error')}"
            )

    part_name = out.get("partName")
    confidence = out.get("confidence", 0.0)
    history_no = out.get("historyNo")

    # 영양정보 및 가격정보 조회 (부위명이 있는 경우)
    nutrition_info = None
    price_info = None
    if part_name:
        try:
            nutrition_data = await nutrition_service.fetch_nutrition(part_name)
            nutrition_info = NutritionInfo(
                calories=nutrition_data.get("calories"),
                protein=nutrition_data.get("protein"),
                fat=nutrition_data.get("fat"),
                carbohydrate=nutrition_data.get("carbohydrate"),
            )
        except Exception as e:
            logger.exception(f"영양정보 조회 실패: {e}")

        try:
            price_data = await price_service.fetch_current_price(
                part_name=part_name,
                region="seoul",
                db=db,
            )
            price_info = PriceInfo(
                currentPrice=price_data.get("currentPrice", 0),
                priceUnit=price_data.get("unit", "100g"),
                priceTrend=price_data.get("trend", "flat"),
                priceDate=price_data.get("price_date"),
                priceSource=price_data.get("source", "fallback"),
            )
        except Exception as e:
            logger.exception(f"가격정보 조회 실패: {e}")

    # 로그인한 사용자인 경우에만 로그 및 냉장고 저장
    if member:
        # recognition_logs에 저장
        recognition_date = datetime.utcnow()
        log = RecognitionLog(
            member_id=member.id,
            image_url=filename,
            part_name=part_name or "unknown",
            confidence_score=confidence or 0.0,
            browser_agent=None,
        )
        db.add(log)
        await db.flush()

        # 축산물 이력제 API 호출 (historyNo가 있는 경우)
        traceability_data = None
        if history_no:
            try:
                traceability_list = await fetch_traceability(history_no)
                if traceability_list and len(traceability_list) > 0:
                    traceability_data = traceability_list[0]
                    logger.info(f"이력제 정보 조회 성공: {traceability_data}")
            except Exception as e:
                logger.exception(f"이력제 API 호출 실패: {e}")

        # 냉장고에 자동 추가
        fridge_item_id = None
        if part_name and auto_add_fridge:
            meat_result = await db.execute(
                select(MeatInfo).where(MeatInfo.part_name == part_name).limit(1)
            )
            meat = meat_result.scalar_one_or_none()
            if meat:
                recognition_date_only = recognition_date.date()
                expiry_date = recognition_date_only + timedelta(days=3)

                # 이력제 정보에서 도축일자, 등급 추출
                slaughter_date = None
                grade = None
                origin = None
                company_name = None

                if traceability_data:
                    slaughter_date_str = traceability_data.get("slaughterDate")
                    if slaughter_date_str:
                        try:
                            slaughter_date = datetime.strptime(slaughter_date_str, "%Y-%m-%d").date()
                        except (ValueError, TypeError):
                            try:
                                slaughter_date = datetime.strptime(slaughter_date_str[:10], "%Y-%m-%d").date()
                            except (ValueError, TypeError):
                                logger.warning(f"도축일자 파싱 실패: {slaughter_date_str}")

                    grade = traceability_data.get("grade")
                    origin = traceability_data.get("origin")
                    company_name = traceability_data.get("companyName")

                fridge_item = FridgeItem(
                    member_id=member.id,
                    meat_info_id=meat.id,
                    storage_date=recognition_date_only,
                    expiry_date=expiry_date,
                    status="stored",
                    slaughter_date=slaughter_date,
                    grade=grade,
                    trace_number=history_no,
                    origin=origin,
                    company_name=company_name,
                )
                db.add(fridge_item)
                await db.flush()
                await db.refresh(fridge_item)
                fridge_item_id = fridge_item.id

                # 유통기한 알림 예약
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
        historyNo=history_no,
        raw=out.get("raw"),
        nutrition=nutrition_info,
        price=price_info,
    )

