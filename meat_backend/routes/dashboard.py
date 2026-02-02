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
        
        # 트렌드 계산 (전주 대비 증감률)
        if prev_count == 0:
            trend = f"+{current_count * 100}%"  # 신규 인기
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
    
    # 데이터 없을 시 기본값
    if not items:
        items = [
            PopularCutItem(name="삼겹살", count=0, trend="+0%", currentPrice=5000),
            PopularCutItem(name="한우 등심", count=0, trend="+0%", currentPrice=12000),
            PopularCutItem(name="닭가슴살", count=0, trend="+0%", currentPrice=3000),
        ]
    
    return PopularCutsResponse(items=items)
