"""AI-01: 육류 AI 분석 요청 (multipart image, ocr/vision)."""
import logging
import os
import random
from datetime import date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, status, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ...config.database import get_db
from ...config.settings import settings as app_settings
from ...config.timezone import now_kst
from ...models.member import Member
from ...models.recognition_log import RecognitionLog
from ...models.fridge_item import FridgeItem
from ...models.meat_info import MeatInfo
from ...models.web_notification import WebNotification
from ...models.saved_recipe import SavedRecipe, RecipeSource
from ...models.recipe_bookmark import RecipeBookmark
from ...schemas.ai import AIAnalyzeResponse, AIMode, NutritionInfo, PriceInfo, TraceabilityInfo
from ...apis import AIProxyService
from ...apis import get_part_display_name
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
    recognition_date = now_kst()
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
            price_data = await price_service.fetch_current_price(part_name=part_name, region="전국", grade_code="00", db=db)
            logger.info("가격정보 조회 성공: part=%s, price=%s", part_name, price_data.get("currentPrice") if price_data else None)
        except Exception as e:
            logger.warning("가격정보 API 호출 실패 (part=%s): %s", part_name, e)

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


class SaveRecipeRequest(BaseModel):
    title: str
    content: str
    source: str  # RecipeSource enum 값
    used_meats: str | None = None  # JSON 문자열


class SavedRecipeResponse(BaseModel):
    id: int
    title: str
    content: str
    source: str
    used_meats: str | None
    created_at: datetime
    updated_at: datetime
    is_bookmarked: bool = False


class BookmarkedIdsResponse(BaseModel):
    bookmarked_ids: list[int]


class RecipeListResponse(BaseModel):
    recipes: list[SavedRecipeResponse]


