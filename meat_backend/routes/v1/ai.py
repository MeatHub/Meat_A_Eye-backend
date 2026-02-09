"""AI-01: 육류 AI 분석 요청 (multipart image, ocr/vision)."""
import logging
import os
import random
from datetime import date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, status, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ...config.database import get_db
from ...config.settings import settings as app_settings
from ...models.member import Member
from ...models.recognition_log import RecognitionLog
from ...models.fridge_item import FridgeItem
from ...models.meat_info import MeatInfo
from ...models.web_notification import WebNotification
from ...schemas.ai import AIAnalyzeResponse, AIMode, NutritionInfo, PriceInfo, TraceabilityInfo
from ...apis import AIProxyService
from ...services.traceability import fetch_traceability
from ...services.nutrition_service import NutritionService
from ...services.price_service import PriceService
from ...middleware.jwt import get_current_user

router = APIRouter()
ai_proxy = AIProxyService()
nutrition_service = NutritionService()
price_service = PriceService()

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
    history_no = out.get("historyNo")

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

    # 축산물 이력제 API 호출 (historyNo가 있는 경우)
    traceability_data = None
    if history_no:
        try:
            traceability_list = await fetch_traceability(history_no, part_name=part_name)
            if traceability_list and len(traceability_list) > 0:
                traceability_data = traceability_list[0]
                logger.info(f"이력제 정보 조회 성공: {traceability_data}")
        except Exception as e:
            logger.exception(f"이력제 API 호출 실패: {e}")

    # 영양정보 API 호출 (part_name이 있는 경우)
    nutrition_data = None
    if part_name:
        try:
            nutrition_data = await nutrition_service.fetch_nutrition(part_name, db=db)
        except Exception as e:
            logger.exception(f"영양정보 API 호출 실패: {e}")

    # 가격정보 API 호출 (part_name이 있는 경우)
    price_data = None
    if part_name:
        try:
            price_data = await price_service.fetch_current_price(part_name=part_name, region="seoul", db=db)
        except Exception as e:
            logger.exception(f"가격정보 API 호출 실패: {e}")

    fridge_item_id = None
    # part_name이 있고 auto_add_fridge가 True면 자동으로 냉장고에 추가 (인식일 +3일)
    if part_name and auto_add_fridge and member:
        meat_result = await db.execute(select(MeatInfo).where(MeatInfo.part_name == part_name).limit(1))
        meat = meat_result.scalar_one_or_none()
        if meat:
            recognition_date_only = recognition_date.date()
            expiry_date = recognition_date_only + timedelta(days=3)
            if traceability_data and traceability_data.get("recommendedExpiry"):
                try:
                    expiry_date = datetime.strptime(str(traceability_data.get("recommendedExpiry"))[:10], "%Y-%m-%d").date()
                except (ValueError, TypeError):
                    pass

            # 이력제 정보에서 도축일자, 등급 추출
            slaughter_date = None
            grade = None
            origin = None
            company_name = None
            
            if traceability_data:
                slaughter_date_str = traceability_data.get("slaughterDate") or traceability_data.get("slaughterDateFrom")
                if slaughter_date_str:
                    try:
                        slaughter_date = datetime.strptime(slaughter_date_str, "%Y-%m-%d").date()
                    except (ValueError, TypeError):
                        try:
                            # 다른 형식 시도
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

    # AIAnalyzeResponse 스키마로 4개 API 데이터 통합
    nutrition_info = None
    if nutrition_data:
        nutrition_info = NutritionInfo(
            calories=nutrition_data.get("calories"),
            protein=nutrition_data.get("protein"),
            fat=nutrition_data.get("fat"),
            carbohydrate=nutrition_data.get("carbohydrate"),
            source=nutrition_data.get("source", "api"),
        )

    price_info = None
    if price_data:
        price_info = PriceInfo(
            currentPrice=price_data.get("currentPrice", 0),
            priceUnit=price_data.get("unit", "100g"),
            priceTrend=price_data.get("trend", "flat"),
            priceDate=price_data.get("price_date"),
            priceSource=price_data.get("source", "api"),
            gradePrices=price_data.get("gradePrices", []),
        )

    traceability_info = None
    if traceability_data:
        traceability_info = TraceabilityInfo(
            historyNo=traceability_data.get("historyNo") or history_no,
            blNo=traceability_data.get("blNo"),
            partName=traceability_data.get("partName"),
            origin=traceability_data.get("origin"),
            slaughterDate=traceability_data.get("slaughterDate"),
            slaughterDateFrom=traceability_data.get("slaughterDateFrom"),
            slaughterDateTo=traceability_data.get("slaughterDateTo"),
            processingDateFrom=traceability_data.get("processingDateFrom"),
            processingDateTo=traceability_data.get("processingDateTo"),
            exporter=traceability_data.get("exporter"),
            importer=traceability_data.get("importer"),
            importDate=traceability_data.get("importDate"),
            partCode=traceability_data.get("partCode"),
            companyName=traceability_data.get("companyName"),
            recommendedExpiry=traceability_data.get("recommendedExpiry"),
            limitFromDt=traceability_data.get("limitFromDt"),
            limitToDt=traceability_data.get("limitToDt"),
            refrigCnvrsAt=traceability_data.get("refrigCnvrsAt"),
            refrigDistbPdBeginDe=traceability_data.get("refrigDistbPdBeginDe"),
            refrigDistbPdEndDe=traceability_data.get("refrigDistbPdEndDe"),
            birth_date=traceability_data.get("birth_date"),
            grade=traceability_data.get("grade"),
            source=traceability_data.get("source", "api"),
        )

    return AIAnalyzeResponse(
        partName=part_name,
        confidence=confidence,
        historyNo=history_no,
        heatmap_image=out.get("heatmap_image"),
        raw=out.get("raw"),
        nutrition=nutrition_info,
        price=price_info,
        traceability=traceability_info,
    )


