# -*- coding: utf-8 -*-
"""
외부 연동 통합 모듈.

- KAMIS 시세
- 식품 영양정보
- 축산물이력제 (국내/수입)
- AI 서버 프록시
"""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from typing import Any
from urllib.parse import quote

import httpx
import xmltodict
from fastapi import HTTPException

from .config.settings import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 공통 유틸
# ---------------------------------------------------------------------------


def _parse_response(text: str, source: str) -> dict:
    if not isinstance(text, str) or not text.strip():
        raise HTTPException(status_code=502, detail=f"{source} 응답이 비었습니다.")
    data = text.strip()
    if data.startswith("<!DOCTYPE") or data.startswith("<html") or "<html" in data[:100]:
        logger.warning("%s: HTML 응답 감지", source)
        raise HTTPException(status_code=502, detail=f"{source} API가 HTML 오류를 반환했습니다.")

    if "{" in data:
        idx = data.find("{")
        try:
            return json.loads(data[idx:])
        except json.JSONDecodeError:
            logger.debug("%s JSON 파싱 실패, XML 시도", source)

    if data.startswith("<"):
        try:
            parsed = xmltodict.parse(data)
            if isinstance(parsed, dict):
                return parsed
        except Exception as exc:  # noqa: BLE001
            logger.warning("%s XML 파싱 실패: %s", source, exc)
            raise HTTPException(status_code=502, detail=f"{source} XML 파싱 실패: {exc}") from exc

    if data.startswith("{") or data.startswith("["):
        try:
            parsed = json.loads(data)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=f"{source} JSON 파싱 실패: {exc}") from exc

    raise HTTPException(status_code=502, detail=f"{source} 응답 파싱 실패")


def _ensure_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    return []


# ---------------------------------------------------------------------------
# KAMIS
# ---------------------------------------------------------------------------

PART_TO_CODES: dict[str, dict[str, Any]] = {
    # 소(국내) - itemcode 4301
    "Beef_Tenderloin": {
        "itemcode": "4301",
        "kindcode": "21",
        "category": "500",
        "food_nm": "소/안심",
        "grades": ["1++등급", "1+등급", "1등급", "2등급", "3등급", "일반"],
    },
    "Beef_Ribeye": {
        "itemcode": "4301",
        "kindcode": "22",
        "category": "500",
        "food_nm": "소/등심",
        "grades": ["1++등급", "1+등급", "1등급", "2등급", "3등급", "일반"],
    },
    "Beef_Sirloin": {
        "itemcode": "4301",
        "kindcode": "23",
        "category": "500",
        "food_nm": "소/채끝",
        "grades": ["1++등급", "1+등급", "1등급", "2등급", "3등급", "일반"],
    },
    "Beef_Chuck": {
        "itemcode": "4301",
        "kindcode": "24",
        "category": "500",
        "food_nm": "소/목심",
        "grades": ["1++등급", "1+등급", "1등급", "2등급", "3등급", "일반"],
    },
    "Beef_Shoulder": {
        "itemcode": "4301",
        "kindcode": "25",
        "category": "500",
        "food_nm": "소/앞다리",
        "grades": ["1++등급", "1+등급", "1등급", "2등급", "3등급", "일반"],
    },
    "Beef_Round": {
        "itemcode": "4301",
        "kindcode": "27",
        "category": "500",
        "food_nm": "소/우둔",
        "grades": ["1++등급", "1+등급", "1등급", "2등급", "3등급", "일반"],
    },
    "Beef_BottomRound": {
        "itemcode": "4301",
        "kindcode": "26",
        "category": "500",
        "food_nm": "소/설도",
        "grades": ["1++등급", "1+등급", "1등급", "2등급", "3등급", "일반"],
    },
    "Beef_Brisket": {
        "itemcode": "4301",
        "kindcode": "28",
        "category": "500",
        "food_nm": "소/양지",
        "grades": ["1++등급", "1+등급", "1등급", "2등급", "3등급", "일반"],
    },
    "Beef_Shank": {
        "itemcode": "4301",
        "kindcode": "29",
        "category": "500",
        "food_nm": "소/사태",
        "grades": ["1++등급", "1+등급", "1등급", "2등급", "3등급", "일반"],
    },
    "Beef_Rib": {
        "itemcode": "4301",
        "kindcode": "50",
        "category": "500",
        "food_nm": "소/갈비",
        "grades": ["1++등급", "1+등급", "1등급", "일반"],
    },
    # 돼지(국내) - itemcode 4304
    "Pork_Shoulder": {
        "itemcode": "4304",
        "kindcode": "25",
        "category": "500",
        "food_nm": "돼지/앞다리",
        "grades": ["일반"],
    },
    "Pork_Belly": {
        "itemcode": "4304",
        "kindcode": "27",
        "category": "500",
        "food_nm": "돼지/삼겹살",
        "grades": ["일반"],
    },
    "Pork_Rib": {
        "itemcode": "4304",
        "kindcode": "28",
        "category": "500",
        "food_nm": "돼지/갈비",
        "grades": ["일반"],
    },
    "Pork_Loin": {
        "itemcode": "4304",
        "kindcode": "68",
        "category": "500",
        "food_nm": "돼지/목심",
        "grades": ["일반"],
    },
}


