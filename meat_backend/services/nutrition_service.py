"""영양정보 API 서비스 - 식품의약품안전처 API 연동."""
import logging
from typing import Any

import httpx

from ..config.settings import settings
from ..services.data_mapper import map_ai_class_to_keywords
from ..constants.meat_data import get_nutrition_fallback

logger = logging.getLogger(__name__)

# 식품의약품안전처 영양정보 API (실제 엔드포인트는 API 문서 기준)
NUTRITION_API_BASE = "https://www.foodsafetykorea.go.kr/api"


class NutritionService:
    """영양정보 API 서비스."""

    def __init__(self) -> None:
        self.api_key = settings.safe_food_api_key

    def _map_part_name_to_keywords(self, part_name: str) -> list[str]:
        """AI 부위명을 API 검색 키워드로 매핑."""
        return map_ai_class_to_keywords(part_name)

    async def fetch_nutrition(self, part_name: str) -> dict[str, Any]:
        """
        부위명으로 영양정보 조회.
        
        Returns:
            {
                "calories": int,      # 칼로리 (100g당)
                "protein": float,     # 단백질 (g)
                "fat": float,         # 지방 (g)
                "carbohydrate": float, # 탄수화물 (g)
                "source": str         # 데이터 출처
            }
        """
        keywords = self._map_part_name_to_keywords(part_name)
        search_query = " ".join(keywords)
        
        if not self.api_key:
            logger.warning(f"Safe Food API key not set, using Fallback data: {part_name}")
            fallback_data = get_nutrition_fallback(part_name)
            return {
                "calories": fallback_data.get("calories"),
                "protein": fallback_data.get("protein"),
                "fat": fallback_data.get("fat"),
                "carbohydrate": fallback_data.get("carbohydrate"),
                "source": "fallback",
            }
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # 실제 API 엔드포인트는 API 문서에 맞게 수정 필요
                r = await client.get(
                    f"{NUTRITION_API_BASE}/nutrition/search",
                    params={
                        "serviceKey": self.api_key,
                        "keyword": search_query,
                        "pageNo": 1,
                        "numOfRows": 1,
                    },
                )
                r.raise_for_status()
                data = r.json() if "application/json" in (r.headers.get("content-type") or "") else {}
        except httpx.TimeoutException:
            logger.warning("Nutrition API request timeout")
            return {
                "calories": None,
                "protein": None,
                "fat": None,
                "carbohydrate": None,
                "source": "timeout",
            }
        except Exception as e:
            logger.exception("Nutrition API fetch error: %s", e)
            return {
                "calories": None,
                "protein": None,
                "fat": None,
                "carbohydrate": None,
                "source": "error",
            }

        # API 응답 구조 파싱 (실제 API 스펙에 맞게 수정 필요)
        items = data.get("body", data.get("items", [])) or []
        if isinstance(items, list) and len(items) > 0:
            item = items[0]
            return {
                "calories": int(item.get("calories", item.get("kcal", 0)) or 0),
                "protein": float(item.get("protein", item.get("protein_g", 0)) or 0),
                "fat": float(item.get("fat", item.get("fat_g", 0)) or 0),
                "carbohydrate": float(item.get("carbohydrate", item.get("carb_g", 0)) or 0),
                "source": "api",
            }
        
        # Fallback: constants/meat_data.py의 평균값 사용
        logger.warning(f"영양정보 API 조회 실패, Fallback 데이터 사용: {part_name}")
        fallback_data = get_nutrition_fallback(part_name)
        return {
            "calories": fallback_data.get("calories"),
            "protein": fallback_data.get("protein"),
            "fat": fallback_data.get("fat"),
            "carbohydrate": fallback_data.get("carbohydrate"),
            "source": "fallback",
        }

