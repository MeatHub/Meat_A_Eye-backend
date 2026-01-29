"""AI-01: 육류 AI 분석 요청 (multipart image, ocr/vision)."""
import logging
import os
from datetime import date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, status, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ...config.database import get_db
from ...models.member import Member
from ...models.recognition_log import RecognitionLog
from ...models.fridge_item import FridgeItem
from ...models.meat_info import MeatInfo
from ...models.web_notification import WebNotification
from ...schemas.ai import AIAnalyzeResponse, AIMode
from ...services.ai_proxy import AIProxyService
from ...services.traceability import fetch_traceability
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
            traceability_list = await fetch_traceability(history_no)
            if traceability_list and len(traceability_list) > 0:
                traceability_data = traceability_list[0]  # 첫 번째 결과 사용
                logger.info(f"이력제 정보 조회 성공: {traceability_data}")
        except Exception as e:
            logger.exception(f"이력제 API 호출 실패: {e}")
            # 이력제 API 실패해도 계속 진행 (Mock 응답 가능)

    fridge_item_id = None
    # part_name이 있고 auto_add_fridge가 True면 자동으로 냉장고에 추가 (인식일 +3일)
    if part_name and auto_add_fridge and member:
        meat_result = await db.execute(select(MeatInfo).where(MeatInfo.part_name == part_name).limit(1))
        meat = meat_result.scalar_one_or_none()
        if meat:
            recognition_date_only = recognition_date.date()
            expiry_date = recognition_date_only + timedelta(days=3)  # 인식일 +3일
            
            # 이력제 정보에서 도축일자, 등급 추출
            slaughter_date = None
            grade = None
            origin = None
            company_name = None
            
            if traceability_data:
                # 도축일자 파싱 (YYYY-MM-DD 형식 가정)
                slaughter_date_str = traceability_data.get("slaughterDate")
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

    return AIAnalyzeResponse(
        partName=part_name,
        confidence=confidence,
        historyNo=history_no,
        raw=out.get("raw"),
    )


class LLMRecipeRequest(BaseModel):
    fridgeItems: list[dict] = []


class LLMRecipeResponse(BaseModel):
    recipe: str


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
    # 냉장고 아이템 가져오기
    q = (
        select(FridgeItem)
        .where(FridgeItem.member_id == member.id)
        .where(FridgeItem.status == "stored")
        .options(selectinload(FridgeItem.meat_info))
    )
    result = await db.execute(q)
    items = result.scalars().all()
    
    # 고기 부위 리스트 추출
    meat_parts = []
    for item in items:
        if item.meat_info:
            meat_parts.append(item.meat_info.part_name)
    
    if not meat_parts:
        return LLMRecipeResponse(
            recipe="# 레시피 추천\n\n현재 냉장고에 보관 중인 고기가 없습니다. 고기를 추가한 후 다시 시도해주세요."
        )
    
    # LLM API 호출 (OpenAI 또는 Gemini)
    openai_api_key = os.getenv("OPENAI_API_KEY")
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    
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

    recipe_text = ""
    
    # OpenAI 사용
    if openai_api_key:
        try:
            import openai
            client = openai.OpenAI(api_key=openai_api_key)
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "당신은 전문 요리사입니다. 한국어로 레시피를 작성해주세요."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=1000,
            )
            recipe_text = response.choices[0].message.content
        except Exception as e:
            logger.exception(f"OpenAI API 호출 실패: {e}")
            recipe_text = f"# 레시피 추천\n\n현재 냉장고에 있는 고기: {meat_list_str}\n\n레시피 생성 중 오류가 발생했습니다."
    
    # Gemini 사용 (OpenAI 실패 시)
    elif gemini_api_key:
        try:
            import google.generativeai as genai
            genai.configure(api_key=gemini_api_key)
            model = genai.GenerativeModel('gemini-pro')
            response = model.generate_content(prompt)
            recipe_text = response.text
        except Exception as e:
            logger.exception(f"Gemini API 호출 실패: {e}")
            recipe_text = f"# 레시피 추천\n\n현재 냉장고에 있는 고기: {meat_list_str}\n\n레시피 생성 중 오류가 발생했습니다."
    
    # LLM API가 없으면 기본 레시피 반환
    else:
        recipe_text = f"""# 고기 레시피 추천

현재 냉장고에 있는 고기: {meat_list_str}

## 추천 레시피

### 1. 고기 요리
**재료:**
- {meat_list_str}
- 소금, 후추
- 올리브유

**조리법:**
1. 고기를 실온에 30분간 두어 온도를 맞춥니다.
2. 소금과 후추로 간을 합니다.
3. 팬을 달군 뒤 올리브유를 두릅니다.
4. 고기를 넣고 각 면을 2-3분씩 굽습니다.
5. 5분간 휴지시킨 후 제공합니다.

맛있게 드세요! 🥩"""

    return LLMRecipeResponse(recipe=recipe_text)
