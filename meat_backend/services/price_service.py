"""가격정보 — KAMIS API + DB 캐시. 실패 시 HTTPException."""
import logging
from datetime import date, datetime, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.market_price import MarketPrice
from ..apis import KamisService

logger = logging.getLogger(__name__)


class PriceService:
    def __init__(self) -> None:
        self.kamis = KamisService()
        self.cache_days = 7

    async def fetch_current_price(
        self,
        part_name: str,
        region: str = "전국",
        grade_code: str = "00",
        db: AsyncSession | None = None,
    ) -> dict[str, Any]:
        """캐시 우선: DB에 당일/어제 데이터가 있으면 즉시 반환, 없으면 KAMIS API 호출 후 저장."""
        today = date.today()
        yesterday = today - timedelta(days=1)
        cache_data: dict[str, Any] | None = None

        # 1) 캐시 우선: DB에 최근(당일/어제) 데이터가 있으면 바로 반환
        if db:
            cache_data = await self._get_from_db_cache(db, part_name, region, today)
            if cache_data:
                try:
                    cache_date = datetime.strptime(cache_data["price_date"], "%Y-%m-%d").date()
                    # 어제 이상이면 신선한 캐시로 사용 (KAMIS는 어제까지 데이터 제공)
                    if cache_date >= yesterday:
                        return {**cache_data, "source": "cache"}
                except (ValueError, TypeError):
                    pass
                # 오래된 캐시라도 API 실패 시 사용할 수 있도록 보관

        # 2) 캐시 없거나 오래됨 → KAMIS API 호출
        try:
            api_data = await self.kamis.fetch_current_price(
                part_name=part_name,
                region=region,
                grade_code=grade_code,
            )
            if api_data.get("currentPrice", 0) > 0:
                if db:
                    await self._save_to_db(db, part_name, region, api_data)
                return {**api_data, "source": "api"}
        except HTTPException:
            raise
        except Exception as e:
            logger.warning("KAMIS API call failed: %s", e)

        # 3) API 실패 시 기존 캐시(오래된 것 포함) 반환
        if db and cache_data:
            return {**cache_data, "source": "cache"}

        raise HTTPException(status_code=503, detail="시세 API 연결 실패. 잠시 후 다시 시도해 주세요.")

    async def _save_to_db(
        self,
        db: AsyncSession,
        part_name: str,
        region: str,
        price_data: dict[str, Any],
    ) -> None:
        try:
            price_val = price_data.get("currentPrice", 0)
            price_dt = datetime.strptime(
                price_data.get("price_date", str(date.today())), "%Y-%m-%d"
            ).date()
            existing = await db.execute(
                select(MarketPrice).where(
                    MarketPrice.part_name == part_name,
                    MarketPrice.region == region,
                    MarketPrice.price_date == price_dt,
                ).limit(1)
            )
            row = existing.scalar_one_or_none()
            if row:
                row.current_price = price_val
            else:
                db.add(MarketPrice(
                    part_name=part_name,
                    current_price=price_val,
                    price_date=price_dt,
                    region=region,
                ))
            await db.flush()
        except Exception as e:
            logger.exception("Failed to save price to DB: %s", e)

    async def _get_from_db_cache(
        self,
        db: AsyncSession,
        part_name: str,
        region: str,
        today: date,
    ) -> dict[str, Any] | None:
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
                    "trend": "flat",
                    "price_date": str(record.price_date),
                    "gradePrices": [],
                }
        except Exception as e:
            logger.exception("DB cache fetch failed: %s", e)
        return None
