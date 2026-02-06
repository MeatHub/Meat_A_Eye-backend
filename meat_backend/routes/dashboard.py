"""대시보드 API - 실시간 인기 부위, 통계 등."""
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from ..apis import fetch_kamis_price_period, check_kamis_monthly_trend_connection
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
    region: str = "전국",
    beef_part: str | None = None,
    pork_part: str | None = None,
    grade_code: str = "00",
    db: AsyncSession = Depends(get_db),
):
    """
    소(등심, 갈비), 돼지(삼겹, 목살) 대표 부위 100g당 가격 조회.
    market_prices 캐시 또는 KAMIS API 사용.
    
    Args:
        region: 지역코드 (기본값: "전국")
        beef_part: 소고기 부위 코드 (기본값: None - 전체, 특정 부위 선택 시 해당 부위만 조회)
        pork_part: 돼지고기 부위 코드 (기본값: None - 전체, 특정 부위 선택 시 해당 부위만 조회)
        grade_code: 등급코드 (기본값: "00" - 전체 평균)
    
    동작 방식:
        - beef_part와 pork_part가 모두 None이면: 기본 부위 목록 반환 (전체 선택)
        - beef_part만 지정되면: 해당 소고기 부위만 조회, 돼지고기는 조회하지 않음
        - pork_part만 지정되면: 해당 돼지고기 부위만 조회, 소고기는 조회하지 않음
    """
    # 기본 부위 목록 (테이블 구조에 맞춤: 품목명/품종명 형식)
    default_beef_parts = [("Beef_Ribeye", "소/등심"), ("Beef_Rib", "소/갈비")]
    default_pork_parts = [("Pork_Belly", "돼지/삼겹살"), ("Pork_Loin", "돼지/목심")]
    
    # 부위 필터 적용 - 부위 코드와 이름 매핑 (테이블 구조에 맞춤)
    # 품목명/품종명 구조: 소/안심, 소/등심, 소/설도, 소/양지, 소/갈비
    #                    돼지/앞다리, 돼지/삼겹살, 돼지/갈비, 돼지/목심
    beef_part_map = {
        "Beef_Tenderloin": "소/안심",  # itemcode 4301, kindcode 21
        "Beef_Ribeye": "소/등심",      # itemcode 4301, kindcode 22
        "Beef_BottomRound": "소/설도",  # itemcode 4301, kindcode 36
        "Beef_Brisket": "소/양지",     # itemcode 4301, kindcode 40
        "Beef_Rib": "소/갈비",         # itemcode 4301, kindcode 50
    }
    pork_part_map = {
        "Pork_Shoulder": "돼지/앞다리",  # itemcode 4304, kindcode 25
        "Pork_Belly": "돼지/삼겹살",    # itemcode 4304, kindcode 27
        "Pork_Rib": "돼지/갈비",        # itemcode 4304, kindcode 28
        "Pork_Loin": "돼지/목심",       # itemcode 4304, kindcode 68
    }
    
    # 부위 필터링 로직:
    # 1. 특정 부위가 선택된 경우: 해당 부위만 조회
    # 2. 부위가 None인 경우: 기본 부위 목록 사용 (전체 선택 시)
    # 3. 잘못된 코드인 경우: 빈 리스트 (조회하지 않음)
    
    # 소고기 부위 결정
    if beef_part and beef_part in beef_part_map:
        # 특정 소고기 부위 선택
        beef_parts = [(beef_part, beef_part_map[beef_part])]
    elif beef_part is None:
        # beef_part가 None이고 pork_part도 None이면 기본 부위 목록 사용 (전체 선택)
        # pork_part가 지정되어 있으면 소고기는 조회하지 않음
        if pork_part is None:
            beef_parts = default_beef_parts
        else:
            beef_parts = []  # 돼지고기만 선택된 경우 소고기는 조회하지 않음
    else:
        # 잘못된 beef_part 코드인 경우 빈 리스트
        beef_parts = []
    
    # 돼지고기 부위 결정
    if pork_part and pork_part in pork_part_map:
        # 특정 돼지고기 부위 선택
        pork_parts = [(pork_part, pork_part_map[pork_part])]
    elif pork_part is None:
        # pork_part가 None이고 beef_part도 None이면 기본 부위 목록 사용 (전체 선택)
        # beef_part가 지정되어 있으면 돼지고기는 조회하지 않음
        if beef_part is None:
            pork_parts = default_pork_parts
        else:
            pork_parts = []  # 소고기만 선택된 경우 돼지고기는 조회하지 않음
    else:
        # 잘못된 pork_part 코드인 경우 빈 리스트
        pork_parts = []
    
    beef_items: List[PriceItem] = []
    pork_items: List[PriceItem] = []

    for code, name in beef_parts:
        try:
            data = await price_service.fetch_current_price(
                part_name=code, region=region, grade_code=grade_code, db=db
            )
            if data.get("currentPrice", 0) > 0:
                beef_items.append(
                    PriceItem(
                        partName=name or code,
                        category="beef",
                        currentPrice=data["currentPrice"],
                        unit=data.get("unit", "100g"),
                        priceDate=data.get("price_date"),
                    )
                )
        except HTTPException as e:
            logger.warning("소 가격 조회 실패 (%s): HTTP %s - %s", name or code, e.status_code, e.detail)
        except Exception as e:
            logger.warning("소 가격 조회 실패 (%s): %s", name or code, e, exc_info=True)

    for code, name in pork_parts:
        try:
            data = await price_service.fetch_current_price(
                part_name=code, region=region, grade_code=grade_code, db=db
            )
            if data.get("currentPrice", 0) > 0:
                pork_items.append(
                    PriceItem(
                        partName=name or code,
                        category="pork",
                        currentPrice=data["currentPrice"],
                        unit=data.get("unit", "100g"),
                        priceDate=data.get("price_date"),
                    )
                )
        except HTTPException as e:
            logger.warning("돼지 가격 조회 실패 (%s): HTTP %s - %s", name or code, e.status_code, e.detail)
        except Exception as e:
            logger.warning("돼지 가격 조회 실패 (%s): %s", name or code, e, exc_info=True)

    return DashboardPricesResponse(beef=beef_items, pork=pork_items)


