"""KAMIS 시세 API — services 폴더 분리, 재사용."""
import logging
from datetime import date
from typing import Any

import httpx

from ..config.settings import settings

logger = logging.getLogger(__name__)

# KAMIS 공공 API (실제 엔드포인트는 KAMIS 문서 기준)
KAMIS_BASE = "https://www.kamis.or.kr/service/price/xml.do"


class KamisService:
    """KAMIS 시세 조회 및 market_price_history 적재용."""

    def __init__(self) -> None:
        self.api_key = settings.kamis_api_key

    async def fetch_current_price(
        self,
        part_name: str,
        region: str = "seoul",
    ) -> dict[str, Any]:
        """실시간 시세 조회. 없으면 trend=flat, 가격 0 등 기본값."""
        if not self.api_key:
            logger.warning("KAMIS API key not set")
            return {
                "currentPrice": 0,
                "unit": "100g",
                "trend": "flat",
                "price_date": str(date.today()),
            }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # KAMIS 실제 API 스펙에 맞게 수정 필요
                r = await client.get(
                    KAMIS_BASE,
                    params={
                        "action": "dailySalesList",
                        "p_cert_key": self.api_key,
                        "p_cert_id": "meat-a-eye",
                        "p_returntype": "json",
                        "p_product_cls_code": "02",  # 축산물
                        "p_item_category_code": "500",
                        "p_region_name": region,
                    },
                )
                r.raise_for_status()
                data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        except httpx.TimeoutException:
            logger.warning("KAMIS request timeout")
            return {"currentPrice": 0, "unit": "100g", "trend": "flat"}
        except Exception as e:
            logger.exception("KAMIS fetch error: %s", e)
            return {"currentPrice": 0, "unit": "100g", "trend": "flat"}

        # 응답 구조에 맞게 파싱 (실제 KAMIS 스펙으로 조정)
        items = data.get("data", []) if isinstance(data, dict) else []
        for it in items if isinstance(items, list) else []:
            name = (it.get("item_name") or it.get("name") or "").strip()
            if part_name in name or name in part_name:
                price = int(it.get("price", it.get("dpr1", 0)) or 0)
                return {
                    "currentPrice": price,
                    "unit": "100g",
                    "trend": (it.get("trend") or "flat").lower(),
                    "price_date": it.get("date") or str(date.today()),
                }
        return {
            "currentPrice": 0,
            "unit": "100g",
            "trend": "flat",
            "price_date": str(date.today()),
        }
