"""영양정보 API 서비스 - 공공데이터포털 식품영양정보 API 연동."""
import logging
from typing import Any

import httpx
import xmltodict

from ..config.settings import settings
from .data_mapper import get_search_query
from ..constants.meat_data import get_nutrition_fallback

logger = logging.getLogger(__name__)


def _parse_numeric(val: Any) -> float | int | None:
    """문자열/숫자를 숫자로 변환. 빈 문자열은 None."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return val
    s = str(val).strip()
    if not s:
        return None
    try:
        f = float(s)
        return int(f) if f == int(f) else f
    except (ValueError, TypeError):
        return None


def _get_nutrition_base_url() -> str:
    """API base URL (.env에서, query 제외). tn_pubr은 /getTnPubrPublicNutriMaterialInfoApi 필요."""
    url = (getattr(settings, "safe_food_api_url", None) or "").strip()
    if not url:
        url = getattr(settings, "nutrition_api_url", None) or ""
    if "?" in url:
        url = url.split("?")[0]
    url = url.rstrip("/")
    if "tn_pubr" in url and "getTnPubr" not in url:
        url = f"{url}/getTnPubrPublicNutriMaterialInfoApi"
    return url


class NutritionService:
    """영양정보 API 서비스 (공공데이터포털 식품영양정보 API)."""

    def __init__(self) -> None:
        self.api_url = _get_nutrition_base_url()
        self.api_key = (getattr(settings, "safe_food_api_key", None) or "").strip()

    def _build_params(self, part_name: str) -> dict[str, str | int]:
        """FOOD_NM / FOOD_NM_KR에 AI가 판별한 한글 부위명 주입."""
        food_nm = get_search_query(part_name)
        return {
            "serviceKey": self.api_key,
            "pageNo": 1,
            "numOfRows": 10,
            "type": "json",
            "FOOD_NM": food_nm,
            "FOOD_NM_KR": food_nm,
        }

    def _parse_response(self, data: dict | str) -> dict[str, Any]:
        """응답에서 calories, protein, fat, carbohydrate 추출."""
        if isinstance(data, str):
            try:
                data = xmltodict.parse(data)
            except Exception:
                return {}

        records: list[dict] = []
        body = (data or {}).get("body") or ((data or {}).get("response") or {}).get("body") or data
        if isinstance(body, dict):
            records = body.get("items") or body.get("records") or []
        if not records and isinstance((data or {}).get("records"), list):
            records = (data or {}).get("records", [])
        if not records and isinstance((data or {}).get("item"), dict):
            records = [(data or {}).get("item")]
        if isinstance(data, list):
            records = data
        if not isinstance(records, list):
            records = []

        if not records:
            return {}
        item = records[0]
        calories = _parse_numeric(
            item.get("에너지(kcal)") or item.get("에너지") or item.get("kcal")
        )
        protein = _parse_numeric(
            item.get("단백질(g)") or item.get("단백질") or item.get("protein")
        )
        fat = _parse_numeric(
            item.get("지방(g)") or item.get("지방") or item.get("fat")
        )
        carbohydrate = _parse_numeric(
            item.get("탄수화물(g)") or item.get("탄수화물") or item.get("carbohydrate")
        )
        return {
            "calories": int(calories) if calories is not None else None,
            "protein": float(protein) if protein is not None else None,
            "fat": float(fat) if fat is not None else None,
            "carbohydrate": float(carbohydrate) if carbohydrate is not None else None,
        }

    async def fetch_nutrition(self, part_name: str) -> dict[str, Any]:
        """부위명으로 영양정보 조회. API 실패 시 meat_data Fallback."""
        print(self.api_url, self.api_key)
        if not self.api_url or not self.api_key:
            logger.warning(
                "영양정보 API URL 또는 키 미설정, Fallback: %s (SAFE_FOOD_API_URL, SAFE_FOOD_API_KEY)", part_name
            )
            fallback = get_nutrition_fallback(part_name)
            return {**fallback, "source": "fallback"}

        params = self._build_params(part_name)

        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                r = await client.get(self.api_url, params=params)
                r.raise_for_status()
                ct = (r.headers.get("content-type") or "").lower()
                if "json" in ct:
                    raw = r.json()
                else:
                    raw = r.text
        except httpx.TimeoutException:
            logger.warning("Nutrition API request timeout")
            fallback = get_nutrition_fallback(part_name)
            return {**fallback, "source": "timeout"}
        except Exception as e:
            logger.exception("Nutrition API fetch error: %s", e)
            fallback = get_nutrition_fallback(part_name)
            return {**fallback, "source": "error"}

        parsed = self._parse_response(raw)
        if not parsed or all(v is None for v in [parsed.get("calories"), parsed.get("protein")]):
            logger.warning("영양정보 API 조회 결과 없음, Fallback: %s", part_name)
            fallback = get_nutrition_fallback(part_name)
            return {**fallback, "source": "fallback"}

        return {**parsed, "source": "api"}
