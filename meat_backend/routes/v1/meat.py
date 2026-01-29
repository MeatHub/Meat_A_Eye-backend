"""MEAT-01~03: 실시간 시세, 부위 상세 정보, 부위명으로 통합 정보 조회."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...config.database import get_db
from ...models.meat_info import MeatInfo
from ...models.market_price import MarketPrice
from ...schemas.meat import MeatPriceResponse, MeatInfoResponse, MeatInfoByPartNameResponse
from ...services.kamis import KamisService
from ...services.safe_food import SafeFoodService
from ...services.nutrition_service import NutritionService
from ...services.price_service import PriceService

router = APIRouter()
kamis = KamisService()
safe_food = SafeFoodService()
nutrition_service = NutritionService()
price_service = PriceService()


@router.get(
    "/prices",
    response_model=MeatPriceResponse,
    summary="MEAT-01 실시간 시세 조회",
    responses={
        404: {"description": "데이터 없음"},
        503: {"description": "KAMIS API 연동 지연"},
    },
)
async def meat_prices(
    partName: str,
    region: str = "seoul",
):
    # 1) DB market_prices 최신 데이터
    # 2) 없으면 KAMIS API 호출
    data = await kamis.fetch_current_price(part_name=partName, region=region)
    return MeatPriceResponse(
        currentPrice=data.get("currentPrice", 0),
        unit=data.get("unit", "100g"),
        trend=data.get("trend", "flat"),
    )


@router.get(
    "/info/{meat_id}",
    response_model=MeatInfoResponse,
    summary="MEAT-02 부위 상세 정보",
    responses={404: {"description": "육류 ID 오류"}},
)
async def meat_info(
    meat_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    row = await db.get(MeatInfo, meat_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="육류 ID 오류")
    # 식품안전나라 영양정보 보강 (선택)
    extra = await safe_food.fetch_nutrition(row.part_name)
    recipes = extra.get("recipes") or ["스테이크", "장조림"]
    cal = row.calories if row.calories is not None else extra.get("calories")
    prot = float(row.protein) if row.protein is not None else extra.get("protein")
    fat_val = float(row.fat) if row.fat is not None else extra.get("fat")
    return MeatInfoResponse(
        name=row.part_name,
        calories=cal,
        protein=prot,
        fat=fat_val,
        recipes=recipes,
        storageGuide=row.storage_guide,
    )


@router.get(
    "/info/part/{part_name}",
    response_model=MeatInfoByPartNameResponse,
    summary="MEAT-03 부위명으로 통합 정보 조회 (영양정보 + 가격정보)",
    responses={404: {"description": "부위 정보 없음"}},
)
async def meat_info_by_part_name(
    part_name: str,
    region: str = "seoul",
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
):
    """
    AI가 판별한 부위명으로 영양정보와 가격정보를 통합 조회.
    
    - 영양정보: 식품의약품안전처 API
    - 가격정보: KAMIS API (캐시 지원)
    """
    # 1. 영양정보 조회
    nutrition_data = await nutrition_service.fetch_nutrition(part_name)
    
    # 2. 가격정보 조회 (DB 캐시 포함)
    price_data = await price_service.fetch_current_price(
        part_name=part_name,
        region=region,
        db=db,
    )
    
    # 3. DB에서 기본 정보 조회 (선택)
    meat_info_record = None
    if db:
        result = await db.execute(
            select(MeatInfo).where(MeatInfo.part_name == part_name).limit(1)
        )
        meat_info_record = result.scalar_one_or_none()
    
    # 4. 응답 구성 (DB 데이터 우선, 없으면 API 데이터)
    calories = (
        meat_info_record.calories
        if meat_info_record and meat_info_record.calories
        else nutrition_data.get("calories")
    )
    protein = (
        float(meat_info_record.protein)
        if meat_info_record and meat_info_record.protein
        else nutrition_data.get("protein")
    )
    fat = (
        float(meat_info_record.fat)
        if meat_info_record and meat_info_record.fat
        else nutrition_data.get("fat")
    )
    
    return MeatInfoByPartNameResponse(
        partName=part_name,
        calories=calories,
        protein=protein,
        fat=fat,
        carbohydrate=nutrition_data.get("carbohydrate"),
        currentPrice=price_data.get("currentPrice", 0),
        priceUnit=price_data.get("unit", "100g"),
        priceTrend=price_data.get("trend", "flat"),
        priceDate=price_data.get("price_date"),
        priceSource=price_data.get("source", "fallback"),
        storageGuide=meat_info_record.storage_guide if meat_info_record else None,
    )