def _call_llm_recipe(prompt: str, fallback_meat_str: str) -> str:
    """Gemini(Flash)로 레시피 생성. .env의 GEMINI_API_KEY 사용."""
    gemini_api_key = (app_settings.gemini_api_key or "").strip()
    if not gemini_api_key:
        return (
            f"# 고기 레시피 추천\n\n{fallback_meat_str}\n\n"
            "레시피를 생성하려면 .env에 GEMINI_API_KEY를 설정해주세요."
        )
    try:
        from google import genai
        
        client = genai.Client(api_key=gemini_api_key)
        # 간결하고 요약된 레시피를 생성하도록 시스템 프롬프트 설정 (영어로 작성하여 번역 시간 단축)
        system_prompt = """You are a creative professional chef. Write diverse, unique, and concise recipes in Korean.
- Create VARIETY: Avoid repetitive recipes like "steak" - suggest different cooking styles (Korean, Western, Japanese, Chinese, fusion, etc.)
- Use diverse cooking methods: grilling, stir-frying, braising, stewing, frying, steaming, etc.
- Skip unnecessary explanations or long introductions
- Recipe title: Write ONLY in Korean. DO NOT include English translation in parentheses or brackets. Example: "돼지 등심 사과 처트니 구이" (NOT "돼지 등심 사과 처트니 구이 (Pan-Seared Pork Loin with Apple Chutney)")
- List COMPLETE ingredients with SPECIFIC AMOUNTS: For each recipe, include ALL ingredients needed:
  * Main meat: Include amount, thickness, and preparation method (e.g., "돼지 등심 스테이크용(약 2cm 두께) 300~400g")
  * Marinade/Seasoning: List ALL marinade ingredients with amounts (e.g., "소금, 후추, 올리브오일 약간")
  * Sauce ingredients: If recipe name includes a sauce (caramel, teriyaki, doubanjiang, etc.), you MUST list ALL sauce ingredients with specific amounts. Example: "캐러멜 소스: 설탕 2큰술, 버터 1큰술, 오렌지 1개(즙을 냄), 디종 머스터드 1작은술, 레몬즙 1작은술, 다진 마늘 1/2작은술"
  * Vegetables: Include all vegetables with amounts
  * Spices and aromatics: Include garlic, ginger, etc. with amounts
  CRITICAL: DO NOT skip any ingredients. If the recipe name mentions a sauce or specific flavor, you MUST include ALL ingredients for that sauce/flavor with specific amounts.
- Summarize cooking steps in 3-5 steps
- Provide only 1-2 simple tips
- Keep the overall length short and easy to read
- Be creative and suggest unique recipes each time
- Write ALL section headers in Korean: "재료", "조리 방법", "팁" (NOT "재료 (Ingredients)", "Cooking Steps", etc.)
Write the entire response in Korean only, without any English translations."""
        
        full_prompt = system_prompt + "\n\n" + prompt
        
        # 모델 이름: models/ 접두사 없이 사용
        # max_output_tokens을 충분히 설정하여 레시피가 잘리지 않도록 함
        from google.genai import types
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=full_prompt,
            config=types.GenerateContentConfig(
                max_output_tokens=3000,  # 최대 3000 토큰으로 설정하여 전체 레시피(제목, 재료, 조리방법, 팁)가 완전히 생성되도록 함
                temperature=0.95,  # 다양성을 높이기 위해 temperature 증가 (0.7 -> 0.95)
            )
        )
        
        # 1. response.text 속성 우선 확인 (가장 간단)
        if hasattr(response, 'text') and response.text:
            return response.text.strip()
        
        # 2. candidates를 통한 추출 (테스트에서 확인한 방식)
        if hasattr(response, 'candidates') and response.candidates:
            candidate = response.candidates[0]
            if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                # parts는 리스트이고, 각 part는 text 속성을 가짐
                text_parts = [part.text for part in candidate.content.parts if hasattr(part, 'text') and part.text]
                if text_parts:
                    return "\n".join(text_parts).strip()
        
        return (
            f"# 레시피 추천\n\n{fallback_meat_str}\n\n레시피 생성 중 응답 형식 오류가 발생했습니다."
        )
    except Exception as e:
        error_str = str(e)
        logger.warning("Gemini 레시피 생성 실패: %s", e)
        logger.exception("상세 오류:")
        
        # 429 에러 (할당량 초과) 처리
        if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str or "quota" in error_str.lower():
            raise HTTPException(
                status_code=429,
                detail="API 사용량 한도를 초과했습니다. 잠시 후 다시 시도해주세요.",
            )
        else:
            raise HTTPException(
                status_code=502,
                detail="레시피 생성에 실패했습니다. 다시 시도해주세요.",
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
            logger.warning(f"냉장고에 고기 없음 (member_id: {member.id})")
            return LLMRecipeResponse(
                recipe="# 레시피 추천\n\n현재 냉장고에 보관 중인 고기가 없습니다. 고기를 추가한 후 다시 시도해주세요."
            )
    except Exception as e:
        logger.exception(f"냉장고 조회 실패: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"냉장고 조회 실패: {str(e)}")
    
    meat_list_str = ", ".join(meat_parts)
    prompt = f"""Meat parts currently in the refrigerator: {meat_list_str}

Recommend one creative and diverse recipe that can be made with these meats.
**CRITICAL LANGUAGE RULE: Write EVERYTHING in Korean ONLY. DO NOT include any English translations, especially in recipe titles. Recipe title should be Korean only, like "돼지 등심 사과 처트니 구이" - NOT "돼지 등심 사과 처트니 구이 (Pan-Seared Pork Loin with Apple Chutney)".**
**CRITICAL: Create VARIETY - avoid common recipes like "steak". Suggest unique cooking styles: Korean (bulgogi, galbi, bossam), Western (stew, pasta, casserole), Japanese (teriyaki, sukiyaki), Chinese (stir-fry, braised), fusion, etc. Use diverse cooking methods: grilling, stir-frying, braising, stewing, frying, steaming, etc.**
**Important: Write concisely. Cooking steps: summarize in 3-5 steps.**
**CRITICAL for Ingredients: Include ALL necessary ingredients with SPECIFIC AMOUNTS. The recipe name must match the ingredients list.**
**Example format (Korean style):**
- 주재료: 돼지 등심 스테이크용(약 2cm 두께) 300~400g
- 밑간: 소금, 후추, 올리브오일 약간
- 캐러멜 소스: 설탕 2큰술, 버터 1큰술, 오렌지 1개(즙을 냄 또는 오렌지 마말레이드 2큰술), 디종 머스터드 1작은술(생략 가능), 레몬즙 또는 식초 1작은술, 다진 마늘 1/2작은술
**DO NOT skip ingredients. If the recipe name mentions a sauce (caramel, teriyaki, doubanjiang, etc.) or specific flavor, you MUST include ALL ingredients for that sauce/flavor with specific amounts.**

Write in the following format (ALL in Korean, NO English):

# 돼지 등심 사과 처트니 구이

## 재료
주재료: 돼지 등심 스테이크용(약 2cm 두께) 300~400g
밑간: 소금, 후추, 올리브오일 약간
사과 처트니 소스: 사과 1개(작게 다짐), 양파 1/2개(다짐), 설탕 2큰술, 식초 1큰술, 생강 1작은술(다짐), 계피가루 약간
채소: 감자 2개, 당근 1개
기타: 버터 1큰술, 다진 마늘 1작은술

## 조리 방법
1. 돼지 등심에 소금, 후추, 올리브오일을 발라 30분 재워둡니다.
2. 사과 처트니 소스를 만들기 위해 사과, 양파, 설탕, 식초, 생강을 넣고 약한 불에서 졸입니다.
3. 팬에 버터를 녹이고 돼지 등심을 앞뒤로 노릇하게 굽습니다.
4. 구운 고기를 접시에 담고 사과 처트니 소스를 올려 완성합니다.

## 팁
- 고기를 너무 오래 구우면 질겨지니 중간 불에서 빠르게 구워주세요.

CRITICAL FORMATTING RULES:
1. Recipe title: Write ONLY in Korean. Example: "# 돼지 등심 사과 처트니 구이" - DO NOT add English like "(Pan-Seared Pork Loin with Apple Chutney)"
2. Section headers: Use ONLY Korean - "## 재료", "## 조리 방법", "## 팁" - NOT "재료 (Ingredients)" or "Cooking Steps"
3. Write ALL content in Korean only - no English translations anywhere
4. Follow the exact format above with all sections: 재료, 조리 방법, 팁"""
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
    prompt = f"""Recommend one creative and diverse recipe using the following meat part.

Meat part: {part_name}

**CRITICAL LANGUAGE RULE: Write EVERYTHING in Korean ONLY. DO NOT include any English translations, especially in recipe titles. Recipe title should be Korean only, like "돼지 등심 사과 처트니 구이" - NOT "돼지 등심 사과 처트니 구이 (Pan-Seared Pork Loin with Apple Chutney)".**
**CRITICAL: Create VARIETY - avoid common recipes like "steak". Suggest unique cooking styles: Korean (bulgogi, galbi, bossam, jeyuk bokkeum), Western (stew, pasta, casserole, roast), Japanese (teriyaki, sukiyaki, yakitori), Chinese (stir-fry, braised, mapo), fusion, etc. Use diverse cooking methods: grilling, stir-frying, braising, stewing, frying, steaming, etc.**
**Important: Write concisely. Cooking steps: summarize in 3-5 steps.**
**CRITICAL for Ingredients: Include ALL necessary ingredients with SPECIFIC AMOUNTS. The recipe name must match the ingredients list.**
**Example format (Korean style):**
- 주재료: 돼지 등심 스테이크용(약 2cm 두께) 300~400g
- 밑간: 소금, 후추, 올리브오일 약간
- 캐러멜 소스: 설탕 2큰술, 버터 1큰술, 오렌지 1개(즙을 냄 또는 오렌지 마말레이드 2큰술), 디종 머스터드 1작은술(생략 가능), 레몬즙 또는 식초 1작은술, 다진 마늘 1/2작은술
**DO NOT skip ingredients. If the recipe name mentions a sauce (caramel, teriyaki, doubanjiang, etc.) or specific flavor, you MUST include ALL ingredients for that sauce/flavor with specific amounts.**

Write in the following format (ALL in Korean, NO English):

# 돼지 등심 사과 처트니 구이

## 재료
주재료: 돼지 등심 스테이크용(약 2cm 두께) 300~400g
밑간: 소금, 후추, 올리브오일 약간
사과 처트니 소스: 사과 1개(작게 다짐), 양파 1/2개(다짐), 설탕 2큰술, 식초 1큰술, 생강 1작은술(다짐), 계피가루 약간
채소: 감자 2개, 당근 1개
기타: 버터 1큰술, 다진 마늘 1작은술

## 조리 방법
1. 돼지 등심에 소금, 후추, 올리브오일을 발라 30분 재워둡니다.
2. 사과 처트니 소스를 만들기 위해 사과, 양파, 설탕, 식초, 생강을 넣고 약한 불에서 졸입니다.
3. 팬에 버터를 녹이고 돼지 등심을 앞뒤로 노릇하게 굽습니다.
4. 구운 고기를 접시에 담고 사과 처트니 소스를 올려 완성합니다.

## 팁
- 고기를 너무 오래 구우면 질겨지니 중간 불에서 빠르게 구워주세요.

CRITICAL FORMATTING RULES:
1. Recipe title: Write ONLY in Korean. Example: "# 돼지 등심 사과 처트니 구이" - DO NOT add English like "(Pan-Seared Pork Loin with Apple Chutney)"
2. Section headers: Use ONLY Korean - "## 재료", "## 조리 방법", "## 팁" - NOT "재료 (Ingredients)" or "Cooking Steps"
3. Write ALL content in Korean only - no English translations anywhere
4. Follow the exact format above with all sections: 재료, 조리 방법, 팁"""
    display_name = get_part_display_name(part_name) or part_name
    fallback = f"부위: {display_name}"
    recipe_text = _call_llm_recipe(prompt, fallback)
    if not recipe_text.strip():
        recipe_text = f"# {display_name} 레시피\n\n부위: {display_name}\n\n레시피를 생성하려면 .env에 GEMINI_API_KEY를 설정해주세요."
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
    meat_type: str | None = Body(None, embed=True, description="beef 또는 pork 필터"),
):
    """냉장고 보관 중인 고기 중 랜덤 1개를 골라 그 부위로 레시피 생성."""
    q = (
        select(FridgeItem)
        .where(FridgeItem.member_id == member.id)
        .where(FridgeItem.status == "stored")
        .options(selectinload(FridgeItem.meat_info))
    )
    # meat_type 필터 적용
    if meat_type and meat_type in ("beef", "pork"):
        q = q.join(FridgeItem.meat_info).where(MeatInfo.category == meat_type)
    result = await db.execute(q)
    items = result.scalars().all()
    if not items:
        type_label = {"beef": "소고기", "pork": "돼지고기"}.get(meat_type or "", "고기")
        return LLMRecipeResponse(
            recipe=f"# 랜덤 레시피\n\n냉장고에 보관 중인 {type_label}가 없습니다. 고기를 추가한 후 다시 시도해주세요."
        )
    item = random.choice(items)
    display_name = (item.custom_name or (item.meat_info.part_name if item.meat_info else "고기")).strip() or (item.meat_info.part_name if item.meat_info else "고기")
    prompt = f"""Recommend one creative and diverse recipe using the following meat part.

Meat part: {display_name}

**CRITICAL LANGUAGE RULE: Write EVERYTHING in Korean ONLY. DO NOT include any English translations, especially in recipe titles. Recipe title should be Korean only, like "돼지 등심 사과 처트니 구이" - NOT "돼지 등심 사과 처트니 구이 (Pan-Seared Pork Loin with Apple Chutney)".**
**CRITICAL: Create VARIETY - avoid common recipes like "steak". Suggest unique cooking styles: Korean (bulgogi, galbi, bossam, jeyuk bokkeum), Western (stew, pasta, casserole, roast), Japanese (teriyaki, sukiyaki, yakitori), Chinese (stir-fry, braised, mapo), fusion, etc. Use diverse cooking methods: grilling, stir-frying, braising, stewing, frying, steaming, etc.**
**Important: Write concisely. Cooking steps: summarize in 3-5 steps.**
**CRITICAL for Ingredients: Include ALL necessary ingredients with SPECIFIC AMOUNTS. The recipe name must match the ingredients list.**
**Example format (Korean style):**
- 주재료: 돼지 등심 스테이크용(약 2cm 두께) 300~400g
- 밑간: 소금, 후추, 올리브오일 약간
- 캐러멜 소스: 설탕 2큰술, 버터 1큰술, 오렌지 1개(즙을 냄 또는 오렌지 마말레이드 2큰술), 디종 머스터드 1작은술(생략 가능), 레몬즙 또는 식초 1작은술, 다진 마늘 1/2작은술
**DO NOT skip ingredients. If the recipe name mentions a sauce (caramel, teriyaki, doubanjiang, etc.) or specific flavor, you MUST include ALL ingredients for that sauce/flavor with specific amounts.**

Write in the following format (ALL in Korean, NO English):

# 돼지 등심 사과 처트니 구이

## 재료
주재료: 돼지 등심 스테이크용(약 2cm 두께) 300~400g
밑간: 소금, 후추, 올리브오일 약간
사과 처트니 소스: 사과 1개(작게 다짐), 양파 1/2개(다짐), 설탕 2큰술, 식초 1큰술, 생강 1작은술(다짐), 계피가루 약간
채소: 감자 2개, 당근 1개
기타: 버터 1큰술, 다진 마늘 1작은술

## 조리 방법
1. 돼지 등심에 소금, 후추, 올리브오일을 발라 30분 재워둡니다.
2. 사과 처트니 소스를 만들기 위해 사과, 양파, 설탕, 식초, 생강을 넣고 약한 불에서 졸입니다.
3. 팬에 버터를 녹이고 돼지 등심을 앞뒤로 노릇하게 굽습니다.
4. 구운 고기를 접시에 담고 사과 처트니 소스를 올려 완성합니다.

## 팁
- 고기를 너무 오래 구우면 질겨지니 중간 불에서 빠르게 구워주세요.

CRITICAL FORMATTING RULES:
1. Recipe title: Write ONLY in Korean. Example: "# 돼지 등심 사과 처트니 구이" - DO NOT add English like "(Pan-Seared Pork Loin with Apple Chutney)"
2. Section headers: Use ONLY Korean - "## 재료", "## 조리 방법", "## 팁" - NOT "재료 (Ingredients)" or "Cooking Steps"
3. Write ALL content in Korean only - no English translations anywhere
4. Follow the exact format above with all sections: 재료, 조리 방법, 팁"""
    fallback = f"부위: {display_name}"
    recipe_text = _call_llm_recipe(prompt, fallback)
    if not recipe_text.strip():
        recipe_text = f"# {display_name} 레시피\n\n부위: {display_name}\n\n레시피를 생성하려면 .env에 GEMINI_API_KEY를 설정해주세요."
    return LLMRecipeResponse(recipe=recipe_text)


@router.post(
    "/recipe-random-any",
    response_model=LLMRecipeResponse,
    summary="AI 랜덤 레시피 (아무 고기로 생성)",
    responses={401: {"description": "인증 필요"}},
)
async def recipe_random_any(
    db: Annotated[AsyncSession, Depends(get_db)],
    member: Annotated[Member, Depends(get_current_user)],
):
    """아무 고기나 선택하여 랜덤 레시피 생성. 냉장고와 무관하게 다양한 고기 부위 중 랜덤 선택."""
    # 모든 고기 부위 중 랜덤 선택
    q = select(MeatInfo).limit(100)  # 최대 100개
    result = await db.execute(q)
    all_meats = result.scalars().all()
    
    if not all_meats:
        return LLMRecipeResponse(
            recipe="# 랜덤 레시피\n\n고기 부위 정보를 찾을 수 없습니다."
        )
    
    random_meat = random.choice(all_meats)
    display_name = random_meat.part_name
    
    prompt = f"""Recommend one creative and diverse recipe using the following meat part.

Meat part: {display_name}

**CRITICAL LANGUAGE RULE: Write EVERYTHING in Korean ONLY. DO NOT include any English translations, especially in recipe titles. Recipe title should be Korean only, like "돼지 등심 사과 처트니 구이" - NOT "돼지 등심 사과 처트니 구이 (Pan-Seared Pork Loin with Apple Chutney)".**
**CRITICAL: Create VARIETY - avoid common recipes like "steak". Suggest unique cooking styles: Korean (bulgogi, galbi, bossam, jeyuk bokkeum), Western (stew, pasta, casserole, roast), Japanese (teriyaki, sukiyaki, yakitori), Chinese (stir-fry, braised, mapo), fusion, etc. Use diverse cooking methods: grilling, stir-frying, braising, stewing, frying, steaming, etc.**
**Important: Write concisely. Cooking steps: summarize in 3-5 steps.**
**CRITICAL for Ingredients: Include ALL necessary ingredients with SPECIFIC AMOUNTS. The recipe name must match the ingredients list.**
**Example format (Korean style):**
- 주재료: 돼지 등심 스테이크용(약 2cm 두께) 300~400g
- 밑간: 소금, 후추, 올리브오일 약간
- 캐러멜 소스: 설탕 2큰술, 버터 1큰술, 오렌지 1개(즙을 냄 또는 오렌지 마말레이드 2큰술), 디종 머스터드 1작은술(생략 가능), 레몬즙 또는 식초 1작은술, 다진 마늘 1/2작은술
**DO NOT skip ingredients. If the recipe name mentions a sauce (caramel, teriyaki, doubanjiang, etc.) or specific flavor, you MUST include ALL ingredients for that sauce/flavor with specific amounts.**

Write in the following format (ALL in Korean, NO English):

# 돼지 등심 사과 처트니 구이

## 재료
주재료: 돼지 등심 스테이크용(약 2cm 두께) 300~400g
밑간: 소금, 후추, 올리브오일 약간
사과 처트니 소스: 사과 1개(작게 다짐), 양파 1/2개(다짐), 설탕 2큰술, 식초 1큰술, 생강 1작은술(다짐), 계피가루 약간
채소: 감자 2개, 당근 1개
기타: 버터 1큰술, 다진 마늘 1작은술

## 조리 방법
1. 돼지 등심에 소금, 후추, 올리브오일을 발라 30분 재워둡니다.
2. 사과 처트니 소스를 만들기 위해 사과, 양파, 설탕, 식초, 생강을 넣고 약한 불에서 졸입니다.
3. 팬에 버터를 녹이고 돼지 등심을 앞뒤로 노릇하게 굽습니다.
4. 구운 고기를 접시에 담고 사과 처트니 소스를 올려 완성합니다.

## 팁
- 고기를 너무 오래 구우면 질겨지니 중간 불에서 빠르게 구워주세요.

CRITICAL FORMATTING RULES:
1. Recipe title: Write ONLY in Korean. Example: "# 돼지 등심 사과 처트니 구이" - DO NOT add English like "(Pan-Seared Pork Loin with Apple Chutney)"
2. Section headers: Use ONLY Korean - "## 재료", "## 조리 방법", "## 팁" - NOT "재료 (Ingredients)" or "Cooking Steps"
3. Write ALL content in Korean only - no English translations anywhere
4. Follow the exact format above with all sections: 재료, 조리 방법, 팁"""
    fallback = f"부위: {display_name}"
    recipe_text = _call_llm_recipe(prompt, fallback)
    if not recipe_text.strip():
        recipe_text = f"# {display_name} 레시피\n\n부위: {display_name}\n\n레시피를 생성하려면 .env에 GEMINI_API_KEY를 설정해주세요."
    return LLMRecipeResponse(recipe=recipe_text)


@router.post(
    "/recipe/save",
    response_model=SavedRecipeResponse,
    summary="레시피 저장",
    responses={401: {"description": "인증 필요"}},
)
async def save_recipe(
    body: SaveRecipeRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    member: Annotated[Member, Depends(get_current_user)],
):
    """레시피를 저장합니다."""
    try:
        # RecipeSource enum 검증
        source_enum = RecipeSource(body.source)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid source: {body.source}. Must be one of: {[e.value for e in RecipeSource]}"
        )
    
    saved_recipe = SavedRecipe(
        member_id=member.id,
        title=body.title,
        content=body.content,
        source=source_enum,
        used_meats=body.used_meats,
    )
    db.add(saved_recipe)
    await db.flush()
    await db.refresh(saved_recipe)
    
    return SavedRecipeResponse(
        id=saved_recipe.id,
        title=saved_recipe.title,
        content=saved_recipe.content,
        source=saved_recipe.source.value,
        used_meats=saved_recipe.used_meats,
        created_at=saved_recipe.created_at,
        updated_at=saved_recipe.updated_at,
    )


