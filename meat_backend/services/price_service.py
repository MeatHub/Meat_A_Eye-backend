"""가격정보 API 서비스 - KAMIS API 연동 및 캐싱."""
import logging
from datetime import date, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from ..config.database import get_db
from ..models.market_price import MarketPrice
from ..constants.meat_data import get_price_fallback
from .kamis import KamisService

logger = logging.getLogger(__name__)


class PriceService:
    """가격정보 API 서비스 (KAMIS) 및 캐싱."""

    def __init__(self) -> None:
        self.kamis = KamisService()
        self.cache_days = 7  # 캐시 유효 기간 (일)

    async def fetch_current_price(
        self,
        part_name: str,
        region: str = "seoul",
        db: AsyncSession | None = None,
    ) -> dict[str, Any]:
        """
        당일 가격정보 조회 (KAMIS API → DB 캐시 → Fallback 순서).
        
        Args:
            part_name: 부위명 (예: "Beef_Ribeye", "한우 등심")
            region: 지역명 (기본값: "seoul")
            db: 데이터베이스 세션 (캐시 조회용)
        
        Returns:
            {
                "currentPrice": int,      # 현재 가격 (원/100g)
                "unit": str,              # 단위
                "trend": str,             # 가격 추세 ("up", "down", "flat")
                "price_date": str,        # 가격 날짜 (YYYY-MM-DD)
                "source": str             # 데이터 출처 ("api", "cache", "fallback")
            }
        """
        today = date.today()
        
        # 1. KAMIS API 호출 시도
        try:
            api_data = await self.kamis.fetch_current_price(part_name=part_name, region=region)
            if api_data.get("currentPrice", 0) > 0:
                # API 성공 시 DB에 저장
                if db:
                    await self._save_to_db(db, part_name, region, api_data)
                return {
                    **api_data,
                    "source": "api",
                }
        except Exception as e:
            logger.warning(f"KAMIS API call failed: {e}, falling back to cache")

        # 2. DB 캐시 조회 (최근 7일 내 데이터)
        if db:
            cache_data = await self._get_from_db_cache(db, part_name, region, today)
            if cache_data:
                return {
                    **cache_data,
                    "source": "cache",
                }

        # 3. Fallback: constants/meat_data.py의 평균값 사용
        logger.warning(f"가격정보 조회 실패, Fallback 데이터 사용: {part_name}")
        fallback_price = get_price_fallback(part_name)
        return {
            "currentPrice": fallback_price,
            "unit": "100g",
            "trend": "flat",
            "price_date": str(today),
            "source": "fallback",
        }

    async def _save_to_db(
        self,
        db: AsyncSession,
        part_name: str,
        region: str,
        price_data: dict[str, Any],
    ) -> None:
        """가격 데이터를 DB에 저장."""
        try:
            price_record = MarketPrice(
                part_name=part_name,
                current_price=price_data.get("currentPrice", 0),
                price_date=datetime.strptime(
                    price_data.get("price_date", str(date.today())), "%Y-%m-%d"
                ).date(),
                region=region,
            )
            db.add(price_record)
            await db.flush()
        except Exception as e:
            logger.exception(f"Failed to save price to DB: {e}")

    async def _get_from_db_cache(
        self,
        db: AsyncSession,
        part_name: str,
        region: str,
        today: date,
    ) -> dict[str, Any] | None:
        """DB에서 최근 가격 데이터 조회."""
        try:
            cutoff_date = today - timedelta(days=self.cache_days)
            result = await db.execute(
                select(MarketPrice)
                .where(MarketPrice.part_name == part_name)
                .where(MarketPrice.region == region)
                .where(MarketPrice.price_date >= cutoff_date)
                .order_by(desc(MarketPrice.price_date))
                .limit(1)
            )
            record = result.scalar_one_or_none()
            if record:
                return {
                    "currentPrice": record.current_price,
                    "unit": "100g",
                    "trend": "flat",  # DB에는 추세 정보가 없으므로 기본값
                    "price_date": str(record.price_date),
                }
        except Exception as e:
            logger.exception(f"Failed to get price from DB cache: {e}")
        return None

