"""대시보드 API - 실시간 인기 부위, 통계 등."""
import logging
from datetime import datetime, timedelta
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from ..config.database import get_db
from ..models.recognition_log import RecognitionLog
from ..services.price_service import PriceService

router = APIRouter()
logger = logging.getLogger(__name__)
price_service = PriceService()


class PopularCutItem(BaseModel):
    name: str
    count: int
    trend: str  # 예: "+12%"
    currentPrice: int | None = None


class PopularCutsResponse(BaseModel):
    items: List[PopularCutItem]


class PriceItem(BaseModel):
    partName: str
    category: str  # "beef" | "pork"
    currentPrice: int
    unit: str = "100g"
    priceDate: str | None = None


class DashboardPricesResponse(BaseModel):
    beef: List[PriceItem]
    pork: List[PriceItem]


@router.get(
    "/prices",
    response_model=DashboardPricesResponse,
    summary="실시간 돼지/소 가격 (100g당)",
)
async def get_dashboard_prices(
    db: AsyncSession = Depends(get_db),
):
    """
    소(등심, 갈비), 돼지(삼겹, 목살) 대표 부위 100g당 가격 조회.
    market_prices 캐시 또는 KAMIS API 사용.
    """
    beef_parts = [("Beef_Ribeye", "등심"), ("Beef_Rib", "갈비")]
    pork_parts = [("Pork_Belly", "삼겹살"), ("Pork_Loin", "목살")]
    beef_items: List[PriceItem] = []
    pork_items: List[PriceItem] = []

    for code, name in beef_parts:
        try:
            data = await price_service.fetch_current_price(
                part_name=code, region="seoul", db=db
            )
            if data.get("currentPrice", 0) > 0:
                beef_items.append(
                    PriceItem(
                        partName=name,
                        category="beef",
                        currentPrice=data["currentPrice"],
                        unit=data.get("unit", "100g"),
                        priceDate=data.get("price_date"),
                    )
                )
        except Exception as e:
            logger.warning("소 가격 조회 실패 (%s): %s", name, e)

    for code, name in pork_parts:
        try:
            data = await price_service.fetch_current_price(
                part_name=code, region="seoul", db=db
            )
            if data.get("currentPrice", 0) > 0:
                pork_items.append(
                    PriceItem(
                        partName=name,
                        category="pork",
                        currentPrice=data["currentPrice"],
                        unit=data.get("unit", "100g"),
                        priceDate=data.get("price_date"),
                    )
                )
        except Exception as e:
            logger.warning("돼지 가격 조회 실패 (%s): %s", name, e)

    return DashboardPricesResponse(beef=beef_items, pork=pork_items)


@router.get(
    "/popular-cuts",
    response_model=PopularCutsResponse,
    summary="실시간 인기 부위 (최근 7일 인식 횟수 기준)",
)
async def get_popular_cuts(
    db: AsyncSession = Depends(get_db),
    limit: int = 5,
):
    """
    최근 7일간 가장 많이 인식된 부위 Top N 조회.
    
    - count: 인식 횟수
    - trend: 전주 대비 증가율 (예: "+12%")
    - currentPrice: KAMIS API 가격 (캐시 사용)
    """
    # 기준 날짜: 최근 7일
    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)
    two_weeks_ago = now - timedelta(days=14)
    
    # 최근 7일 집계
    recent_query = (
        select(
            RecognitionLog.part_name,
            func.count(RecognitionLog.id).label("count"),
        )
        .where(RecognitionLog.created_at >= week_ago)
        .where(RecognitionLog.part_name != "unknown")
        .group_by(RecognitionLog.part_name)
        .order_by(desc("count"))
        .limit(limit)
    )
    recent_result = await db.execute(recent_query)
    recent_rows = recent_result.all()
    
    # 전주 7일 집계 (트렌드 계산용)
    prev_query = (
        select(
            RecognitionLog.part_name,
            func.count(RecognitionLog.id).label("count"),
        )
        .where(RecognitionLog.created_at >= two_weeks_ago)
        .where(RecognitionLog.created_at < week_ago)
        .where(RecognitionLog.part_name != "unknown")
        .group_by(RecognitionLog.part_name)
    )
    prev_result = await db.execute(prev_query)
    prev_rows = prev_result.all()
    prev_counts = {row.part_name: row.count for row in prev_rows}
    
    items = []
    for row in recent_rows:
        part_name = row.part_name
        current_count = row.count
        prev_count = prev_counts.get(part_name, 0)
        
        # 트렌드 계산 (전주 대비 증감률, prev=0이면 "신규"로 표시)
        if prev_count == 0:
            trend = "신규" if current_count > 0 else "0%"
        else:
            change = ((current_count - prev_count) / prev_count) * 100
            trend = f"{'+' if change > 0 else ''}{int(change)}%"
        
        # KAMIS 가격 조회 (캐시 우선, 실패 시 None)
        current_price = None
        try:
            price_data = await price_service.fetch_current_price(
                part_name=part_name,
                region="seoul",
                db=db,
            )
            current_price = price_data.get("currentPrice")
        except Exception as e:
            logger.warning(f"인기 부위 가격 조회 실패 ({part_name}): {e}")
        
        items.append(
            PopularCutItem(
                name=part_name,
                count=current_count,
                trend=trend,
                currentPrice=current_price,
            )
        )
    
    # 데이터 없을 시 빈 리스트 반환 (더미 데이터 제거)
    if not items:
        print("=" * 50)
        print(f"🚨 [API INFO] Endpoint: /api/dashboard/popular-cuts")
        print(f"🚨 [DETAILS]: 인식 로그 데이터 없음 (최근 7일)")
        print("=" * 50)
        logger.warning("인기 부위 데이터 없음 (최근 7일간 인식 로그 없음)")
    
    return PopularCutsResponse(items=items)