@router.get(
    "/recipe/saved",
    response_model=RecipeListResponse,
    summary="저장된 레시피 목록 조회",
    responses={401: {"description": "인증 필요"}},
)
async def get_saved_recipes(
    db: Annotated[AsyncSession, Depends(get_db)],
    member: Annotated[Member, Depends(get_current_user)],
):
    """저장된 레시피 목록을 조회합니다."""
    q = (
        select(SavedRecipe)
        .where(SavedRecipe.member_id == member.id)
        .order_by(SavedRecipe.created_at.desc())
    )
    result = await db.execute(q)
    recipes = result.scalars().all()
    recipe_ids = [r.id for r in recipes]
    bookmarked_q = select(RecipeBookmark.saved_recipe_id).where(
        RecipeBookmark.member_id == member.id,
        RecipeBookmark.saved_recipe_id.in_(recipe_ids),
    )
    bm_result = await db.execute(bookmarked_q)
    bookmarked_set = set(bm_result.scalars().all())
    
    return RecipeListResponse(
        recipes=[
            SavedRecipeResponse(
                id=r.id,
                title=r.title,
                content=r.content,
                source=r.source.value,
                used_meats=r.used_meats,
                created_at=r.created_at,
                updated_at=r.updated_at,
                is_bookmarked=r.id in bookmarked_set,
            )
            for r in recipes
        ]
    )


