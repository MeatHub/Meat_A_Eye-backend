"""KAMIS 시세 API — Dynamic URL/params, data_mapper 연동."""
import logging
from datetime import date
from typing import Any
from urllib.parse import urlparse, parse_qs, urlunparse

import httpx
import xmltodict

from ..config.settings import settings
from .data_mapper import map_ai_class_to_api_codes

logger = logging.getLogger(__name__)


def _get_base_url_and_action() -> tuple[str, str]:
    """KAMIS_API_URL에서 base URL과 action 추출 (action= 포함 시)."""
    url = (settings.kamis_api_url or "").strip()
    action = (settings.kamis_action or "periodProductList").strip()
    if "?" in url:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        if "action" in qs:
            action = qs["action"][0]
        base = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
        return base, action
    if not url:
        url = "https://www.kamis.or.kr/service/price/xml.do"
    return url.rstrip("/").rstrip("?"), action


class KamisService:
    """KAMIS 시세 조회 — action 동적 변경, part_name 기반 파라미터 주입."""

    def __init__(self) -> None:
        self.api_key = (settings.kamis_api_key or "").strip()

    def _build_params(
        self,
        part_name: str,
        region: str = "seoul",
        product_cls_code: str = "01",
    ) -> dict[str, str]:
        """part_name에 따라 data_mapper에서 변환한 파라미터 주입."""
        codes = map_ai_class_to_api_codes(part_name)
        return {
            "action": _get_base_url_and_action()[1],
            "p_cert_key": self.api_key,
            "p_cert_id": "meat-a-eye",
            "p_returntype": "json",
            "p_product_cls_code": product_cls_code,
            "p_item_category_code": codes.get("category_code", "500"),
            "p_item_code": codes.get("kamis_code", "500"),
            "p_region_name": region,
        }

    def _parse_response(self, data: dict | str) -> dict[str, Any]:
        """XML/JSON 응답에서 가격 등 핵심 데이터 추출."""
        if isinstance(data, str):
            try:
                data = xmltodict.parse(data)
            except Exception as e:
                logger.warning("KAMIS XML parse error: %s", e)
                return {}

        items = []
        if isinstance(data, dict):
            body = data.get("response", data.get("data", data))
            if isinstance(body, dict):
                items = body.get("data", body.get("item", body.get("items", [])))
            if isinstance(items, dict):
                items = [items]
            if not isinstance(items, list):
                items = []

        for it in items:
            if not isinstance(it, dict):
                continue
            price_val = it.get("price") or it.get("dpr1") or it.get("price") or 0
            try:
                price = int(float(price_val))
            except (ValueError, TypeError):
                price = 0
            if price > 0:
                return {
                    "currentPrice": price,
                    "unit": "100g",
                    "trend": (it.get("trend") or "flat").lower(),
                    "price_date": it.get("date") or str(date.today()),
                }
        return {}

    async def fetch_current_price(
        self,
        part_name: str,
        region: str = "seoul",
    ) -> dict[str, Any]:
        """실시간 시세 조회. action은 .env KAMIS_ACTION으로 동적 변경 가능."""
        if not self.api_key:
            logger.warning("KAMIS API key not set")
            return {"currentPrice": 0, "unit": "100g", "trend": "flat", "price_date": str(date.today())}

        base_url, _ = _get_base_url_and_action()
        if not base_url:
            return {"currentPrice": 0, "unit": "100g", "trend": "flat", "price_date": str(date.today())}

        params = self._build_params(part_name, region)

        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                r = await client.get(base_url, params=params)
                r.raise_for_status()
                ct = (r.headers.get("content-type") or "").lower()
                if "json" in ct:
                    raw = r.json()
                else:
                    raw = r.text
        except httpx.TimeoutException:
            logger.warning("KAMIS request timeout")
            return {"currentPrice": 0, "unit": "100g", "trend": "flat", "price_date": str(date.today())}
        except Exception as e:
            logger.exception("KAMIS fetch error: %s", e)
            return {"currentPrice": 0, "unit": "100g", "trend": "flat", "price_date": str(date.today())}

        result = self._parse_response(raw)
        if not result:
            return {"currentPrice": 0, "unit": "100g", "trend": "flat", "price_date": str(date.today())}
        return result
