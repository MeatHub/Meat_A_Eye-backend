"""축산물/수입육 이력제 API — trace_no 기반 조회, API Key 인코딩 주의."""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlencode
from xml.etree import ElementTree

import httpx
import xmltodict

from ..config.settings import settings
from ..constants.meat_data import get_traceability_fallback

logger = logging.getLogger(__name__)


def _parse_xml_text(text: str | None) -> str:
    return (text or "").strip()


def _refine_response(raw: str | dict) -> list[dict[str, Any]]:
    """이력제 API XML/JSON 응답 → birth_date, grade 등 정제된 JSON."""
    out: list[dict[str, Any]] = []

    if isinstance(raw, dict):
        data = raw.get("response", raw.get("body", raw))
        items = []
        if isinstance(data, dict):
            items = data.get("items", data.get("item", data.get("data", [])))
        if isinstance(items, dict):
            items = [items]
        if not isinstance(items, list):
            items = []
        for it in items if isinstance(items, list) else []:
            if not isinstance(it, dict):
                continue
            out.append({
                "historyNo": _parse_xml_text(it.get("historyNo") or it.get("이력번호") or it.get("traceNo")),
                "birth_date": _parse_xml_text(it.get("birthDate") or it.get("출생일") or it.get("birth_date")),
                "slaughterDate": _parse_xml_text(it.get("slaughterDate") or it.get("도축일자") or it.get("slaughter_date")),
                "grade": _parse_xml_text(it.get("grade") or it.get("등급") or it.get("등급명")),
                "origin": _parse_xml_text(it.get("origin") or it.get("원산지") or it.get("origin_country")),
                "partName": _parse_xml_text(it.get("partName") or it.get("부위명") or it.get("part_name")),
                "companyName": _parse_xml_text(it.get("companyName") or it.get("업체명") or it.get("company_name")),
            })
        return out

    if isinstance(raw, str):
        try:
            parsed = xmltodict.parse(raw)
            return _refine_response(parsed)
        except Exception:
            pass
        try:
            root = ElementTree.fromstring(raw)
            for item in root.findall(".//item") or root.findall("item") or [root]:
                if item.tag != "item" and not item.tag.endswith("item"):
                    continue
                rec = {}
                for child in item:
                    tag = (child.tag or "").split("}")[-1].lower()
                    text = (child.text or "").strip()
                    if "history" in tag or "이력" in tag or "trace" in tag:
                        rec["historyNo"] = text
                    elif "slaughter" in tag or "도축" in tag:
                        rec["slaughterDate"] = text
                    elif "birth" in tag or "출생" in tag:
                        rec["birth_date"] = text
                    elif "grade" in tag or "등급" in tag:
                        rec["grade"] = text
                    elif "origin" in tag or "원산지" in tag:
                        rec["origin"] = text
                    elif "part" in tag or "부위" in tag:
                        rec["partName"] = text
                    elif "company" in tag or "업체" in tag:
                        rec["companyName"] = text
                if rec:
                    out.append({
                        "historyNo": rec.get("historyNo", ""),
                        "birth_date": rec.get("birth_date", ""),
                        "slaughterDate": rec.get("slaughterDate", ""),
                        "grade": rec.get("grade", ""),
                        "origin": rec.get("origin", ""),
                        "partName": rec.get("partName", ""),
                        "companyName": rec.get("companyName", ""),
                    })
        except ElementTree.ParseError:
            pass
    return out


class TraceabilityService:
    """축산물 이력제 API. API Key는 이미 인코딩되어 있으므로 params 자동 인코딩 회피."""

    def __init__(self) -> None:
        self.api_key = (settings.traceability_api_key or "").strip()
        self.api_url = (settings.traceability_api_url or "").strip().split("?")[0].rstrip("/")

    def _build_url(self, trace_no: str) -> str:
        """serviceKey는 이미 인코딩된 값이므로 URL에 그대로 붙이고, 나머지만 encode."""
        base = self.api_url or "http://data.ekape.or.kr/openapi-data/service/user/animalTrace/traceNoSearch"
        other_params = urlencode({"traceNo": trace_no, "type": "json"})
        return f"{base}?serviceKey={self.api_key}&{other_params}"

    async def fetch_traceability(self, trace_no: str) -> dict[str, Any]:
        """trace_no(OCR 결과)로 이력제 API 호출. 실패 시 Fallback."""
        if not self.api_key or not trace_no:
            logger.warning("이력제 API key 또는 trace_no 없음")
            return get_traceability_fallback(trace_no)

        url = self._build_url(trace_no)

        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                r = await client.get(url)
                r.raise_for_status()
                ct = (r.headers.get("content-type") or "").lower()
                if "json" in ct:
                    raw = r.json()
                else:
                    raw = r.text
        except Exception as e:
            logger.exception("Traceability fetch error: %s", e)
            return get_traceability_fallback(trace_no)

        items = _refine_response(raw)
        if not items:
            return get_traceability_fallback(trace_no)

        first = items[0]
        return {
            "birth_date": first.get("birth_date") or first.get("slaughterDate"),
            "slaughterDate": first.get("slaughterDate"),
            "grade": first.get("grade"),
            "origin": first.get("origin"),
            "partName": first.get("partName"),
            "companyName": first.get("companyName"),
            "historyNo": first.get("historyNo") or trace_no,
            "source": "api",
        }