@router.delete(
    "/recipe/saved/{recipe_id}",
    summary="저장된 레시피 삭제",
    responses={401: {"description": "인증 필요"}, 404: {"description": "레시피를 찾을 수 없음"}},
)
async def delete_saved_recipe(
    recipe_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    member: Annotated[Member, Depends(get_current_user)],
):
    """저장된 레시피를 삭제합니다."""
    q = (
        select(SavedRecipe)
        .where(SavedRecipe.id == recipe_id)
        .where(SavedRecipe.member_id == member.id)
    )
    result = await db.execute(q)
    recipe = result.scalar_one_or_none()
    
    if not recipe:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="레시피를 찾을 수 없습니다."
        )
    
    await db.delete(recipe)
    await db.flush()
    
    return {"success": True, "message": "레시피가 삭제되었습니다."}


@router.get(
    "/recipe/bookmarks",
    response_model=BookmarkedIdsResponse,
    summary="즐겨찾기한 레시피 ID 목록",
    responses={401: {"description": "인증 필요"}},
)
async def get_recipe_bookmarks(
    db: Annotated[AsyncSession, Depends(get_db)],
    member: Annotated[Member, Depends(get_current_user)],
):
    """즐겨찾기한 저장 레시피 ID 목록을 반환합니다."""
    q = select(RecipeBookmark.saved_recipe_id).where(RecipeBookmark.member_id == member.id)
    result = await db.execute(q)
    ids = list(result.scalars().all())
    return BookmarkedIdsResponse(bookmarked_ids=ids)