def _get_codes(part_name: str) -> dict[str, Any]:
    if part_name in PART_TO_CODES:
        data = PART_TO_CODES[part_name].copy()
        data.setdefault("grades", ["일반"])
        return data
    lower = (part_name or "").lower()
    for key, value in PART_TO_CODES.items():
        if key.lower() in lower or lower in key.lower():
            data = value.copy()
            data.setdefault("grades", ["일반"])
            return data
    if "_" in lower:
        prefix = lower.split("_", 1)[0]
        if prefix == "beef":
            return {
                "itemcode": "4301",
                "kindcode": "",
                "category": "500",
                "food_nm": "소",
                "grades": ["1++등급", "1+등급", "1등급", "2등급", "3등급", "일반"],
            }
        if prefix == "pork":
            return {
                "itemcode": "4304",
                "kindcode": "",
                "category": "500",
                "food_nm": "돼지",
                "grades": ["일반"],
            }
    return {"itemcode": "", "kindcode": "", "category": "500", "food_nm": part_name, "grades": ["일반"]}


async def fetch_kamis_price(part_name: str, region: str = "seoul") -> dict[str, Any]:
    key = (settings.kamis_api_key or "").strip()
    cert_id = (settings.kamis_cert_id or "meat-a-eye").strip()
    if not key:
        raise HTTPException(status_code=503, detail="KAMIS API 키가 설정되지 않았습니다.")

    base = (settings.kamis_api_url or "https://www.kamis.or.kr/service/price/xml.do").strip()
    today = date.today()
    end_day = today.strftime("%Y-%m-%d")
    start_day = (today - timedelta(days=6)).strftime("%Y-%m-%d")

    codes = _get_codes(part_name)
    if (part_name not in PART_TO_CODES and codes.get("food_nm") == part_name) or not codes.get("itemcode"):
        raise HTTPException(
            status_code=404,
            detail=f"{part_name} 실시간 데이터를 알 수 없습니다.",
        )
    params = {
        "action": "periodProductList",
        "p_cert_key": key,
        "p_cert_id": cert_id,
        "p_returntype": "xml",
        "p_startday": start_day,
        "p_endday": end_day,
        "p_productclscode": "01",
        "p_itemcategorycode": codes.get("category", "500"),
        "p_itemcode": codes.get("itemcode", ""),
        "p_kindcode": codes.get("kindcode", ""),
        "p_productrankcode": "",
        "p_countrycode": "",
        "p_convert_kg_yn": "N",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            req = client.build_request("GET", base, params=params)
            print("DEBUG: REAL API REQUEST KAMIS | Full URL:")
            print(f"  {req.url}")
            resp = await client.send(req)
            print(f"DEBUG: REAL API RESPONSE KAMIS | status={resp.status_code} | body_preview={resp.text[:150]}...")
            resp.raise_for_status()
            payload = resp.text
    except httpx.HTTPStatusError as exc:
        print(f"🚨 [REAL ERROR] {exc}")
        raise HTTPException(status_code=503, detail=f"KAMIS API 연결 실패: HTTP {exc.response.status_code}") from exc
    except Exception as exc:  # noqa: BLE001
        print(f"🚨 [REAL ERROR] {exc}")
        raise HTTPException(status_code=503, detail=f"KAMIS API 연결 실패: {exc}") from exc

    parsed = _parse_response(payload, "KAMIS")

    def _collect_items(node: Any) -> list:
        collected: list = []
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "item":
                    collected.extend(_ensure_list(value))
                else:
                    collected.extend(_collect_items(value))
        elif isinstance(node, list):
            for child in node:
                collected.extend(_collect_items(child))
        return collected

    items: list[dict[str, Any]] = []
    if "document" in parsed:
        document = parsed.get("document", {}) or {}
        error_code = str(document.get("error_code", "000"))
        if error_code not in ("0", "000"):
            print(f"🚨 [REAL ERROR] KAMIS 오류 코드: {error_code}")
            raise HTTPException(status_code=502, detail=f"KAMIS 오류 코드: {error_code}")
        items = _collect_items(document)
    elif "data" in parsed:
        data = parsed.get("data", {})
        if isinstance(data, dict) and data.get("error_code") == "000":
            items = _ensure_list(data.get("item"))

    grade_prices: list[dict[str, Any]] = []
    grade_seen: set[str] = set()
    target_name = codes.get("food_nm", "")

    def _extract_grade(name: str) -> str:
        if "(" in name and ")" in name:
            return name.split("(", 1)[1].split(")", 1)[0]
        return "일반"

    def _trend_from_direction(value: Any) -> str:
        mapping = {"0": "down", "1": "up", "2": "flat"}
        return mapping.get(str(value).strip(), "flat")

    for item in items:
        if not isinstance(item, dict):
            continue
        product_name = str(item.get("productName") or item.get("item_name") or "")
        if target_name and target_name not in product_name:
            continue
        unit = (item.get("unit") or "").lower()
        if "100g" not in unit:
            continue
        raw_price = item.get("price") or item.get("dpr1") or item.get("dpr0") or item.get("avgPrc")
        try:
            price_value = int(float(str(raw_price).replace(",", "")))
        except (TypeError, ValueError):
            price_value = 0
        if price_value <= 0:
            continue
        grade = _extract_grade(product_name)
        if grade in grade_seen:
            continue
        grade_seen.add(grade)
        grade_prices.append(
            {
                "grade": grade,
                "price": price_value,
                "unit": "100g",
                "priceDate": item.get("lastest_day") or item.get("regday") or end_day,
                "trend": _trend_from_direction(item.get("direction")),
            }
        )

    if not grade_prices:
        target_label = codes.get("food_nm") or part_name
        print(f"🚨 [REAL ERROR] KAMIS 실시간 데이터 없음: {target_label}")
        raise HTTPException(
            status_code=404,
            detail=f"{target_label} 실시간 데이터를 알 수 없습니다.",
        )

    grade_order = {grade: idx for idx, grade in enumerate(codes.get("grades", []))}
    grade_prices.sort(key=lambda x: grade_order.get(x["grade"], 99))
    debug_summary = ", ".join(f"{gp['grade']}:{gp['price']}" for gp in grade_prices)
    print(f"DEBUG: REAL API PARSED KAMIS | gradePrices=[{debug_summary}]")
    primary = grade_prices[0]
    return {
        "currentPrice": primary["price"],
        "unit": primary["unit"],
        "trend": primary["trend"],
        "price_date": primary["priceDate"],
        "source": "api",
        "gradePrices": grade_prices,
    }



# 영양정보 (DB meat_nutrition 사용 — NutritionService 참고)

# 외부 API 호출 제거됨. 영양정보는 meat_nutrition 테이블에서 LIKE 검색.

# Traceability helpers



def _fmt_date(value: str | None) -> str:
    if not value:
        return ""
    text = str(value).strip()
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    return text


def _recommended_expiry(slaughter_date_str: str | None, days: int = 3) -> str:
    """도축일 기준 냉장 권장 유통기한(일) 계산. YYYY-MM-DD 반환."""
    if not slaughter_date_str or not (slaughter_date_str or "").strip():
        return ""
    s = (slaughter_date_str or "").strip()
    if len(s) == 10 and s[4] == "-" and s[7] == "-":
        y, m, d = s[:4], s[5:7], s[8:10]
    elif len(s) == 8 and s.isdigit():
        y, m, d = s[:4], s[4:6], s[6:8]
    else:
        return ""
    try:
        from datetime import datetime, timedelta
        dt = datetime(int(y), int(m), int(d)) + timedelta(days=days)
        return dt.strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return ""


def _is_pork(part_name: str | None) -> bool:
    if not part_name:
        return False
    text = part_name.lower()
    return "pork" in text or "돼지" in text or "삼겹" in text or "목살" in text


def _unified_traceability_item(raw: dict[str, Any], trace_no: str, *, is_import: bool) -> dict[str, Any]:
    slaughter = ""
    if is_import:
        butch_from = _fmt_date(raw.get("butchfromDt"))
        butch_to = _fmt_date(raw.get("butchtoDt"))
        slaughter = butch_from or butch_to or _fmt_date(raw.get("butchYmd"))
        prcss_begin = _fmt_date(raw.get("prcssBeginDe"))
        prcss_end = _fmt_date(raw.get("prcssEndDe"))
        limit_to = _fmt_date(raw.get("limitToDt"))
        limit_from = _fmt_date(raw.get("limitFromDt"))
        base_item = {
            "historyNo": (raw.get("distbIdntfcNo") or raw.get("historyNo") or trace_no).strip(),
            "blNo": (raw.get("blNo") or "").strip() or None,
            "partName": (raw.get("kprodNm") or raw.get("regnNm") or raw.get("partName") or "").strip() or None,
            "origin": (raw.get("makeplcNm") or raw.get("impCtryNm") or raw.get("origin") or "").strip() or None,
            "slaughterDate": slaughter or None,
            "slaughterDateFrom": butch_from or None,
            "slaughterDateTo": butch_to or None,
            "processingDateFrom": prcss_begin or None,
            "processingDateTo": prcss_end or None,
            "exporter": (raw.get("butchNm") or raw.get("senderNm") or "").strip() or None,
            "importer": (raw.get("receiverNm") or "").strip() or None,
            "importDate": _fmt_date(raw.get("applyDt")) or None,
            "partCode": (raw.get("regnNm") or raw.get("regnCode") or "").strip() or None,
            "companyName": (raw.get("prcssNm") or raw.get("prcssBizNm") or raw.get("companyName") or "").strip() or None,
            "recommendedExpiry": limit_to or limit_from or _recommended_expiry(slaughter, 3) or None,
            "limitFromDt": limit_from or None,
            "limitToDt": limit_to or None,
            "refrigCnvrsAt": (raw.get("refrigCnvrsAt") or "").strip() or None,
            "refrigDistbPdBeginDe": _fmt_date(raw.get("refrigDistbPdBeginDe")) or None,
            "refrigDistbPdEndDe": _fmt_date(raw.get("refrigDistbPdEndDe")) or None,
            "birth_date": None,
            "grade": (raw.get("gradeNm") or raw.get("grade") or "").strip() or None,
        }
    else:
        slaughter = _fmt_date(raw.get("butcheryYmd") or raw.get("butchYmd"))
        base_item = {
            "historyNo": (raw.get("histNo") or raw.get("lotNo") or raw.get("cattleNo") or raw.get("pigNo") or trace_no).strip(),
            "blNo": None,
            "partName": (raw.get("partName") or raw.get("part_name") or "").strip() or None,
            "origin": (raw.get("lsTypeNm") or raw.get("origin") or "").strip() or None,
            "slaughterDate": slaughter or None,
            "slaughterDateFrom": None,
            "slaughterDateTo": None,
            "processingDateFrom": None,
            "processingDateTo": None,
            "exporter": None,
            "importer": None,
            "importDate": None,
            "partCode": None,
            "companyName": (raw.get("butcheryPlaceNm") or raw.get("processPlaceNm") or raw.get("prcssNm") or "").strip() or None,
            "recommendedExpiry": _recommended_expiry(slaughter, 3) or None,
            "limitFromDt": None,
            "limitToDt": None,
            "refrigCnvrsAt": None,
            "refrigDistbPdBeginDe": None,
            "refrigDistbPdEndDe": None,
            "birth_date": _fmt_date(raw.get("birthYmd")) or None,
            "grade": (raw.get("gradeNm") or raw.get("grade") or "").strip() or None,
        }
    return base_item


async def fetch_domestic_traceability(trace_no: str, part_name: str | None = None) -> dict[str, Any]:
    if not trace_no:
        raise HTTPException(status_code=400, detail="이력번호가 필요합니다.")

    base = (settings.mtrace_base_url or "http://api.mtrace.go.kr/rest").rstrip("/")
    user_id = (getattr(settings, "mtrace_user_id", None) or settings.traceability_api_key or "").strip()
    api_key = (getattr(settings, "mtrace_api_key", None) or settings.traceability_api_key or "").strip()
    call_type = getattr(settings, "mtrace_call_type", None) or "1"
    proc_type = getattr(settings, "mtrace_proc_type", None) or "1"

    if not api_key:
        raise HTTPException(status_code=503, detail="국내 이력제 API 키가 설정되지 않았습니다.")

    is_pig = _is_pork(part_name)
    path = "pig/market/uploadMarketDist" if is_pig else "cattle/market/uploadMarketDist"
    param = "pigNo" if is_pig else "cattleNo"
    url = (
        f"{base}/{path}?userId={quote(user_id or api_key)}&apiKey={quote(api_key)}&callType={call_type}&procType={proc_type}"
        f"&{param}={trace_no}"
    )
    print(f"DEBUG: REAL API REQUEST Domestic | URL: {url}")

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
            resp = await client.get(url)
            print(f"DEBUG: REAL API RESPONSE Domestic | status={resp.status_code} | body_preview={resp.text[:150]}...")
            
            # HTML 응답 체크 (리다이렉트 또는 오류 페이지)
            if resp.status_code >= 300 and resp.status_code < 400:
                # 리다이렉트 발생 시 HTML 오류로 처리
                raise HTTPException(status_code=502, detail="국내 이력제 API가 리다이렉트를 반환했습니다. API 키 또는 URL을 확인해주세요.")
            
            if resp.status_code == 503:
                raise HTTPException(status_code=503, detail="국내 이력제 서버가 503을 반환했습니다.")
            
            # HTML 응답인지 먼저 체크
            content_type = resp.headers.get("content-type", "").lower()
            if "text/html" in content_type or resp.text.strip().startswith("<!DOCTYPE") or resp.text.strip().startswith("<html"):
                logger.warning("국내 이력제 API가 HTML을 반환했습니다. API 키 또는 URL을 확인해주세요.")
                raise HTTPException(status_code=502, detail="국내 이력제 API가 HTML 오류를 반환했습니다. API 키 또는 URL을 확인해주세요.")
            
            resp.raise_for_status()
            payload = resp.text
    except HTTPException:
        raise
    except httpx.HTTPStatusError as exc:
        print(f"🚨 [REAL ERROR] {exc}")
        raise HTTPException(status_code=503, detail=f"국내 이력제 연결 실패: HTTP {exc.response.status_code}") from exc
    except Exception as exc:  # noqa: BLE001
        print(f"🚨 [REAL ERROR] {exc}")
        raise HTTPException(status_code=503, detail=f"국내 이력제 연결 실패: {exc}") from exc

    parsed = _parse_response(payload, "Domestic")
    items: list[dict[str, Any]] = []
    response = parsed.get("response")
    if isinstance(response, dict):
        body = response.get("body", {})
        if isinstance(body, dict):
            for entry in _ensure_list(body.get("items", body.get("item"))):
                if isinstance(entry, dict):
                    items.append(_unified_traceability_item(entry, trace_no, is_import=False))
    if not items:
        print(f"🚨 [REAL ERROR] 국내 이력제에서 이력번호를 찾지 못함: {trace_no}")
        raise HTTPException(status_code=502, detail="국내 이력제에서 이력번호를 찾지 못했습니다.")
    result = items[0]
    result["source"] = "api"
    result["server_maintenance"] = False
    return result


async def fetch_import_traceability(trace_no: str) -> dict[str, Any]:
    if not trace_no:
        raise HTTPException(status_code=400, detail="이력번호가 필요합니다.")

    base = (settings.meatwatch_base_url or "http://www.meatwatch.go.kr/rest").rstrip("/")
    sys_id = (settings.meatwatch_sys_id or settings.import_meat_api_key or "test2000").strip()
    url = f"{base}/selectDistbHistInfoWsrvDetail/{sys_id}/{trace_no}/list.do"
    print(f"DEBUG: REAL API REQUEST Import | URL: {url}")

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(url, headers={"Accept": "application/json"})
            print(f"DEBUG: REAL API RESPONSE Import | status={resp.status_code} | body_preview={resp.text[:150]}...")
            resp.raise_for_status()
            payload = resp.text
    except httpx.HTTPStatusError as exc:
        print(f"🚨 [REAL ERROR] {exc}")
        raise HTTPException(status_code=503, detail=f"수입 이력제 연결 실패: HTTP {exc.response.status_code}") from exc
    except Exception as exc:  # noqa: BLE001
        print(f"🚨 [REAL ERROR] {exc}")
        raise HTTPException(status_code=503, detail=f"수입 이력제 연결 실패: {exc}") from exc

    parsed = _parse_response(payload, "Import")
    items: list[dict[str, Any]] = []
    response = parsed.get("response")
    if isinstance(response, dict):
        body = response.get("body", {})
        if isinstance(body, dict):
            for entry in _ensure_list(body.get("items", body.get("item"))):
                if isinstance(entry, dict):
                    items.append(_unified_traceability_item(entry, trace_no, is_import=True))
    if not items and isinstance(parsed, dict) and str(parsed.get("returnCode")) == "0":
        flat = {k: v for k, v in parsed.items() if k not in {"returnCode", "returnMsg"}}
        if flat:
            items.append(_unified_traceability_item(flat, trace_no, is_import=True))
    if not items:
        print(f"🚨 [REAL ERROR] 수입 이력제에서 이력번호를 찾지 못함: {trace_no}")
        raise HTTPException(status_code=502, detail="수입 이력제에서 이력번호를 찾지 못했습니다.")
    result = items[0]
    result["source"] = "api"
    result["server_maintenance"] = False
    return result


def _is_bundle_no(value: str) -> bool:
    """수입육 묶음번호: A + 19~29자리 숫자."""
    t = (value or "").strip()
    if not t or len(t) < 20 or t[0] != "A":
        return False
    return t[1:].isdigit()


async def fetch_import_bundle_list(bundle_no: str) -> list[dict[str, Any]]:
    """
    수입육 묶음번호정보 조회 (meatwatch selectDistbHistInfoWsrvList).
    JSON: /rest/selectDistbHistInfoWsrvList/{SYS_ID}/{BUNDLE_NO}/list.do
    """
    if not bundle_no or not (bundle_no or "").strip():
        raise HTTPException(status_code=400, detail="묶음번호가 필요합니다.")
    bundle_no = (bundle_no or "").strip()

    base = (settings.meatwatch_base_url or "http://www.meatwatch.go.kr/rest").rstrip("/")
    sys_id = (settings.meatwatch_sys_id or settings.import_meat_api_key or "test2000").strip()
    url = f"{base}/selectDistbHistInfoWsrvList/{sys_id}/{bundle_no}/list.do"
    print(f"DEBUG: REAL API REQUEST Import Bundle | URL: {url}")

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(url, headers={"Accept": "application/json"})
            print(f"DEBUG: REAL API RESPONSE Import Bundle | status={resp.status_code} | body_preview={resp.text[:150]}...")
            resp.raise_for_status()
            payload = resp.text
    except httpx.HTTPStatusError as exc:
        print(f"🚨 [REAL ERROR] {exc}")
        raise HTTPException(status_code=503, detail=f"수입 이력제(묶음) 연결 실패: HTTP {exc.response.status_code}") from exc
    except Exception as exc:  # noqa: BLE001
        print(f"🚨 [REAL ERROR] {exc}")
        raise HTTPException(status_code=503, detail=f"수입 이력제(묶음) 연결 실패: {exc}") from exc

    parsed = _parse_response(payload, "ImportBundle")
    items: list[dict[str, Any]] = []

    # meatwatch 묶음 API 응답: bundleListVO = [ { distbIdntfcNo, sn, regnNm }, ... ], bundleDetailVO = { bundleNo, bundleDe, ... }
    bundle_list: list[dict[str, Any]] = []
    if isinstance(parsed, dict):
        return_code = str(parsed.get("returnCode", ""))
        if return_code != "0":
            print(f"🚨 [REAL ERROR] 수입 이력제(묶음) returnCode={return_code} msg={parsed.get('returnMsg')}")
            raise HTTPException(status_code=502, detail=parsed.get("returnMsg") or "묶음 조회 실패")
        # 최상위 / response / response.body 순으로 bundleListVO 탐색
        bundle_list = _ensure_list(parsed.get("bundleListVO"))
        if not bundle_list:
            resp = parsed.get("response")
            if isinstance(resp, dict):
                bundle_list = _ensure_list(resp.get("bundleListVO"))
                if not bundle_list:
                    body = resp.get("body", {}) or resp
                    bundle_list = _ensure_list(body.get("bundleListVO"))

        for vo in bundle_list:
            if not isinstance(vo, dict):
                continue
            distb_no = (vo.get("distbIdntfcNo") or vo.get("historyNo") or "").strip()
            if not distb_no:
                continue
            # 목록에는 distbIdntfcNo만 있음. 상세(도축일·유통기한 등)는 클릭 시 이력 상세 API로 조회
            items.append({
                "historyNo": distb_no,
                "partName": (vo.get("regnNm") or "").strip() or None,
                "slaughterDate": None,
                "recommendedExpiry": None,
                "grade": None,
                "origin": None,
                "companyName": None,
                "birth_date": None,
                "source": "api",
                "server_maintenance": False,
            })

    if not items:
        print(f"🚨 [REAL ERROR] 수입 이력제(묶음)에서 묶음번호를 찾지 못함: {bundle_no}")
        raise HTTPException(status_code=502, detail="수입 이력제에서 묶음번호를 찾지 못했습니다.")
    return items


async def fetch_traceability(trace_no: str, part_name: str | None = None) -> dict[str, Any]:
    """이력제 조회 (국내/수입 자동 분기)."""
    from .services.traceability_service import TraceabilityService  # noqa: WPS433

    return await TraceabilityService().fetch_traceability(trace_no, part_name)


# ---------------------------------------------------------------------------
# 서비스 클래스 통합 (기존 kamis.py, ai_proxy.py 래퍼)
# ---------------------------------------------------------------------------


class KamisService:
    """KAMIS 시세 서비스 (apis.fetch_kamis_price 래퍼)."""
    
    async def fetch_current_price(self, part_name: str, region: str = "seoul") -> dict[str, Any]:
        """KAMIS API로 시세 조회."""
        return await fetch_kamis_price(part_name, region)


class AIProxyService:
    """AI 서버 프록시 (apis.fetch_ai_analyze 래퍼)."""
    
    async def analyze(self, image_bytes: bytes, *, filename: str = "image.jpg", mode: str = "vision") -> dict[str, Any]:
        """AI 서버로 이미지 분석 요청."""
        return await fetch_ai_analyze(image_bytes, filename, mode)


# ---------------------------------------------------------------------------
# AI 서버
# ---------------------------------------------------------------------------


async def fetch_ai_analyze(image_bytes: bytes, filename: str = "image.jpg", mode: str = "vision") -> dict[str, Any]:
    base = (settings.ai_server_url or "").rstrip("/")
    if not base:
        raise HTTPException(status_code=503, detail="AI 서버 URL이 설정되지 않았습니다.")

    endpoint = f"{base}/predict" if mode == "vision" else f"{base}/ai/analyze"
    files = {"file": (filename, image_bytes, "image/jpeg")}
    data = {"mode": "ocr"} if mode == "ocr" else None
    print(f"DEBUG: REAL API REQUEST AI | URL: {endpoint} mode={mode}")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(endpoint, files=files, data=data)
            preview = resp.text[:200] if resp.text else "(binary)"
            print(f"DEBUG: REAL API RESPONSE AI | status={resp.status_code} | body_preview={preview}...")
            resp.raise_for_status()
            result = resp.json()
    except httpx.HTTPStatusError as exc:
        print(f"🚨 [REAL ERROR] {exc}")
        raise HTTPException(status_code=503, detail=f"AI 서버 연결 실패: HTTP {exc.response.status_code}") from exc
    except Exception as exc:  # noqa: BLE001
        print(f"🚨 [REAL ERROR] {exc}")
        raise HTTPException(status_code=503, detail=f"AI 서버 연결 실패: {exc}") from exc

    if result.get("status") != "success":
        raise HTTPException(status_code=422, detail=result.get("message", "AI 분석 실패"))

    if mode == "vision":
        part = result.get("class_name")
        if part:
            codes = _get_codes(part)
            logger.info("AI class_name=%s -> kamis_code=%s category=%s", part, codes.get("kamis_code"), codes.get("category"))
        return {
            "partName": part,
            "confidence": result.get("confidence"),
            "historyNo": None,
            "heatmap_image": result.get("heatmap_image"),
            "raw": result,
        }

    payload = result.get("data", {})
    return {
        "partName": None,
        "confidence": None,
        "historyNo": payload.get("trace_number") or payload.get("history_no") or payload.get("historyNo"),
        "heatmap_image": None,
        "raw": result,
    }

