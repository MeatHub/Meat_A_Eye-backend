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

        # 1) 캐시 우선: DB에 최근(당일/어제) 데이터가 있으면 바로 반환 (등급별로 구분)
        if db:
            cache_data = await self._get_from_db_cache(db, part_name, region, today, grade_code)
            if cache_data:
                try:
                    cache_date = datetime.strptime(cache_data["price_date"], "%Y-%m-%d").date()
                    # 어제 이상·오늘 이하일 때만 신선한 캐시로 사용 (미래 날짜 캐시는 무시)
                    if yesterday <= cache_date <= today:
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
                    await self._save_to_db(db, part_name, region, grade_code, api_data)
                return {**api_data, "source": "api"}
        except HTTPException:
            raise
        except Exception as e:
            logger.warning("KAMIS API call failed: %s", e)

        # 3) API 실패 시 기존 캐시(오래된 것 포함) 반환
        if db and cache_data:
            return {**cache_data, "source": "cache"}

        raise HTTPException(status_code=503, detail="시세 API 연결 실패. 잠시 후 다시 시도해 주세요.")

    def _normalize_grade_for_storage(self, part_name: str, grade_code: str) -> str:
        """캐시 저장/조회용 등급값: 국내 소는 01/02/03, 돼지/수입은 ''."""
        if part_name.startswith("Beef_") and not part_name.startswith("Import_Beef_"):
            return grade_code if grade_code in ("01", "02", "03") else ""
        return ""

    async def _save_to_db(
        self,
        db: AsyncSession,
        part_name: str,
        region: str,
        grade_code: str,
        price_data: dict[str, Any],
    ) -> None:
        try:
            price_val = price_data.get("currentPrice", 0)
            price_dt = datetime.strptime(
                price_data.get("price_date", str(date.today())), "%Y-%m-%d"
            ).date()
            g = self._normalize_grade_for_storage(part_name, grade_code)
            existing = await db.execute(
                select(MarketPrice).where(
                    MarketPrice.part_name == part_name,
                    MarketPrice.region == region,
                    MarketPrice.price_date == price_dt,
                    MarketPrice.grade_code == g,
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
                    grade_code=g,
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
        grade_code: str,
    ) -> dict[str, Any] | None:
        try:
            # 국내 소고기 "전체(00)"는 캐시 사용 안 함 → API에서 01+02+03 평균 계산
            if part_name.startswith("Beef_") and not part_name.startswith("Import_Beef_"):
                if grade_code == "00":
                    return None
                g = grade_code if grade_code in ("01", "02", "03") else ""
                if not g:
                    return None
            else:
                g = ""  # 돼지/수입: 등급 없음
            cutoff_date = today - timedelta(days=self.cache_days)
            q = (
                select(MarketPrice)
                .where(MarketPrice.part_name == part_name)
                .where(MarketPrice.region == region)
                .where(MarketPrice.grade_code == g)
                .where(MarketPrice.price_date >= cutoff_date)
                .order_by(desc(MarketPrice.price_date))
                .limit(1)
            )
            result = await db.execute(q)
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