@router.post(
    "/recipe/saved/{recipe_id}/bookmark",
    status_code=status.HTTP_201_CREATED,
    summary="레시피 즐겨찾기 추가",
    responses={401: {"description": "인증 필요"}, 404: {"description": "레시피를 찾을 수 없음"}},
)
async def add_recipe_bookmark(
    recipe_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    member: Annotated[Member, Depends(get_current_user)],
):
    """저장된 레시피를 즐겨찾기에 추가합니다."""
    recipe_q = select(SavedRecipe).where(SavedRecipe.id == recipe_id, SavedRecipe.member_id == member.id)
    r = await db.execute(recipe_q)
    recipe = r.scalar_one_or_none()
    if not recipe:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="레시피를 찾을 수 없습니다.")
    existing = await db.execute(
        select(RecipeBookmark).where(
            RecipeBookmark.member_id == member.id,
            RecipeBookmark.saved_recipe_id == recipe_id,
        )
    )
    if existing.scalar_one_or_none():
        return {"success": True, "message": "이미 즐겨찾기에 있습니다."}
    bookmark = RecipeBookmark(member_id=member.id, saved_recipe_id=recipe_id)
    db.add(bookmark)
    await db.flush()
    return {"success": True, "message": "즐겨찾기에 추가되었습니다."}


@router.delete(
    "/recipe/saved/{recipe_id}/bookmark",
    summary="레시피 즐겨찾기 해제",
    responses={401: {"description": "인증 필요"}},
)
async def remove_recipe_bookmark(
    recipe_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    member: Annotated[Member, Depends(get_current_user)],
):
    """저장된 레시피를 즐겨찾기에서 제거합니다."""
    q = select(RecipeBookmark).where(
        RecipeBookmark.member_id == member.id,
        RecipeBookmark.saved_recipe_id == recipe_id,
    )
    result = await db.execute(q)
    bookmark = result.scalar_one_or_none()
    if bookmark:
        await db.delete(bookmark)
        await db.flush()
    return {"success": True, "message": "즐겨찾기가 해제되었습니다."}
