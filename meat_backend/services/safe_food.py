"""식품안전나라 API — 영양 정보 등. services 폴더 분리."""
import logging
from typing import Any

import httpx

from ..config.settings import settings

logger = logging.getLogger(__name__)

SAFE_FOOD_BASE = "https://www.foodsafetykorea.go.kr/api"


class SafeFoodService:
    """식품안전나라 API (영양정보 등)."""

    def __init__(self) -> None:
        self.api_key = settings.safe_food_api_key

    async def fetch_nutrition(self, food_name: str) -> dict[str, Any]:
        """이름으로 영양정보 조회. API 스펙에 맞게 수정."""
        if not self.api_key:
            return {"name": food_name, "calories": None, "protein": None, "fat": None, "recipes": []}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(
                    f"{SAFE_FOOD_BASE}/search",
                    params={"serviceKey": self.api_key, "keyword": food_name},
                )
                r.raise_for_status()
                data = r.json() if "application/json" in (r.headers.get("content-type") or "") else {}
        except Exception as e:
            logger.exception("SafeFood fetch error: %s", e)
            return {"name": food_name, "calories": None, "protein": None, "fat": None, "recipes": []}

        # 실제 API 응답 구조에 맞게 파싱
        items = data.get("body", data.get("items", [])) or []
        if isinstance(items, list) and items:
            it = items[0]
            return {
                "name": it.get("name", food_name),
                "calories": it.get("calories"),
                "protein": it.get("protein"),
                "fat": it.get("fat"),
                "recipes": it.get("recipes", []) or ["스테이크", "장조림"],
            }
        return {"name": food_name, "calories": None, "protein": None, "fat": None, "recipes": []}
