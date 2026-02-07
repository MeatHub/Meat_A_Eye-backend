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
from datetime import date, datetime, timedelta
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

# 등급코드 매핑 (KAMIS API용)
GRADE_CODE_MAP: dict[str, str] = {
    "00": "전체",  # 전체 평균
    "01": "1++등급",
    "02": "1+등급",
    "03": "1등급",
    "81": "미국산",
    "82": "호주산",
}

PART_TO_CODES: dict[str, dict[str, Any]] = {
    # 소(국내) - itemcode 4301
    "Beef_Tenderloin": {
        "itemcode": "4301",
        "kindcode": "21",
        "category": "500",
        "food_nm": "소/안심",
        "grades": ["1++등급", "1+등급", "1등급", "2등급", "3등급", "일반"],
        "grade_codes": {"00": "전체", "01": "1++등급", "02": "1+등급", "03": "1등급"},
    },
    "Beef_Ribeye": {
        "itemcode": "4301",
        "kindcode": "22",
        "category": "500",
        "food_nm": "소/등심",
        "grades": ["1++등급", "1+등급", "1등급", "2등급", "3등급", "일반"],
        "grade_codes": {"00": "전체", "01": "1++등급", "02": "1+등급", "03": "1등급"},
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
        "kindcode": "36",
        "category": "500",
        "food_nm": "소/설도",
        "grades": ["1++등급", "1+등급", "1등급", "2등급", "3등급", "일반"],
        "grade_codes": {"00": "전체", "01": "1++등급", "02": "1+등급", "03": "1등급"},
    },
    "Beef_Brisket": {
        "itemcode": "4301",
        "kindcode": "40",
        "category": "500",
        "food_nm": "소/양지",
        "grades": ["1++등급", "1+등급", "1등급", "2등급", "3등급", "일반"],
        "grade_codes": {"00": "전체", "01": "1++등급", "02": "1+등급", "03": "1등급"},
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
        "grade_codes": {"00": "전체", "01": "1++등급", "02": "1+등급", "03": "1등급"},
    },
    # 돼지(국내) - itemcode 4304
    "Pork_Shoulder": {
        "itemcode": "4304",
        "kindcode": "25",
        "category": "500",
        "food_nm": "돼지/앞다리",
        "grades": ["일반"],
        "grade_codes": {"00": "전체"},
    },
    "Pork_Belly": {
        "itemcode": "4304",
        "kindcode": "27",
        "category": "500",
        "food_nm": "돼지/삼겹살",
        "grades": ["일반"],
        "grade_codes": {"00": "전체"},
    },
    "Pork_Rib": {
        "itemcode": "4304",
        "kindcode": "28",
        "category": "500",
        "food_nm": "돼지/갈비",
        "grades": ["일반"],
        "grade_codes": {"00": "전체"},
    },
    "Pork_Loin": {
        "itemcode": "4304",
        "kindcode": "68",
        "category": "500",
        "food_nm": "돼지/목심",
        "grades": ["일반"],
        "grade_codes": {"00": "전체"},
    },
}


def _get_codes(part_name: str) -> dict[str, Any]:
    if part_name in PART_TO_CODES:
        data = PART_TO_CODES[part_name].copy()
        data.setdefault("grades", ["일반"])
        data.setdefault("grade_codes", {"00": "전체"})
        return data
    lower = (part_name or "").lower()
    for key, value in PART_TO_CODES.items():
        if key.lower() in lower or lower in key.lower():
            data = value.copy()
            data.setdefault("grades", ["일반"])
            data.setdefault("grade_codes", {"00": "전체"})
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
                "grade_codes": {"00": "전체", "01": "1++등급", "02": "1+등급", "03": "1등급"},
            }
        if prefix == "pork":
            return {
                "itemcode": "4304",
                "kindcode": "",
                "category": "500",
                "food_nm": "돼지",
                "grades": ["일반"],
                "grade_codes": {"00": "전체"},
            }
    return {
        "itemcode": "",
        "kindcode": "",
        "category": "500",
        "food_nm": part_name,
        "grades": ["일반"],
        "grade_codes": {"00": "전체"},
    }