class LLMRecipeRequest(BaseModel):
    fridgeItems: list[dict] = []


class LLMRecipeResponse(BaseModel):
    recipe: str


class RecipeForPartRequest(BaseModel):
    partName: str


def _call_llm_recipe(prompt: str, fallback_meat_str: str) -> str:
    """Gemini(Flash)로 레시피 생성. .env의 GEMINI_API_KEY 사용."""
    gemini_api_key = (app_settings.gemini_api_key or "").strip()
    if not gemini_api_key:
        return (
            f"# 고기 레시피 추천\n\n{fallback_meat_str}\n\n"
            "레시피를 생성하려면 .env에 GEMINI_API_KEY를 설정해주세요."
        )
    try:
        import google.generativeai as genai
        genai.configure(api_key=gemini_api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(
            "당신은 전문 요리사입니다. 한국어로 레시피를 작성해주세요.\n\n" + prompt
        )
        return (response.text or "").strip()
    except Exception as e:
        logger.warning("Gemini 레시피 생성 실패: %s", e)
        return (
            f"# 레시피 추천\n\n{fallback_meat_str}\n\n레시피 생성 중 오류가 발생했습니다."
        )


@router.post(
    "/recipe",
    response_model=LLMRecipeResponse,
    summary="LLM 레시피 생성 (냉장고 고기 기반)",
    responses={
        401: {"description": "인증 필요"},
    },
)
async def generate_recipe(
    body: LLMRecipeRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    member: Annotated[Member, Depends(get_current_user)],
):
    """현재 냉장고의 고기 리스트를 기반으로 LLM 레시피 생성"""
    try:
        # 냉장고 아이템 가져오기
        q = (
            select(FridgeItem)
            .where(FridgeItem.member_id == member.id)
            .where(FridgeItem.status == "stored")
            .options(selectinload(FridgeItem.meat_info))
        )
        result = await db.execute(q)
        items = result.scalars().all()
        
        # 고기 부위 리스트 추출 (사용자 수정 이름 custom_name 우선, 레시피 LLM 전달용)
        meat_parts = []
        for item in items:
            display_name = (item.custom_name or (item.meat_info.part_name if item.meat_info else "고기")).strip() or (item.meat_info.part_name if item.meat_info else "고기")
            meat_parts.append(display_name)
        
        if not meat_parts:
            print("=" * 50)
            print(f"🚨 [REAL ERROR] Endpoint: /api/v1/ai/recipe")
            print(f"🚨 [DETAILS]: 냉장고에 고기 없음 (member_id: {member.id})")
            print("=" * 50)
            return LLMRecipeResponse(
                recipe="# 레시피 추천\n\n현재 냉장고에 보관 중인 고기가 없습니다. 고기를 추가한 후 다시 시도해주세요."
            )
    except Exception as e:
        print("=" * 50)
        print(f"🚨 [REAL ERROR] Endpoint: /api/v1/ai/recipe")
        print(f"🚨 [DETAILS]: DB 조회 실패 - {type(e).__name__}: {str(e)}")
        print("=" * 50)
        logger.exception(f"냉장고 조회 실패: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"냉장고 조회 실패: {str(e)}")
    
    meat_list_str = ", ".join(meat_parts)
    prompt = f"""현재 냉장고에 있는 고기 부위: {meat_list_str}

이 고기들로 만들 수 있는 맛있는 레시피를 추천해주세요. 
다음 형식으로 작성해주세요:

# 레시피 이름

## 재료
- 재료 목록

## 조리법
1. 첫 번째 단계
2. 두 번째 단계
...

## 팁
- 조리 팁이나 주의사항

한국어로 작성해주세요."""
    recipe_text = _call_llm_recipe(prompt, f"현재 냉장고에 있는 고기: {meat_list_str}")
    if not recipe_text.strip():
        recipe_text = f"# 고기 레시피 추천\n\n현재 냉장고에 있는 고기: {meat_list_str}\n\n맛있게 드세요! 🥩"
    return LLMRecipeResponse(recipe=recipe_text)


@router.post(
    "/recipe-for-part",
    response_model=LLMRecipeResponse,
    summary="이 부위 레시피 추천 (분석한 부위 1개)",
)
async def recipe_for_part(
    body: RecipeForPartRequest,
):
    """분석한 고기 부위(partName) 하나로 레시피 생성. 인증 없이 호출 가능."""
    part_name = (body.partName or "").strip()
    if not part_name:
        return LLMRecipeResponse(
            recipe="# 레시피 추천\n\n부위명이 없습니다. 먼저 고기 부위를 분석해주세요."
        )
    prompt = f"""다음 고기 부위로 만드는 레시피 하나를 추천해주세요.

부위: {part_name}

다음 형식으로 작성해주세요:

# 레시피 이름

## 재료
- 재료 목록

## 조리법
1. 첫 번째 단계
2. 두 번째 단계
...

## 팁
- 조리 팁이나 주의사항

한국어로 작성해주세요."""
    fallback = f"부위: {part_name}"
    recipe_text = _call_llm_recipe(prompt, fallback)
    if not recipe_text.strip():
        recipe_text = f"# {part_name} 레시피\n\n부위: {part_name}\n\n레시피를 생성하려면 .env에 GEMINI_API_KEY를 설정해주세요."
    return LLMRecipeResponse(recipe=recipe_text)


@router.post(
    "/recipe-random",
    response_model=LLMRecipeResponse,
    summary="랜덤 레시피 (냉장고에서 랜덤 1부위)",
    responses={401: {"description": "인증 필요"}},
)
async def recipe_random(
    db: Annotated[AsyncSession, Depends(get_db)],
    member: Annotated[Member, Depends(get_current_user)],
):
    """냉장고 보관 중인 고기 중 랜덤 1개를 골라 그 부위로 레시피 생성."""
    q = (
        select(FridgeItem)
        .where(FridgeItem.member_id == member.id)
        .where(FridgeItem.status == "stored")
        .options(selectinload(FridgeItem.meat_info))
    )
    result = await db.execute(q)
    items = result.scalars().all()
    if not items:
        return LLMRecipeResponse(
            recipe="# 랜덤 레시피\n\n냉장고에 보관 중인 고기가 없습니다. 고기를 추가한 후 다시 시도해주세요."
        )
    item = random.choice(items)
    display_name = (item.custom_name or (item.meat_info.part_name if item.meat_info else "고기")).strip() or (item.meat_info.part_name if item.meat_info else "고기")
    prompt = f"""다음 고기 부위로 만드는 레시피 하나를 다양한 스타일(한식/양식/일식/퓨전 등)으로 추천해주세요.

부위: {display_name}

다음 형식으로 작성해주세요:

# 레시피 이름

## 재료
- 재료 목록

## 조리법
1. 첫 번째 단계
2. 두 번째 단계
...

## 팁
- 조리 팁이나 주의사항

한국어로 작성해주세요."""
    fallback = f"부위: {display_name}"
    recipe_text = _call_llm_recipe(prompt, fallback)
    if not recipe_text.strip():
        recipe_text = f"# {display_name} 레시피\n\n부위: {display_name}\n\n레시피를 생성하려면 .env에 GEMINI_API_KEY를 설정해주세요."
    return LLMRecipeResponse(recipe=recipe_text)
