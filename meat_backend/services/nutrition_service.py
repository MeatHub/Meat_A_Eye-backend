"""영양정보 API 서비스 - 식품의약품안전처 API 연동."""
import logging
from typing import Any

import httpx

from ..config.settings import settings

logger = logging.getLogger(__name__)

# 식품의약품안전처 영양정보 API (실제 엔드포인트는 API 문서 기준)
NUTRITION_API_BASE = "https://www.foodsafetykorea.go.kr/api"

# AI 부위명 → API 검색어 매핑
PART_NAME_MAPPING = {
    # 소고기
    "Beef_Tenderloin": ["소고기", "안심", "생것"],
    "Beef_Ribeye": ["소고기", "등심", "생것"],
    "Beef_Sirloin": ["소고기", "채끝살", "생것"],
    "Beef_Chuck": ["소고기", "목심", "생것"],
    "Beef_Brisket": ["소고기", "양지", "생것"],
    "Beef_Shank": ["소고기", "사태", "생것"],
    "Beef_BottomRound": ["소고기", "우둔", "생것"],
    "Beef_TopRound": ["소고기", "설도", "생것"],
    # 돼지고기
    "Pork_Belly": ["돼지고기", "삼겹살", "생것"],
    "Pork_Loin": ["돼지고기", "목살", "생것"],
    "Pork_Shoulder": ["돼지고기", "앞다리", "생것"],
    "Pork_Ham": ["돼지고기", "뒷다리", "생것"],
    "Pork_Neck": ["돼지고기", "목살", "생것"],
    # 한글 부위명도 지원
    "한우 안심": ["소고기", "안심", "생것"],
    "한우 등심": ["소고기", "등심", "생것"],
    "삼겹살": ["돼지고기", "삼겹살", "생것"],
    "목살": ["돼지고기", "목살", "생것"],
}


class NutritionService:
    """영양정보 API 서비스."""

    def __init__(self) -> None:
        self.api_key = settings.safe_food_api_key

    def _map_part_name_to_keywords(self, part_name: str) -> list[str]:
        """AI 부위명을 API 검색 키워드로 매핑."""
        # 정확한 매칭
        if part_name in PART_NAME_MAPPING:
            return PART_NAME_MAPPING[part_name]
        
        # 부분 매칭
        part_lower = part_name.lower()
        for key, keywords in PART_NAME_MAPPING.items():
            if any(kw.lower() in part_lower for kw in keywords):
                return keywords
        
        # 기본값: 부위명을 그대로 사용
        return [part_name, "생것"]

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
            logger.warning("Safe Food API key not set, returning default values")
            return {
                "calories": None,
                "protein": None,
                "fat": None,
                "carbohydrate": None,
                "source": "default",
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
        
        # 기본값 반환 (실제 데이터가 없을 경우)
        return {
            "calories": None,
            "protein": None,
            "fat": None,
            "carbohydrate": None,
            "source": "not_found",
        }