async def fetch_kamis_price(
    part_name: str,
    region: str = "전국",
    grade_code: str = "00",
) -> dict[str, Any]:
    """
    KAMIS API로 시세 조회
    
    Args:
        part_name: 고기 부위명
        region: 지역코드 (기본값: "전국" - 전체지역)
        grade_code: 등급코드 (기본값: "00" - 전체 평균)
    """
    key = (settings.kamis_api_key or "").strip()
    cert_id = (settings.kamis_cert_id or "pak101044").strip()
    if not key:
        raise HTTPException(status_code=503, detail="KAMIS API 키가 설정되지 않았습니다.")

    base = (settings.kamis_api_url or "https://www.kamis.or.kr/service/price/xml.do").strip()
    today = date.today()
    # API는 어제 날짜까지만 데이터가 있으므로 어제 날짜를 end_day로 사용
    yesterday = today - timedelta(days=1)
    end_day = yesterday.strftime("%Y-%m-%d")
    start_day = (yesterday - timedelta(days=7)).strftime("%Y-%m-%d")  # 어제 기준 7일전

    codes = _get_codes(part_name)
    if (part_name not in PART_TO_CODES and codes.get("food_nm") == part_name) or not codes.get("itemcode"):
        raise HTTPException(
            status_code=404,
            detail=f"{part_name} 실시간 데이터를 알 수 없습니다.",
        )
    
    # 지역코드 매핑 (KAMIS API 소매가격 지역코드)
    # 소매가격: 1101(서울), 2100(부산), 2200(대구), 2300(인천), 2401(광주), 2501(대전), 2601(울산), 
    # 3111(수원), 3214(강릉), 3211(춘천), 3311(청주), 3511(전주), 3711(포항), 3911(제주), 
    # 3113(의정부), 3613(순천), 3714(안동), 3814(창원), 3145(용인), 2701(세종), 3112(성남), 
    # 3138(고양), 3411(천안), 3818(김해)
    region_code_map = {
        "전국": "",
        "서울": "1101",
        "부산": "2100",
        "대구": "2200",
        "인천": "2300",
        "광주": "2401",
        "대전": "2501",
        "울산": "2601",
        "세종": "2701",
        "수원": "3111",
        "강릉": "3214",
        "춘천": "3211",
        "청주": "3311",
        "전주": "3511",
        "포항": "3711",
        "제주": "3911",
        "의정부": "3113",
        "순천": "3613",
        "안동": "3714",
        "창원": "3814",
        "용인": "3145",
        "성남": "3112",
        "고양": "3138",
        "천안": "3411",
        "김해": "3818",
    }
    county_code = region_code_map.get(region, region)  # 매핑되지 않은 경우 원본 값 사용
    
    # 등급코드 처리: 소고기만 등급 구분이 있음, 돼지는 항상 전체 평균
    is_beef = part_name.startswith("Beef_")
    if is_beef:
        # 소고기: 등급코드 "00" (전체 평균)일 때는 빈 문자열, 아니면 해당 등급코드 사용
        product_rank_code = "" if grade_code == "00" else grade_code
    else:
        # 돼지: 항상 전체 평균 (등급 구분 없음)
        product_rank_code = ""
    
    params = {
        "action": "periodRetailProductList",  # 소매가격 조회 액션
        "p_cert_key": key,
        "p_cert_id": cert_id,
        "p_returntype": "xml",  # XML 형식 사용 (사용자 예시와 동일)
        "p_startday": start_day,
        "p_endday": end_day,
        "p_itemcategorycode": codes.get("category", "500"),  # 품목카테고리코드 추가
        "p_itemcode": codes.get("itemcode", ""),
        "p_kindcode": codes.get("kindcode", ""),
        "p_productrankcode": product_rank_code,  # 등급코드 (소고기만 사용, 돼지는 항상 빈 문자열)
        "p_countrycode": county_code,  # 지역코드 (p_countrycode 사용)
        "p_convert_kg_yn": "N",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            req = client.build_request("GET", base, params=params)
            print("DEBUG: REAL API REQUEST KAMIS | Full URL:")
            print(f"  {req.url}")
            resp = await client.send(req)
            print(f"DEBUG: REAL API RESPONSE KAMIS | status={resp.status_code} | body_preview={resp.text[:500]}...")
            resp.raise_for_status()
            payload = resp.text
            print(f"DEBUG: FULL RESPONSE LENGTH: {len(payload)} bytes")
    except httpx.HTTPStatusError as exc:
        print(f"🚨 [REAL ERROR] {exc}")
        raise HTTPException(status_code=503, detail=f"KAMIS API 연결 실패: HTTP {exc.response.status_code}") from exc
    except Exception as exc:  # noqa: BLE001
        print(f"🚨 [REAL ERROR] {exc}")
        raise HTTPException(status_code=503, detail=f"KAMIS API 연결 실패: {exc}") from exc

    parsed = _parse_response(payload, "KAMIS")
    print(f"DEBUG: PARSED RESPONSE KEYS: {list(parsed.keys()) if isinstance(parsed, dict) else 'NOT A DICT'}")
    print(f"DEBUG: PARSED RESPONSE TYPE: {type(parsed)}")
    if isinstance(parsed, dict):
        if "document" in parsed:
            doc_data = parsed.get("document", {})
            print(f"DEBUG: document.data exists: {'data' in doc_data}")
            if "data" in doc_data:
                data = doc_data.get("data", {})
                print(f"DEBUG: data.item exists: {'item' in data}")
                if "item" in data:
                    items_preview = data.get("item", [])
                    print(f"DEBUG: data.item type: {type(items_preview)}, length: {len(items_preview) if isinstance(items_preview, list) else 'N/A'}")
        if "data" in parsed:
            top_data = parsed.get("data", {})
            print(f"DEBUG: top-level data.item exists: {'item' in top_data}")

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
    
    # XML 응답 처리 (document.data.item 구조)
    if "document" in parsed:
        document = parsed.get("document", {}) or {}
        # document 내부의 data 확인
        data = document.get("data", {})
        if isinstance(data, dict):
            error_code = str(data.get("error_code", "000"))
            if error_code not in ("0", "000"):
                error_msg = data.get("error_msg", "") or data.get("message", "")
                print(f"🚨 [REAL ERROR] KAMIS 오류 코드: {error_code}, 메시지: {error_msg}")
                raise HTTPException(status_code=502, detail=f"KAMIS 오류 코드: {error_code} - {error_msg}")
            # document.data.item 배열에서 실제 가격 데이터 가져오기
            items = _ensure_list(data.get("item"))
            print(f"DEBUG: Found {len(items)} items from 'document.data.item' key")
        
        # document.data에서 찾지 못한 경우, document 전체에서 재귀적으로 검색
        if not items:
            items = _collect_items(document)
            print(f"DEBUG: Found {len(items)} items from 'document' (recursive search)")
    
    # JSON 응답 처리 - 실제 데이터는 "data.item" 배열에 있음 (최상위 레벨)
    if not items and "data" in parsed:
        data = parsed.get("data", {})
        if isinstance(data, dict):
            error_code = str(data.get("error_code", "000"))
            if error_code not in ("0", "000"):
                error_msg = data.get("error_msg", "") or data.get("message", "")
                print(f"🚨 [REAL ERROR] KAMIS 오류 코드: {error_code}, 메시지: {error_msg}")
                raise HTTPException(status_code=502, detail=f"KAMIS 오류 코드: {error_code} - {error_msg}")
            # data.item 배열에서 실제 가격 데이터 가져오기
            items = _ensure_list(data.get("item"))
            if not items and isinstance(data.get("item"), list):
                items = data.get("item", [])
        print(f"DEBUG: Found {len(items)} items from top-level 'data.item' key")
    
    # 파싱된 응답이 비어있거나 예상과 다른 경우
    if not items:
        print(f"⚠️ [WARNING] KAMIS 응답 형식이 예상과 다릅니다. parsed keys: {list(parsed.keys()) if isinstance(parsed, dict) else 'NOT A DICT'}")
        # 최상위 레벨에서 item을 찾아봄
        if isinstance(parsed, dict) and "item" in parsed:
            items = _ensure_list(parsed.get("item"))
            print(f"DEBUG: Found {len(items)} items from top-level 'item' key")

    grade_prices: list[dict[str, Any]] = []
    grade_seen: set[str] = set()
    target_name = codes.get("food_nm", "")

    def _extract_grade(item_data: dict, product_name: str) -> str:
        """API 응답 데이터와 제품명에서 등급 정보 추출"""
        # 1. API 응답에서 직접 등급 정보 확인 (productrankcode, productrankname)
        productrankcode = item_data.get("productrankcode") or item_data.get("productrankcode") or ""
        productrankname = item_data.get("productrankname") or item_data.get("productrank") or ""
        
        # 등급코드를 등급명으로 매핑 (API는 "1", "2", "3" 형식으로 올 수 있음)
        if productrankcode:
            rankcode_str = str(productrankcode).strip()
            # "1" -> "01", "2" -> "02" 등으로 정규화
            rankcode_map = {"1": "01", "2": "02", "3": "03", "0": "00", "": "00"}
            normalized_code = rankcode_map.get(rankcode_str, rankcode_str.zfill(2))
            
            grade_code_map = {"00": "전체", "01": "1++등급", "02": "1+등급", "03": "1등급"}
            mapped_grade = grade_code_map.get(normalized_code)
            if mapped_grade:
                return mapped_grade
        
        # 등급명 직접 확인
        if productrankname:
            productrankname_str = str(productrankname).strip()
            grade_keywords = ["1++등급", "1+등급", "1등급", "2등급", "3등급", "전체"]
            for keyword in grade_keywords:
                if keyword in productrankname_str:
                    return keyword
        
        # 2. 제품명에서 등급 정보 추출
        if not product_name:
            return "일반"
        # 괄호 안의 등급 정보 추출 (예: "소/등심(1++등급)" -> "1++등급")
        if "(" in product_name and ")" in product_name:
            grade_in_paren = product_name.split("(", 1)[1].split(")", 1)[0]
            if grade_in_paren:
                return grade_in_paren
        # 등급 키워드 직접 검색
        grade_keywords = ["1++등급", "1+등급", "1등급", "2등급", "3등급", "전체"]
        for keyword in grade_keywords:
            if keyword in product_name:
                return keyword
        return "일반"

    def _trend_from_direction(value: Any) -> str:
        mapping = {"0": "down", "1": "up", "2": "flat"}
        return mapping.get(str(value).strip(), "flat")

    for item in items:
        if not isinstance(item, dict):
            continue
        
        # countyname 필터링: "평균", "평년" 제외하고 실제 지역명만 사용
        countyname = str(item.get("countyname", "")).strip()
        if countyname in ("평균", "평년", ""):
            # 전국 조회가 아닌 경우, 평균/평년 데이터는 제외
            if region != "전국":
                continue
        # 특정 지역 조회 시 해당 지역명과 일치하는 데이터만 사용
        elif region != "전국":
            region_name_map = {
                "서울": "서울", "부산": "부산", "대구": "대구", "인천": "인천",
                "광주": "광주", "대전": "대전", "울산": "울산", "세종": "세종",
                "수원": "수원", "강릉": "강릉", "춘천": "춘천", "청주": "청주",
                "전주": "전주", "포항": "포항", "제주": "제주", "의정부": "의정부",
                "순천": "순천", "안동": "안동", "창원": "창원", "용인": "용인",
                "성남": "성남", "고양": "고양", "천안": "천안", "김해": "김해",
            }
            expected_countyname = region_name_map.get(region, region)
            if countyname != expected_countyname:
                continue
        
        # periodRetailProductList API 응답: itemname="소", kindname="안심(100g)"
        # itemcode와 kindcode로 이미 정확한 부위를 필터링했으므로 제품명 매칭 불필요
        itemname_val = item.get("itemname")
        kindname_val = item.get("kindname")
        
        # 빈 배열이거나 리스트인 경우 처리
        if isinstance(itemname_val, list):
            itemname_val = itemname_val[0] if itemname_val else ""
        elif itemname_val is None:
            itemname_val = ""
        else:
            itemname_val = str(itemname_val).strip()
            
        if isinstance(kindname_val, list):
            kindname_val = kindname_val[0] if kindname_val else ""
        elif kindname_val is None:
            kindname_val = ""
        else:
            kindname_val = str(kindname_val).strip()
        
        # itemname과 kindname을 결합하여 제품명 생성 (예: "소/안심")
        if itemname_val and kindname_val:
            # kindname에서 단위 제거 (예: "안심(100g)" -> "안심")
            kindname_clean = kindname_val.split("(")[0].strip()
            product_name = f"{itemname_val}/{kindname_clean}"
        else:
            product_name = str(
                item.get("productName")
                or itemname_val
                or item.get("item_name")
                or kindname_val
                or item.get("productname")
                or ""
            )
        
        # itemcode와 kindcode로 이미 필터링된 데이터이므로 제품명 매칭 완전히 건너뛰기
        # periodRetailProductList는 itemcode/kindcode로 정확한 부위를 조회하므로
        # 추가 제품명 필터링 불필요
        unit = (item.get("unit") or "").lower()
        # JSON 응답에서는 단위 정보가 없을 수 있으므로 100g 체크 완화
        # 단위가 없거나 100g가 아닌 경우도 허용 (API 응답 형식에 따라 다를 수 있음)
        # 단, 명시적으로 다른 단위(kg 등)인 경우만 제외
        if unit and unit not in ("", "100g", "100g당", "100g/원") and "kg" in unit:
            continue
        raw_price = (
            item.get("price")
            or item.get("dpr1")
            or item.get("dpr0")
            or item.get("avgPrc")
            or item.get("value")  # 추가
            or item.get("priceValue")  # 추가
        )
        print(f"DEBUG: Item | name={product_name} | price={raw_price} | unit={item.get('unit', 'N/A')}")
        try:
            price_value = int(float(str(raw_price).replace(",", "")))
        except (TypeError, ValueError):
            price_value = 0
        if price_value <= 0:
            print(f"DEBUG: 가격이 0 이하이므로 스킵 | price={raw_price}")
            continue
        
        # 등급 정보 추출 (API 응답 데이터 포함)
        grade = _extract_grade(item, product_name)
        
        # 등급 필터링: periodRetailProductList는 이미 p_productrankcode로 필터링된 결과를 반환
        # 따라서 각 아이템의 등급 필터링은 완화 (API 요청 시 이미 필터링됨)
        if grade_code != "00":  # 전체 평균이 아닌 경우
            # API 요청 시 이미 등급으로 필터링되었으므로, 응답의 모든 아이템이 해당 등급
            # 다만 명시적으로 다른 등급이 표시된 경우만 제외
            grade_code_map = codes.get("grade_codes", {})
            target_grade_name = grade_code_map.get(grade_code, "")
            
            # API 응답의 productrankcode 확인 (있으면 우선 사용)
            item_productrankcode = str(item.get("productrankcode", "")).strip()
            if item_productrankcode:
                rankcode_map = {"1": "01", "2": "02", "3": "03", "0": "00", "": "00"}
                normalized_code = rankcode_map.get(item_productrankcode, item_productrankcode.zfill(2))
                # 등급코드가 명시적으로 다르면 제외 (단, 빈 문자열이나 "0"은 전체 평균이므로 허용)
                if normalized_code and normalized_code != "00" and normalized_code != grade_code:
                    print(f"DEBUG: 등급코드 불일치 스킵 | 선택한 등급코드={grade_code} | API 등급코드={item_productrankcode}(정규화={normalized_code})")
                    continue
            # 등급명으로 확인 (fallback) - 명시적으로 다른 등급인 경우만 제외
            elif target_grade_name and grade:
                # 등급명이 명시적으로 다르고, "일반"이 아닌 경우만 제외
                if grade != "일반" and target_grade_name not in grade and grade not in target_grade_name:
                    # 예: "1++등급" vs "1+등급" 같은 경우는 제외
                    if any(g in grade for g in ["1++등급", "1+등급", "1등급", "2등급", "3등급"]):
                        print(f"DEBUG: 등급명 불일치 스킵 | 선택한 등급={target_grade_name} | 실제 등급={grade}")
                        continue
        
        if grade in grade_seen:
            continue
        grade_seen.add(grade)
        # API 응답에서 실제 날짜 추출 및 정규화
        # KAMIS API는 regday가 "02/06" 형식(MM/DD)이고 yyyy 필드가 별도로 제공됨
        yyyy_field = str(item.get("yyyy", "")).strip()
        regday_raw = item.get("regday") or item.get("lastest_day") or ""
        
        price_date = None
        if regday_raw:
            regday_str = str(regday_raw).strip()
            # 케이스 1: "02/06" 형식 (MM/DD) - yyyy 필드 필수 사용
            if "/" in regday_str:
                parts = regday_str.split("/")
                if len(parts) == 2 and yyyy_field:
                    # MM/DD 형식이면 yyyy 필드와 결합
                    price_date = f"{yyyy_field}-{parts[0].zfill(2)}-{parts[1].zfill(2)}"
                elif len(parts) == 3:
                    # "2025/02/06" 형식
                    price_date = "-".join(parts)
            # 케이스 2: "2025-02-06" 형식
            elif "-" in regday_str and len(regday_str) >= 10:
                price_date = regday_str[:10]
            # 케이스 3: "20250206" 형식 (8자리 숫자)
            elif len(regday_str) == 8 and regday_str.isdigit():
                price_date = f"{regday_str[:4]}-{regday_str[4:6]}-{regday_str[6:8]}"
        
        # 날짜 검증 및 오늘 이후 필터링
        today = date.today()
        yesterday = today - timedelta(days=1)
        if price_date:
            try:
                date_obj = datetime.strptime(price_date[:10], "%Y-%m-%d").date()
                # 오늘 날짜를 넘어가는 데이터는 제외 (어제까지만 유효)
                if date_obj > yesterday:
                    logger.debug(f"날짜 필터링: {price_date}는 어제({yesterday}) 이후이므로 제외")
                    continue  # 이 아이템은 건너뛰기
                # 2000년 이전이나 2100년 이후의 비정상적인 날짜 제외
                elif date_obj.year < 2000 or date_obj.year > 2100:
                    logger.warning(f"비정상적인 날짜: {price_date} (년도: {date_obj.year}), 제외")
                    continue  # 이 아이템은 건너뛰기
                # API 응답의 실제 날짜를 그대로 사용 (어제보다 오래된 날짜도 유지)
            except (ValueError, TypeError) as e:
                logger.warning(f"날짜 파싱 실패: {price_date}, 에러: {e}, 제외")
                continue  # 이 아이템은 건너뛰기
        else:
            # 날짜가 없으면 제외
            logger.debug("날짜 정보가 없는 아이템 제외")
            continue
        
        grade_prices.append(
            {
                "grade": grade,
                "price": price_value,
                "unit": "100g",
                "priceDate": price_date,
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

    # 가장 최근 날짜 찾기 (API 응답의 실제 날짜 사용)
    def parse_date(date_str: str) -> date | None:
        """날짜 문자열을 date 객체로 변환"""
        if not date_str:
            return None
        try:
            # "YYYY-MM-DD" 형식만 처리
            date_str = str(date_str).strip()
            if len(date_str) >= 10:
                return datetime.strptime(date_str[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            pass
        return None
    
    # API 응답의 실제 최신 날짜 찾기
    today = date.today()
    yesterday = today - timedelta(days=1)
    latest_date = None
    latest_prices = []
    
    for gp in grade_prices:
        price_date = parse_date(gp.get("priceDate", ""))
        if price_date:
            # 오늘 날짜를 넘어가는 데이터는 제외 (어제까지만 유효)
            if price_date > yesterday:
                continue
            # API 응답의 실제 날짜 중 가장 최신 날짜 찾기
            if latest_date is None or price_date > latest_date:
                latest_date = price_date
                latest_prices = [gp]
            elif price_date == latest_date:
                latest_prices.append(gp)
    
    # 최근 날짜 데이터가 없으면 모든 데이터 중 가장 최신 날짜 찾기
    if not latest_prices or latest_date is None:
        # 모든 가격 중 가장 최근 날짜 찾기
        for gp in grade_prices:
            price_date = parse_date(gp.get("priceDate", ""))
            if price_date:
                if latest_date is None or price_date > latest_date:
                    latest_date = price_date
                    latest_prices = [gp]
                elif price_date == latest_date:
                    latest_prices.append(gp)
        
        # 여전히 날짜를 찾지 못한 경우 첫 번째 항목 사용
        if latest_date is None:
            if grade_prices:
                latest_prices = [grade_prices[0]]
                latest_date = parse_date(grade_prices[0].get("priceDate", ""))
    
    grade_order = {grade: idx for idx, grade in enumerate(codes.get("grades", []))}
    latest_prices.sort(key=lambda x: grade_order.get(x["grade"], 99))
    debug_summary = ", ".join(f"{gp['grade']}:{gp['price']}" for gp in latest_prices)
    print(f"DEBUG: REAL API PARSED KAMIS | gradeCode={grade_code} | latestDate={latest_date} | gradePrices=[{debug_summary}]")
    
    # 등급코드에 맞는 가격 선택
    primary = None
    if grade_code == "00":
        # 전체 평균: 모든 등급의 평균 계산
        if latest_prices:
            avg_price = sum(gp["price"] for gp in latest_prices) / len(latest_prices)
            primary = {
                "grade": "전체 평균",
                "price": int(avg_price),
                "unit": latest_prices[0]["unit"],
                "priceDate": str(latest_date) if latest_date else latest_prices[0]["priceDate"],
                "trend": latest_prices[0]["trend"],
            }
            print(f"DEBUG: 전체 평균 계산 | 평균가격={primary['price']}원 (등급 수={len(latest_prices)}, 날짜={latest_date})")
        else:
            primary = latest_prices[0] if latest_prices else None
    else:
        # 특정 등급 선택: grade_code에 해당하는 등급 찾기
        grade_code_map = codes.get("grade_codes", {})
        target_grade_name = grade_code_map.get(grade_code, "")
        
        # 등급명으로 정확히 매칭 (예: "1++등급", "1+등급", "1등급")
        # 정확한 매칭 우선, 부분 매칭은 후순위
        exact_match = None
        partial_match = None
        
        for gp in latest_prices:
            grade_name = gp.get("grade", "")
            # 정확한 매칭 (예: "1++등급" == "1++등급")
            if target_grade_name and grade_name == target_grade_name:
                exact_match = gp
                break
            # 부분 매칭 (예: "1++등급" in "안심 1++등급")
            elif target_grade_name and target_grade_name in grade_name and not partial_match:
                partial_match = gp
        
        if exact_match:
            primary = exact_match
            primary["priceDate"] = str(latest_date) if latest_date else primary["priceDate"]
        elif partial_match:
            primary = partial_match
            primary["priceDate"] = str(latest_date) if latest_date else primary["priceDate"]
            print(f"⚠️ [WARNING] 등급코드 {grade_code} 부분 매칭: {primary['grade']}")
        elif latest_prices:
            # 매칭 실패 시 첫 번째 항목 사용
            primary = latest_prices[0]
            primary["priceDate"] = str(latest_date) if latest_date else primary["priceDate"]
            print(f"⚠️ [WARNING] 등급코드 {grade_code}에 해당하는 등급을 찾지 못함. 첫 번째 항목 사용: {primary['grade']}")
    
    if not primary:
        target_label = codes.get("food_nm") or part_name
        raise HTTPException(
            status_code=404,
            detail=f"{target_label} 실시간 데이터를 알 수 없습니다.",
        )
    
    # 최종 날짜: API 응답의 실제 최신 날짜 사용
    final_date = latest_date if latest_date else yesterday
    
    return {
        "currentPrice": primary["price"],
        "unit": primary["unit"],
        "trend": primary["trend"],
        "price_date": str(final_date),  # API 응답의 실제 날짜 사용
        "source": "api",
        "gradePrices": latest_prices,
        "selectedGrade": primary.get("grade", "일반"),
    }


async def fetch_kamis_price_period(
    part_name: str,
    region: str = "전국",
    grade_code: str = "00",
    months: int | None = None,
    weeks: int | None = 6,
) -> list[dict[str, Any]]:
    """
    KAMIS 기간별 시세 조회 (periodProductList: p_startday, p_endday, p_itemcode, p_kindcode 등).
    주별 그래프용: weeks 지정 시 최근 N주 일별 데이터 반환. months 지정 시 기존 월별 구간.
    Returns: [ {"date": "2025-01-15", "price": 12000}, ... ]
    """
    key = (settings.kamis_api_key or "").strip()
    cert_id = (settings.kamis_cert_id or "pak101044").strip()
    if not key:
        raise HTTPException(status_code=503, detail="KAMIS API 키가 설정되지 않았습니다.")

    base = (settings.kamis_api_url or "https://www.kamis.or.kr/service/price/xml.do").strip()
    today = date.today()
    # API는 어제 날짜까지만 데이터가 있으므로 어제 날짜를 end_day로 사용
    yesterday = today - timedelta(days=1)
    end_day = yesterday.strftime("%Y-%m-%d")
    if weeks is not None and weeks > 0:
        days = min(weeks * 7, 365)
    else:
        days = min((months or 6) * 31, 365)
    start_day = (yesterday - timedelta(days=days)).strftime("%Y-%m-%d")

    codes = _get_codes(part_name)
    if (part_name not in PART_TO_CODES and codes.get("food_nm") == part_name) or not codes.get("itemcode"):
        raise HTTPException(
            status_code=404,
            detail=f"{part_name} 기간 데이터를 알 수 없습니다.",
        )

    # 지역코드 매핑 (fetch_kamis_price와 동일)
    region_code_map = {
        "전국": "",
        "서울": "1101",
        "부산": "2100",
        "대구": "2200",
        "인천": "2300",
        "광주": "2401",
        "대전": "2501",
        "울산": "2601",
        "세종": "2701",
        "수원": "3111",
        "강릉": "3214",
        "춘천": "3211",
        "청주": "3311",
        "전주": "3511",
        "포항": "3711",
        "제주": "3911",
        "의정부": "3113",
        "순천": "3613",
        "안동": "3714",
        "창원": "3814",
        "용인": "3145",
        "성남": "3112",
        "고양": "3138",
        "천안": "3411",
        "김해": "3818",
    }
    county_code = region_code_map.get(region, region)
    
    # 등급코드 처리: 소고기만 등급 구분이 있음, 돼지는 항상 전체 평균
    is_beef = part_name.startswith("Beef_")
    if is_beef:
        # 소고기: 등급코드 "00" (전체 평균)일 때는 빈 문자열, 아니면 해당 등급코드 사용
        product_rank_code = "" if grade_code == "00" else grade_code
    else:
        # 돼지: 항상 전체 평균 (등급 구분 없음)
        product_rank_code = ""

    params = {
        "action": "periodRetailProductList",  # 소매가격 조회 액션
        "p_cert_key": key,
        "p_cert_id": cert_id,
        "p_returntype": "xml",  # XML 형식 사용
        "p_startday": start_day,
        "p_endday": end_day,
        "p_itemcategorycode": codes.get("category", "500"),  # 품목카테고리코드 추가
        "p_itemcode": codes.get("itemcode", ""),
        "p_kindcode": codes.get("kindcode", ""),
        "p_productrankcode": product_rank_code,  # 등급코드 (소고기만 사용, 돼지는 항상 빈 문자열)
        "p_countrycode": county_code,  # 지역코드 (p_countrycode 사용)
        "p_convert_kg_yn": "N",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            req = client.build_request("GET", base, params=params)
            resp = await client.send(req)
            resp.raise_for_status()
            payload = resp.text
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=503, detail=f"KAMIS API 연결 실패: HTTP {exc.response.status_code}") from exc
    except Exception as exc:
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
        data = document.get("data", {})
        if isinstance(data, dict) and str(data.get("error_code", "000")) in ("0", "000"):
            items = _ensure_list(data.get("item"))
        if not items:
            items = _collect_items(document)
    if not items and "data" in parsed:
        data = parsed.get("data", {})
        if isinstance(data, dict) and str(data.get("error_code", "000")) in ("0", "000"):
            items = _ensure_list(data.get("item"))
    if not items and isinstance(parsed, dict) and "item" in parsed:
        items = _ensure_list(parsed.get("item"))

    target_name = codes.get("food_nm", "")
    result: list[dict[str, Any]] = []
    seen_dates: set[str] = set()
    today = date.today()

    for item in items:
        if not isinstance(item, dict):
            continue
        
        # countyname 필터링: "평균", "평년" 제외하고 실제 지역명만 사용
        countyname = str(item.get("countyname", "")).strip()
        if countyname in ("평균", "평년", ""):
            # 전국 조회가 아닌 경우, 평균/평년 데이터는 제외
            if region != "전국":
                continue
        # 특정 지역 조회 시 해당 지역명과 일치하는 데이터만 사용
        elif region != "전국":
            region_name_map = {
                "서울": "서울", "부산": "부산", "대구": "대구", "인천": "인천",
                "광주": "광주", "대전": "대전", "울산": "울산", "세종": "세종",
                "수원": "수원", "강릉": "강릉", "춘천": "춘천", "청주": "청주",
                "전주": "전주", "포항": "포항", "제주": "제주", "의정부": "의정부",
                "순천": "순천", "안동": "안동", "창원": "창원", "용인": "용인",
                "성남": "성남", "고양": "고양", "천안": "천안", "김해": "김해",
            }
            expected_countyname = region_name_map.get(region, region)
            if countyname != expected_countyname:
                continue
        
        raw_price = (
            item.get("price")
            or item.get("dpr1")
            or item.get("dpr0")
            or item.get("avgPrc")
            or item.get("value")
            or item.get("priceValue")
        )
        try:
            price_value = int(float(str(raw_price).replace(",", "")))
        except (TypeError, ValueError):
            price_value = 0
        if price_value <= 0:
            continue
        # 날짜 추출: KAMIS API는 regday가 "02/06" 형식(MM/DD)이고 yyyy 필드가 별도로 제공됨
        yyyy = str(item.get("yyyy", "")).strip()
        regday_raw = item.get("regday") or item.get("lastest_day") or ""
        
        if not regday_raw or not isinstance(regday_raw, str):
            continue
        
        regday_str = str(regday_raw).strip()
        regday = None
        
        # 날짜 형식 정규화
        # 케이스 1: "02/06" 형식 (MM/DD) - yyyy 필드 필수 사용
        if "/" in regday_str:
            parts = regday_str.split("/")
            if len(parts) == 2 and yyyy:
                # MM/DD 형식이면 yyyy 필드와 결합
                regday = f"{yyyy}-{parts[0].zfill(2)}-{parts[1].zfill(2)}"
            elif len(parts) == 3:
                # "2025/02/06" 형식
                regday = "-".join(parts)
            else:
                continue
        
        # 케이스 2: "20250206" 형식 (8자리 숫자)
        elif len(regday_str) == 8 and regday_str.isdigit():
            regday = f"{regday_str[:4]}-{regday_str[4:6]}-{regday_str[6:8]}"
        
        # 케이스 3: 이미 "YYYY-MM-DD" 형식
        elif "-" in regday_str and len(regday_str) >= 10:
            regday = regday_str[:10]
        
        # 날짜 형식 검증
        if not regday or len(regday) < 10:
            continue
        
        # 중복 날짜 체크
        if regday in seen_dates:
            continue
        
        # 날짜 파싱 및 오늘 이후 날짜 필터링
        try:
            date_obj = datetime.strptime(regday[:10], "%Y-%m-%d").date()
            # 오늘 날짜를 넘어가는 데이터는 제외
            if date_obj > today:
                logger.debug(f"날짜 필터링: {regday}는 오늘({today}) 이후이므로 제외")
                continue
            # 2000년 이전이나 2100년 이후의 비정상적인 날짜 제외
            if date_obj.year < 2000 or date_obj.year > 2100:
                logger.warning(f"비정상적인 날짜: {regday} (년도: {date_obj.year})")
                continue
        except (ValueError, TypeError) as e:
            logger.warning(f"날짜 파싱 실패: {regday}, 에러: {e}")
            continue
        
        seen_dates.add(regday)
        result.append({"date": regday, "price": price_value})

    result.sort(key=lambda x: x["date"])
    return result


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

    async def fetch_current_price(
        self,
        part_name: str,
        region: str = "전국",
        grade_code: str = "00",
    ) -> dict[str, Any]:
        """KAMIS API로 시세 조회."""
        return await fetch_kamis_price(part_name, region, grade_code)


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

