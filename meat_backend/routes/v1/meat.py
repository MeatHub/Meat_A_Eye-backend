"""MEAT-01~02: 실시간 시세, 부위 상세 정보."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...config.database import get_db
from ...models.meat_info import MeatInfo
from ...models.market_price import MarketPrice
from ...schemas.meat import MeatPriceResponse, MeatInfoResponse
from ...services.kamis import KamisService
from ...services.safe_food import SafeFoodService

router = APIRouter()
kamis = KamisService()
safe_food = SafeFoodService()


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
