"""축산물 이력제 API — XML/JSON 응답 정제, Bento Grid용 정제된 JSON."""

from __future__ import annotations

import logging
import re
from typing import Any
from xml.etree import ElementTree

import httpx

from ..config.settings import settings

logger = logging.getLogger(__name__)

# 이력제 API (실제 엔드포인트는 농림축산식품부 문서 참고)
TRACEABILITY_BASE = "https://traceability.mafra.go.kr/api"


def _parse_xml_text(text: str | None) -> str:
    return (text or "").strip()


def _parse_xml_int(text: str | None) -> int | None:
    if text is None:
        return None
    s = (text or "").strip()
    if not s:
        return None
    try:
        return int(re.sub(r"[^0-9-]", "", s))
    except ValueError:
        return None


def refine_history_response(raw: str | dict) -> list[dict[str, Any]]:
    """이력제 API XML/JSON 응답 → Bento Grid에서 바로 쓸 수 있는 정제된 JSON 리스트."""
    out: list[dict[str, Any]] = []

    if isinstance(raw, dict):
        items = raw.get("data", raw.get("items", raw.get("list", []))) or []
        if not isinstance(items, list):
            items = [items] if items else []
        for it in items:
            out.append({
                "historyNo": _parse_xml_text(it.get("historyNo") or it.get("history_no") or it.get("이력번호")),
                "slaughterDate": _parse_xml_text(it.get("slaughterDate") or it.get("도축일자") or it.get("slaughter_date")),
                "grade": _parse_xml_text(it.get("grade") or it.get("등급") or it.get("등급명")),
                "origin": _parse_xml_text(it.get("origin") or it.get("원산지") or it.get("origin_country")),
                "partName": _parse_xml_text(it.get("partName") or it.get("부위명") or it.get("part_name")),
                "companyName": _parse_xml_text(it.get("companyName") or it.get("업체명") or it.get("company_name")),
            })
        return out

    if not isinstance(raw, str):
        return out

    # XML 파싱
    try:
        root = ElementTree.fromstring(raw)
    except ElementTree.ParseError:
        return out

    # 흔한 래퍼: <response><item>...</item></response>
    for item in root.findall(".//item") or root.findall("item") or [root]:
        if item.tag == "item" or item.tag.endswith("item"):
            rec = {}
            for child in item:
                tag = (child.tag or "").split("}")[-1].lower()
                text = (child.text or "").strip()
                if "history" in tag or "이력" in tag:
                    rec["historyNo"] = text
                elif "slaughter" in tag or "도축" in tag or "date" in tag:
                    rec["slaughterDate"] = text
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
                    "slaughterDate": rec.get("slaughterDate", ""),
                    "grade": rec.get("grade", ""),
                    "origin": rec.get("origin", ""),
                    "partName": rec.get("partName", ""),
                    "companyName": rec.get("companyName", ""),
                })
    return out


async def fetch_traceability(history_no: str) -> list[dict[str, Any]]:
    """이력번호로 이력제 API 호출 후 정제된 JSON 반환."""
    api_key = settings.traceability_api_key
    if not api_key:
        logger.warning("축산물이력제 API key not set")
        return []
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                f"{TRACEABILITY_BASE}/trace",
                params={
                    "serviceKey": api_key,
                    "historyNo": history_no,
                },
            )
            r.raise_for_status()
            ct = (r.headers.get("content-type") or "").lower()
            if "json" in ct:
                raw = r.json()
            else:
                raw = r.text
    except Exception as e:
        logger.exception("Traceability fetch error: %s", e)
        return []
    return refine_history_response(raw)