class PriceHistoryPoint(BaseModel):
    week: str  # "01.06~01.12" (주 구간 라벨)
    partName: str
    price: int


class PriceHistoryResponse(BaseModel):
    beef: List[PriceHistoryPoint]
    pork: List[PriceHistoryPoint]


def _aggregate_daily_by_week(daily: list[dict], part_name: str) -> list[dict]:
    """
    일별 리스트를 1주일 간격으로 집계. 최근 날(오늘) 기준 역순으로 주 구간 묶음.
    Returns: [ {"week": "01.06~01.12", "partName": "...", "price": int}, ... ]
    """
    if not daily:
        return []
    # (week_label, week_end_date) -> list of prices (주 끝 날짜로 정렬)
    by_week: dict[tuple[str, datetime], list[int]] = defaultdict(list)
    for point in daily:
        d = point.get("date", "")
        if len(d) < 10:
            continue
        try:
            dt_obj = datetime.strptime(d[:10], "%Y-%m-%d").date()
            week_start = dt_obj - timedelta(days=dt_obj.weekday())
            week_end = week_start + timedelta(days=6)
            week_label = f"{week_start.month:02d}.{week_start.day:02d}~{week_end.month:02d}.{week_end.day:02d}"
            week_end_dt = datetime.combine(week_end, datetime.min.time())
            by_week[(week_label, week_end_dt)].append(point.get("price", 0))
        except (ValueError, TypeError):
            continue
    result = []
    for (week_label, _), prices in sorted(by_week.items(), key=lambda x: x[0][1]):
        if prices:
            result.append({
                "week": week_label,
                "partName": part_name,
                "price": int(sum(prices) / len(prices)),
            })
    return result


@router.get(
    "/prices/history/check",
    summary="시세 API 연결 확인",
)
async def get_price_history_connection_check():
    """
    KAMIS 시세 API 연결 여부 확인.
    Returns: { "connected": true/false, "message": "..." }
    """
    return await check_kamis_monthly_trend_connection()


@router.get(
    "/prices/history",
    response_model=PriceHistoryResponse,
    summary="주별 가격 변동 (그래프용, periodProductList)",
)
async def get_dashboard_price_history(
    region: str = "전국",
    beef_part: str | None = None,
    pork_part: str | None = None,
    grade_code: str = "00",
    weeks: int = 6,
):
    """
    KAMIS 기간별 시세 API(periodProductList, p_startday/p_endday)로 최근 N주 일별 조회 후
    1주일 간격으로 집계. 실시간 시세와 동일한 지역/등급 필터 적용.
    """
    beef_part_map = {
        "Beef_Tenderloin": "소/안심",
        "Beef_Ribeye": "소/등심",
        "Beef_BottomRound": "소/설도",
        "Beef_Brisket": "소/양지",
        "Beef_Rib": "소/갈비",
    }
    pork_part_map = {
        "Pork_Shoulder": "돼지/앞다리",
        "Pork_Belly": "돼지/삼겹살",
        "Pork_Rib": "돼지/갈비",
        "Pork_Loin": "돼지/목심",
    }
    default_beef = [("Beef_Ribeye", "소/등심")]
    default_pork = [("Pork_Belly", "돼지/삼겹살")]

    beef_parts = (
        [(beef_part, beef_part_map[beef_part])]
        if beef_part and beef_part in beef_part_map
        else default_beef if pork_part is None else []
    )
    pork_parts = (
        [(pork_part, pork_part_map[pork_part])]
        if pork_part and pork_part in pork_part_map
        else default_pork if beef_part is None else []
    )

    beef_history: List[PriceHistoryPoint] = []
    pork_history: List[PriceHistoryPoint] = []

    for code, name in beef_parts:
        try:
            daily = await fetch_kamis_price_period(
                part_name=code,
                region=region,
                grade_code=grade_code,
                weeks=weeks,
            )
            for pt in _aggregate_daily_by_week(daily, name):
                beef_history.append(
                    PriceHistoryPoint(week=pt["week"], partName=pt["partName"], price=pt["price"])
                )
        except HTTPException:
            raise
        except Exception as e:
            logger.warning("소 주별 시세 조회 실패 (%s): %s", name, e)

    for code, name in pork_parts:
        try:
            daily = await fetch_kamis_price_period(
                part_name=code,
                region=region,
                grade_code=grade_code,
                weeks=weeks,
            )
            for pt in _aggregate_daily_by_week(daily, name):
                pork_history.append(
                    PriceHistoryPoint(week=pt["week"], partName=pt["partName"], price=pt["price"])
                )
        except HTTPException:
            raise
        except Exception as e:
            logger.warning("돼지 주별 시세 조회 실패 (%s): %s", name, e)

    return PriceHistoryResponse(beef=beef_history, pork=pork_history)


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
