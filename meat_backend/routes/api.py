"""프론트엔드 호환을 위한 /api 엔드포인트 (Next.js)."""
import asyncio
import logging
from typing import Annotated
from datetime import datetime, timedelta, date

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, status, UploadFile, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config.database import get_db
from ..config.settings import settings
from ..config.timezone import now_kst
from ..models.member import Member
from ..models.recognition_log import RecognitionLog
from ..models.fridge_item import FridgeItem
from ..models.meat_info import MeatInfo
from ..models.web_notification import WebNotification
from ..schemas.ai import AIAnalyzeResponse, NutritionInfo, NutritionInfoByGrade, NutritionInfoBySubpart, PriceInfo, TraceabilityInfo
from ..apis import AIProxyService
from ..services.traceability_service import TraceabilityService
from ..services.nutrition_service import NutritionService
from ..services.price_service import PriceService
from ..middleware.jwt import get_current_user, get_current_user_optional, hash_password

nutrition_service = NutritionService()
price_service = PriceService()
traceability_service = TraceabilityService()

router = APIRouter()
ai_proxy = AIProxyService()

MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5MB
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}

logger = logging.getLogger(__name__)


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
    request: Request,
    image: UploadFile = File(..., alias="image"),
    mode: str = Form("vision", description="vision 또는 ocr"),
    auto_add_fridge: bool = Form(True, description="인식 후 자동으로 냉장고에 추가"),
    guest_id: str | None = Form(None, description="게스트 세션 ID (게스트 모드용)"),
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    member: Annotated[Member | None, Depends(get_current_user_optional)] = None,
):
    """
    AI 이미지 분석 엔드포인트 (프론트엔드 호환).
    
    - 인증이 없어도 사용 가능 (게스트 모드)
    - 실제 API만 사용 (더미 데이터 제거)
    """
    # AI 서버 URL 확인
    if not settings.ai_server_url:
        print("=" * 50)
        print(f"🚨 [REAL ERROR] Endpoint: {request.url}")
        print(f"🚨 [DETAILS]: AI 서버 URL이 설정되지 않음 (AI_SERVER_URL)")
        print("=" * 50)
        logger.error("AI 서버 URL이 설정되지 않음 (AI_SERVER_URL)")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI 서버가 설정되지 않았습니다."
        )
    
    # 이미지 검증
    ct = (image.content_type or "").lower()
    if ct and ct not in ALLOWED_CONTENT_TYPES:
        print("=" * 50)
        print(f"🚨 [REAL ERROR] Endpoint: {request.url}")
        print(f"🚨 [DETAILS]: 지원하지 않는 이미지 포맷 - {ct}")
        print("=" * 50)
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="지원하지 않는 이미지 포맷 (jpeg/png/webp)"
        )
    
    try:
        raw = await image.read()
    except Exception as e:
        print("=" * 50)
        print(f"🚨 [REAL ERROR] Endpoint: {request.url}")
        print(f"🚨 [DETAILS]: {str(e)}")
        print("=" * 50)
        logger.exception("Image read error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="이미지 읽기 실패"
        )
    
    if len(raw) > MAX_IMAGE_SIZE:
        print("=" * 50)
        print(f"🚨 [REAL ERROR] Endpoint: {request.url}")
        print(f"🚨 [DETAILS]: 파일 크기 초과 - {len(raw)} bytes (최대 {MAX_IMAGE_SIZE} bytes)")
        print("=" * 50)
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="파일 크기 초과 (5MB 제한)"
        )

    # mode 검증
    if mode not in ("vision", "ocr"):
        mode = "vision"

    filename = image.filename or "image.jpg"
    
    # AI 서버 호출
    try:
        out = await ai_proxy.analyze(raw, filename=filename, mode=mode)
    except HTTPException:
        raise
    except Exception as e:
        print("=" * 50)
        print(f"🚨 [REAL ERROR] Endpoint: {request.url}")
        print(f"🚨 [DETAILS]: AI 서버 호출 실패 - {type(e).__name__}: {str(e)}")
        print("=" * 50)
        logger.exception(f"AI 서버 호출 실패: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI 서버 연결 실패: {str(e)}"
        )
    
    if out.get("error"):
        error_msg = out.get('error', 'Unknown error')
        print("=" * 50)
        print(f"🚨 [REAL ERROR] Endpoint: {request.url}")
        print(f"🚨 [DETAILS]: AI 서버 응답 오류 - {error_msg}")
        print("=" * 50)
        logger.error(f"AI 서버 응답 오류: {error_msg}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"인식 실패: {error_msg}"
        )

    part_name = out.get("partName")
    confidence = out.get("confidence", 0.0)
    history_no = out.get("historyNo")
    heatmap_image = out.get("heatmap_image")

    # 4개 공공 API 병렬 호출 (asyncio.gather)
    async def _fetch_nutrition() -> NutritionInfo | None:
        if not part_name:
            return None
        try:
            data = await nutrition_service.fetch_nutrition(part_name, db=db)
            # 새로운 구조: by_grade와 default 지원
            if "by_grade" in data:
                # 등급별 데이터가 있으면 첫 번째 등급 사용 (또는 가장 높은 등급)
                default_data = data.get("default", {})
            else:
                # 기존 구조 (하위 호환성)
                default_data = data
            
            return NutritionInfo(
                calories=default_data.get("calories"),
                protein=default_data.get("protein"),
                fat=default_data.get("fat"),
                carbohydrate=default_data.get("carbohydrate"),
                source=default_data.get("source", "api"),
                grade=default_data.get("grade"),
            )
        except HTTPException as e:
            print("=" * 50)
            print(f"🚨 [REAL ERROR] Endpoint: {request.url}")
            print(f"🚨 [DETAILS]: 영양정보 {e.status_code} (부위: {part_name}) - {e.detail}")
            print("=" * 50)
            logger.exception("영양정보 조회 실패: %s", e.detail)
            return None
        except Exception as e:
            print("=" * 50)
            print(f"🚨 [REAL ERROR] Endpoint: {request.url}")
            print(f"🚨 [DETAILS]: 영양정보 {type(e).__name__} (부위: {part_name}) - {str(e)}")
            print("=" * 50)
            logger.exception("영양정보 조회 실패: %s", e)
            return None

    async def _fetch_price() -> PriceInfo | None:
        if not part_name:
            return None
        try:
            data = await price_service.fetch_current_price(
                part_name=part_name,
                region="seoul",
                db=db,
            )
            return PriceInfo(
                currentPrice=data.get("currentPrice", 0),
                priceUnit=data.get("unit", "100g"),
                priceTrend=data.get("trend", "flat"),
                priceDate=data.get("price_date"),
                priceSource=data.get("source", "api"),
                gradePrices=data.get("gradePrices", []),
            )
        except httpx.TimeoutException as e:
            print("=" * 50)
            print(f"🚨 [REAL ERROR] Endpoint: {request.url}")
            print(f"🚨 [DETAILS]: 가격정보 API Timeout (부위: {part_name}) - {str(e)}")
            print("=" * 50)
            logger.exception("가격정보 API Timeout: %s", e)
            return None
        except httpx.HTTPStatusError as e:
            print("=" * 50)
            print(f"🚨 [REAL ERROR] Endpoint: {request.url}")
            print(f"🚨 [DETAILS]: 가격정보 API HTTP {e.response.status_code} (부위: {part_name}) - {str(e)}")
            print("=" * 50)
            logger.exception("가격정보 API HTTP Error: %s", e)
            return None
        except Exception as e:
            print("=" * 50)
            print(f"🚨 [REAL ERROR] Endpoint: {request.url}")
            print(f"🚨 [DETAILS]: 가격정보 API {type(e).__name__} (부위: {part_name}) - {str(e)}")
            print("=" * 50)
            logger.exception("가격정보 조회 실패: %s", e)
            return None

    async def _fetch_traceability() -> TraceabilityInfo | None:
        if not history_no:
            return None
        try:
            data = await traceability_service.fetch_traceability(history_no, part_name=part_name)
            if data:
                return TraceabilityInfo(
                    historyNo=data.get("historyNo"),
                    blNo=data.get("blNo"),
                    partName=data.get("partName"),
                    origin=data.get("origin"),
                    slaughterDate=data.get("slaughterDate"),
                    slaughterDateFrom=data.get("slaughterDateFrom"),
                    slaughterDateTo=data.get("slaughterDateTo"),
                    processingDateFrom=data.get("processingDateFrom"),
                    processingDateTo=data.get("processingDateTo"),
                    exporter=data.get("exporter"),
                    importer=data.get("importer"),
                    importDate=data.get("importDate"),
                    partCode=data.get("partCode"),
                    companyName=data.get("companyName"),
                    recommendedExpiry=data.get("recommendedExpiry"),
                    limitFromDt=data.get("limitFromDt"),
                    limitToDt=data.get("limitToDt"),
                    refrigCnvrsAt=data.get("refrigCnvrsAt"),
                    refrigDistbPdBeginDe=data.get("refrigDistbPdBeginDe"),
                    refrigDistbPdEndDe=data.get("refrigDistbPdEndDe"),
                    birth_date=data.get("birth_date"),
                    grade=data.get("grade"),
                    source=data.get("source", "api"),
                    server_maintenance=data.get("server_maintenance", False),
                )
        except HTTPException as e:
            # HTML 응답 등으로 인한 HTTPException은 조용히 실패 (OCR은 성공했으므로 계속 진행)
            print("=" * 50)
            print(f"⚠️ [WARNING] Endpoint: {request.url}")
            print(f"⚠️ [DETAILS]: 이력제 API HTTPException (이력번호: {history_no}) - {e.detail}")
            print("=" * 50)
            logger.warning("이력제 조회 실패 (계속 진행): %s", e.detail)
        except httpx.TimeoutException as e:
            print("=" * 50)
            print(f"⚠️ [WARNING] Endpoint: {request.url}")
            print(f"⚠️ [DETAILS]: 이력제 API Timeout (이력번호: {history_no}) - {str(e)}")
            print("=" * 50)
            logger.warning("이력제 API Timeout (계속 진행): %s", e)
        except httpx.HTTPStatusError as e:
            print("=" * 50)
            print(f"⚠️ [WARNING] Endpoint: {request.url}")
            print(f"⚠️ [DETAILS]: 이력제 API HTTP {e.response.status_code} (이력번호: {history_no}) - {str(e)}")
            print("=" * 50)
            logger.warning("이력제 API HTTP Error (계속 진행): %s", e)
        except Exception as e:
            print("=" * 50)
            print(f"⚠️ [WARNING] Endpoint: {request.url}")
            print(f"⚠️ [DETAILS]: 이력제 API {type(e).__name__} (이력번호: {history_no}) - {str(e)}")
            print("=" * 50)
            logger.warning("이력제 조회 실패 (계속 진행): %s", e)
        return None

    nutrition_info, price_info, traceability_info = await asyncio.gather(
        _fetch_nutrition(),
        _fetch_price(),
        _fetch_traceability(),
    )
    
    # 등급별 + 세부부위별 영양정보 조회
    nutrition_by_grade: list[NutritionInfoByGrade] | None = None
    if part_name:
        try:
            nutrition_data = await nutrition_service.fetch_nutrition(part_name, db=db)
            if "by_grade" in nutrition_data and nutrition_data["by_grade"]:
                nutrition_by_grade = []
                for item in nutrition_data["by_grade"]:
                    # 세부부위별 영양정보 변환
                    by_subpart_list = []
                    if "by_subpart" in item and item["by_subpart"]:
                        for subpart_item in item["by_subpart"]:
                            by_subpart_list.append(
                                NutritionInfoBySubpart(
                                    subpart=subpart_item.get("subpart", "기본"),
                                    nutrition=NutritionInfo(
                                        calories=subpart_item["nutrition"].get("calories"),
                                        protein=subpart_item["nutrition"].get("protein"),
                                        fat=subpart_item["nutrition"].get("fat"),
                                        carbohydrate=subpart_item["nutrition"].get("carbohydrate"),
                                        source=subpart_item["nutrition"].get("source", "api"),
                                        grade=subpart_item["nutrition"].get("grade"),
                                    ),
                                )
                            )
                    
                    # 등급별 영양정보 (기본값 + 세부부위 목록)
                    nutrition_by_grade.append(
                        NutritionInfoByGrade(
                            grade=item["grade"],
                            nutrition=NutritionInfo(
                                calories=item["nutrition"].get("calories"),
                                protein=item["nutrition"].get("protein"),
                                fat=item["nutrition"].get("fat"),
                                carbohydrate=item["nutrition"].get("carbohydrate"),
                                source=item["nutrition"].get("source", "api"),
                                grade=item["nutrition"].get("grade"),
                            ),
                            bySubpart=by_subpart_list,
                        )
                    )
                print(f"✅ 등급별 영양정보 변환 완료: {part_name} (등급 {len(nutrition_by_grade)}개, 총 세부부위 {sum(len(g.bySubpart) for g in nutrition_by_grade)}개)")
        except Exception as e:
            print(f"🚨 [REAL ERROR] 등급별 영양정보 조회 실패: {e}")
            logger.warning(f"등급별 영양정보 조회 실패: {e}")

    # 게스트 모드: guest_id가 있으면 게스트 멤버 찾기 또는 생성
    if not member and guest_id:
        result = await db.execute(
            select(Member).where(Member.guest_id == guest_id).limit(1)
        )
        member = result.scalar_one_or_none()
        if not member:
            # 게스트 계정 생성
            import uuid
            temp_email = f"guest_{uuid.uuid4().hex[:12]}@temp.meathub"
            temp_password = hash_password(uuid.uuid4().hex)
            member = Member(
                email=temp_email,
                password=temp_password,
                nickname=f"Guest_{guest_id[:8]}",
                is_guest=True,
                guest_id=guest_id,
            )
            db.add(member)
            await db.flush()
            await db.refresh(member)

    # 로그인한 사용자 또는 게스트인 경우 로그 및 냉장고 저장
    if member:
        # recognition_logs에 저장
        recognition_date = now_kst()
        log = RecognitionLog(
            member_id=member.id,
            image_url=filename,
            part_name=part_name or "unknown",
            confidence_score=confidence or 0.0,
            browser_agent=None,
        )
        db.add(log)
        await db.flush()

        # 냉장고에 자동 추가 (이력제는 이미 병렬로 조회됨)
        fridge_item_id = None
        if auto_add_fridge and member:
            meat = None
            if part_name:
                meat_result = await db.execute(
                    select(MeatInfo).where(MeatInfo.part_name == part_name).limit(1)
                )
                meat = meat_result.scalar_one_or_none()
            if not meat and traceability_info and getattr(traceability_info, "partName", None):
                # OCR만 이력번호만 반환한 경우: 이력 품목명으로 meat_info 결정
                p = (traceability_info.partName or "").strip()
                
                # 1. part_name으로 정확히 매칭 시도
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
            recognition_date_only = recognition_date.date()
            expiry_date = recognition_date_only + timedelta(days=3)
            if traceability_info and getattr(traceability_info, "recommendedExpiry", None):
                try:
                    expiry_date = datetime.strptime(
                        str(traceability_info.recommendedExpiry)[:10], "%Y-%m-%d"
                    ).date()
                except (ValueError, TypeError):
                    pass

            slaughter_date = None
            grade = None
            origin = None
            company_name = None
            if traceability_info:
                slaughter_date_str = getattr(traceability_info, "slaughterDate", None) or getattr(traceability_info, "slaughterDateFrom", None)
                if slaughter_date_str:
                    try:
                        slaughter_date = datetime.strptime(slaughter_date_str, "%Y-%m-%d").date()
                    except (ValueError, TypeError):
                        try:
                            slaughter_date = datetime.strptime(str(slaughter_date_str)[:10], "%Y-%m-%d").date()
                        except (ValueError, TypeError):
                            logger.warning("도축일자 파싱 실패: %s", slaughter_date_str)
                grade = traceability_info.grade
                origin = traceability_info.origin
                company_name = traceability_info.companyName

            fridge_item = FridgeItem(
                member_id=member.id,
                meat_info_id=meat_info_id,  # None 허용
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

            # 유통기한 알림 예약 (meat_info가 없으면 "고기"로 표시)
            item_name = meat.part_name if meat else "고기"
            alert_time = datetime.combine(expiry_date, datetime.min.time().replace(hour=9))
            notification = WebNotification(
                member_id=member.id,
                fridge_item_id=fridge_item_id,
                notification_type="expiry_alert",
                title=f"{item_name} 유통기한 임박",
                body=f"{item_name}의 유통기한이 {expiry_date}입니다.",
                scheduled_at=alert_time,
                status="pending",
            )
            db.add(notification)
            await db.flush()

    return AIAnalyzeResponse(
        partName=part_name,
        confidence=confidence,
        historyNo=history_no,
        heatmap_image=heatmap_image,
        raw=out.get("raw"),
        nutrition=nutrition_info,
        nutritionByGrade=nutrition_by_grade,
        price=price_info,
        traceability=traceability_info,
    )
