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
from collections import defaultdict
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

# 등급코드 매핑 (KAMIS API용) - 통합 매핑 테이블
# UI 카테고리: 등급 -> p_productrankcode
GRADE_CODE_MAP: dict[str, str] = {
    "00": "전체",  # 전체 평균
    "01": "1++등급",
    "02": "1+등급",
    "03": "1등급",
    "04": "2등급",
    "05": "3등급",
    "06": "등외",
    "81": "미국산",  # 수입 소고기
    "82": "호주산",  # 수입 소고기
}

# KAMIS 매핑 데이터 (데이터 기반 매핑 테이블) - _get_codes fallback용
# 등급 코드: 01(1++), 02(1+), 03(1), 04(2), 05(3), 06(등외)
# 주의: PART_TO_CODES가 우선 사용되며, KAMIS_MAP은 fallback으로만 사용
# 실제로는 PART_TO_CODES에 모든 데이터가 포함되어 있어 거의 사용되지 않음
KAMIS_MAP: dict[str, dict[str, Any]] = {
    "소안심": {"item": "4301", "kind": "21", "ranks": {"일반": "00", "1++": "01", "1+": "02", "1": "03", "2": "04", "3": "05", "등외": "06"}},
    "소등심": {"item": "4301", "kind": "22", "ranks": {"일반": "00", "1++": "01", "1+": "02", "1": "03", "2": "04", "3": "05", "등외": "06"}},
    "소설도": {"item": "4301", "kind": "36", "ranks": {"일반": "00", "1++": "01", "1+": "02", "1": "03", "2": "04", "3": "05", "등외": "06"}},
    "소양지": {"item": "4301", "kind": "40", "ranks": {"일반": "00", "1++": "01", "1+": "02", "1": "03", "2": "04", "3": "05", "등외": "06"}},
    "소갈비": {"item": "4301", "kind": "50", "ranks": {"일반": "00", "1++": "01", "1+": "02", "1": "03", "2": "04", "3": "05", "등외": "06"}},
    "돼지앞다리": {"item": "4304", "kind": "25", "ranks": {"일반": "00"}},
    "돼지삼겹살": {"item": "4304", "kind": "27", "ranks": {"일반": "00"}},
    "돼지갈비": {"item": "4304", "kind": "28", "ranks": {"일반": "00"}},
    "돼지목심": {"item": "4304", "kind": "68", "ranks": {"일반": "00"}},
    "수입소양지_미국": {"item": "4401", "kind": "29", "ranks": {"냉장": "81"}},
    "수입소양지_호주": {"item": "4401", "kind": "29", "ranks": {"냉장": "82"}},
    "수입소갈비": {"item": "4401", "kind": "31", "ranks": {"일반": "00", "미국": "81", "호주": "82"}},
    "수입돼지삼겹살": {"item": "4402", "kind": "27", "ranks": {"일반": "00"}},
}

# UI 카테고리 매핑 (4개 항목: 지역/품목/품종/등급)
# 지역: REGION_CODE_MAP 사용 (p_countrycode)
# 품목: PART_TO_CODES의 itemcode 사용 (p_itemcode: 4301=소, 4304=돼지)
# 품종: PART_TO_CODES의 kindcode 사용 (p_kindcode: 21=안심, 22=등심 등)
# 등급: GRADE_CODE_MAP 사용 (p_productrankcode: 01=1++, 02=1+, 03=1 등)

# 지역명-지역코드 매핑 테이블 (KAMIS API용)
REGION_CODE_MAP: dict[str, str] = {
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
    "성남": "3112",
    "의정부": "3113",
    "용인": "3145",
    "고양": "3138",
    "춘천": "3211",
    "강릉": "3214",
    "청주": "3311",
    "천안": "3411",
    "전주": "3511",
    "군산": "3512",
    "순천": "3613",
    "목포": "3611",
    "포항": "3711",
    "안동": "3714",
    "창원": "3814",
    "마산": "3811",
    "김해": "3818",
    "제주": "3911",
    "온라인": "9998",
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
    # 수입 소고기 - itemcode 4401
    "Import_Beef_Brisket_US": {
        "itemcode": "4401",
        "kindcode": "29",
        "category": "500",
        "food_nm": "수입 소고기/양지(냉장)",
        "grades": ["미국산"],
        "grade_codes": {"81": "미국산"},
    },
    "Import_Beef_Brisket_AU": {
        "itemcode": "4401",
        "kindcode": "29",
        "category": "500",
        "food_nm": "수입 소고기/양지(냉장)",
        "grades": ["호주산"],
        "grade_codes": {"82": "호주산"},
    },
    "Import_Beef_Rib": {
        "itemcode": "4401",
        "kindcode": "31",
        "category": "500",
        "food_nm": "수입 소고기/갈비",
        "grades": ["전체", "미국산", "호주산"],
        "grade_codes": {"00": "전체", "81": "미국산", "82": "호주산"},
    },
    "Import_Beef_Rib_US": {
        "itemcode": "4401",
        "kindcode": "31",
        "category": "500",
        "food_nm": "수입 소고기/갈비",
        "grades": ["미국산"],
        "grade_codes": {"81": "미국산"},
    },
    "Import_Beef_Rib_AU": {
        "itemcode": "4401",
        "kindcode": "31",
        "category": "500",
        "food_nm": "수입 소고기/갈비",
        "grades": ["호주산"],
        "grade_codes": {"82": "호주산"},
    },
    "Import_Beef_Ribeye_US": {
        "itemcode": "4401",
        "kindcode": "37",
        "category": "500",
        "food_nm": "수입 소고기/갈비살",
        "grades": ["미국산"],
        "grade_codes": {"81": "미국산"},
    },
    "Import_Beef_Ribeye_AU": {
        "itemcode": "4401",
        "kindcode": "37",
        "category": "500",
        "food_nm": "수입 소고기/갈비살",
        "grades": ["호주산"],
        "grade_codes": {"82": "호주산"},
    },
    "Import_Beef_ChuckEye_US": {
        "itemcode": "4401",
        "kindcode": "62",
        "category": "500",
        "food_nm": "수입 소고기/척아이롤(냉장)",
        "grades": ["미국산"],
        "grade_codes": {"81": "미국산"},
    },
    "Import_Beef_ChuckEye_AU": {
        "itemcode": "4401",
        "kindcode": "62",
        "category": "500",
        "food_nm": "수입 소고기/척아이롤(냉장)",
        "grades": ["호주산"],
        "grade_codes": {"82": "호주산"},
    },
    "Import_Beef_ChuckEye_Frozen_US": {
        "itemcode": "4401",
        "kindcode": "68",
        "category": "500",
        "food_nm": "수입 소고기/척아이롤(냉동)",
        "grades": ["미국산"],
        "grade_codes": {"81": "미국산"},
    },
    "Import_Beef_ChuckEye_Frozen_AU": {
        "itemcode": "4401",
        "kindcode": "68",
        "category": "500",
        "food_nm": "수입 소고기/척아이롤(냉동)",
        "grades": ["호주산"],
        "grade_codes": {"82": "호주산"},
    },
    # 수입 돼지고기 - itemcode 4402
    "Import_Pork_Belly": {
        "itemcode": "4402",
        "kindcode": "27",
        "category": "500",
        "food_nm": "수입 돼지고기/삼겹살",
        "grades": ["전체"],
        "grade_codes": {"00": "전체"},
    },
}


def _get_codes(part_name: str) -> dict[str, Any]:
    """부위명으로 KAMIS 코드 조회 (PART_TO_CODES 우선, KAMIS_MAP fallback)"""
    if part_name in PART_TO_CODES:
        data = PART_TO_CODES[part_name].copy()
        data.setdefault("grades", ["일반"])
        data.setdefault("grade_codes", {"00": "전체"})
        return data
    
    # KAMIS_MAP에서 검색 (한글명 기반)
    part_name_clean = (part_name or "").replace("/", "").replace("_", "").replace(" ", "")
    for kamis_key, kamis_data in KAMIS_MAP.items():
        if kamis_key in part_name_clean or part_name_clean in kamis_key:
            # KAMIS_MAP 데이터를 PART_TO_CODES 형식으로 변환
            ranks = kamis_data.get("ranks", {})
            grade_codes = {}
            grades = []
            for rank_name, rank_code in ranks.items():
                if rank_code == "00":
                    grade_codes[rank_code] = "전체"
                    grades.append("전체")
                elif rank_code == "01":
                    grade_codes[rank_code] = "1++등급"
                    grades.append("1++등급")
                elif rank_code == "02":
                    grade_codes[rank_code] = "1+등급"
                    grades.append("1+등급")
                elif rank_code == "03":
                    grade_codes[rank_code] = "1등급"
                    grades.append("1등급")
                else:
                    grade_codes[rank_code] = rank_name
                    grades.append(rank_name)
            
            return {
                "itemcode": kamis_data.get("item", ""),
                "kindcode": kamis_data.get("kind", ""),
                "category": "500",
                "food_nm": part_name,
                "grades": grades if grades else ["일반"],
                "grade_codes": grade_codes if grade_codes else {"00": "전체"},
            }
    
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
    KAMIS API로 실시간 시세 조회 (주별 그래프 로직 기반)
    
    Args:
        part_name: 고기 부위명 (예: "Beef_Tenderloin", "소/안심")
        region: 지역명 (예: "서울", "전국") -> p_countrycode로 변환
        grade_code: 등급코드 (예: "00"=전체, "01"=1++, "02"=1+, "03"=1) -> p_periodProductList로 변환
    
    Returns:
        {
            "currentPrice": int,
            "unit": str,
            "trend": str,
            "price_date": str,
            "source": str,
            "gradePrices": list,
            "selectedGrade": str
        }
    """
    # 주별 그래프 로직을 사용하여 최신 날짜의 데이터만 추출
    # 기간 조회를 통해 최근 7일 데이터를 가져온 후, 최신 날짜의 데이터만 선택
    period_data = await fetch_kamis_price_period(
        part_name=part_name,
        region=region,
        grade_code=grade_code,
        weeks=1,  # 최근 1주일 데이터만 조회
    )
    
    if not period_data:
        target_label = _get_codes(part_name).get("food_nm") or part_name
        raise HTTPException(
            status_code=404,
            detail=f"{target_label} 실시간 데이터를 알 수 없습니다.",
        )
    
    # 최신 날짜의 데이터 선택 (주별 그래프 로직에서 이미 최신 날짜만 반환됨)
    # period_data는 날짜 순으로 정렬되어 있으므로 마지막 항목이 최신
    latest_item = period_data[-1] if period_data else None
    
    if not latest_item:
        target_label = _get_codes(part_name).get("food_nm") or part_name
        raise HTTPException(
            status_code=404,
            detail=f"{target_label} 실시간 데이터를 알 수 없습니다.",
        )
    
    # 등급별 가격 정보 생성 (전체 등급일 경우)
    codes = _get_codes(part_name)
    grade_prices: list[dict[str, Any]] = []
    
    if grade_code == "00":
        # 전체 등급일 경우: 국내 소고기만 각 등급별로 별도 조회하여 등급별 가격 수집
        # 수입 소고기는 등급이 없으므로 등급별 조회 불필요
        grade_codes_to_fetch = ["01", "02", "03"] if part_name.startswith("Beef_") else []
        
        for gc in grade_codes_to_fetch:
            try:
                grade_period = await fetch_kamis_price_period(
                    part_name=part_name,
                    region=region,
                    grade_code=gc,
                    weeks=1,
                )
                if grade_period:
                    grade_item = grade_period[-1]
                    grade_code_map = codes.get("grade_codes", {})
                    grade_name = grade_code_map.get(gc, f"{gc}등급")
                    grade_prices.append({
                        "grade": grade_name,
                        "price": grade_item["price"],
                        "unit": "100g",
                        "priceDate": grade_item["date"],
                        "trend": "flat",
                    })
            except Exception:
                continue
        
        # 전체 평균 계산
        if grade_prices:
            avg_price = sum(gp["price"] for gp in grade_prices) / len(grade_prices)
            primary_price = int(avg_price)
        else:
            primary_price = latest_item["price"]
    else:
        # 특정 등급: 현재 조회 결과 사용
        grade_code_map = codes.get("grade_codes", {})
        grade_name = grade_code_map.get(grade_code, "일반")
        grade_prices = [{
            "grade": grade_name,
            "price": latest_item["price"],
            "unit": "100g",
            "priceDate": latest_item["date"],
            "trend": "flat",
        }]
        primary_price = latest_item["price"]
    
    return {
        "currentPrice": primary_price,
        "unit": "100g",
        "trend": "flat",
        "price_date": latest_item["date"],
        "source": "api",
        "gradePrices": grade_prices,
        "selectedGrade": grade_prices[0]["grade"] if grade_prices else "일반",
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

    # 지역코드 매핑 (REGION_CODE_MAP 사용)
    county_code = REGION_CODE_MAP.get(region, region)
    
    # 등급코드 처리: 국내 소고기만 등급 구분이 있음, 돼지는 항상 전체 평균(00)
    # 사용자 제공 표에 따르면: 소 안심 00(전체), 01(1++등급), 02(1+등급), 03(1등급)
    # 수입 소고기: 00(전체), 81(미국산), 82(호주산) - 등급이 아니라 원산지
    # 돼지는 등급이 없으므로 항상 전체 평균
    is_domestic_beef = part_name.startswith("Beef_")  # 국내 소고기만
    is_import_beef = part_name.startswith("Import_Beef_")
    is_pork = part_name.startswith("Pork_") or part_name.startswith("Import_Pork_")
    
    if is_import_beef:
        # 수입 소고기: 등급코드 그대로 사용 (00=전체, 81=미국산, 82=호주산)
        # part_name에 이미 등급 정보가 포함되어 있으면 그대로 사용, 아니면 grade_code 사용
        if "_US" in part_name:
            product_rank_code = "81"  # 미국산
        elif "_AU" in part_name:
            product_rank_code = "82"  # 호주산
        else:
            product_rank_code = grade_code  # "00", "81", "82"
    elif is_domestic_beef:
        # 국내 소고기만: 등급코드 그대로 사용 (00=전체 평균, 01=1++등급, 02=1+등급, 03=1등급)
        product_rank_code = grade_code  # "00", "01", "02", "03" 모두 그대로 전달
    elif is_pork:
        # 돼지(국내/수입): 항상 전체 평균 (등급 구분 없음) - 빈 문자열
        product_rank_code = ""
    else:
        # 기본값: 등급코드 그대로 사용
        product_rank_code = grade_code

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
        "p_periodProductList": product_rank_code,  # 등급코드 (소고기: 00/01/02/03, 돼지: 빈 문자열)
        "p_countrycode": county_code,  # 지역코드 (p_countrycode 사용)
        "p_convert_kg_yn": "N",
    }
    
    # 디버그: 등급 파라미터 전달 확인
    print(f"DEBUG: fetch_kamis_price_period | part_name={part_name} | region={region} | grade_code={grade_code} | product_rank_code={product_rank_code}")
    print(f"DEBUG: API PARAMS | itemcode={params['p_itemcode']} | kindcode={params['p_kindcode']} | p_periodProductList={params['p_periodProductList']} | countrycode={params['p_countrycode']}")

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            req = client.build_request("GET", base, params=params)
            print(f"DEBUG: KAMIS API 요청 URL: {req.url}")
            resp = await client.send(req)
            resp.raise_for_status()
            payload = resp.text
            print(f"DEBUG: KAMIS API 응답 길이: {len(payload)} bytes")
            # 응답의 첫 1000자만 출력 (너무 길면 잘림)
            if len(payload) > 1000:
                print(f"DEBUG: KAMIS API 응답 미리보기: {payload[:1000]}...")
            else:
                print(f"DEBUG: KAMIS API 응답: {payload}")
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
    
    # 디버그: 파싱된 items의 첫 3개 항목 확인
    if items:
        print(f"DEBUG: 파싱된 items 수: {len(items)}")
        for idx, item in enumerate(items[:3], 1):
            if isinstance(item, dict):
                print(f"DEBUG: Item[{idx}] | productrankcode={item.get('productrankcode', 'N/A')} | countyname={item.get('countyname', 'N/A')} | price={item.get('price', 'N/A')} | itemname={item.get('itemname', 'N/A')} | kindname={item.get('kindname', 'N/A')}")
    else:
        print(f"DEBUG: ⚠️ 파싱된 items가 없음")

    target_name = codes.get("food_nm", "")
    # 날짜별로 그룹화하여 각 날짜의 가장 최신 항목만 선택 (실시간 가격 정보와 동일한 로직)
    by_date: dict[str, list[tuple[dict[str, Any], str, int]]] = defaultdict(list)  # 날짜 -> [(item, countyname, price), ...]
    today = date.today()
    
    # Forward Fill을 위한 마지막 가격 저장
    last_price: int | None = None
    
    # 등급 필터링: 국내 소고기만 등급별 필터링 적용
    is_domestic_beef_for_filter = part_name.startswith("Beef_")
    
    print(f"DEBUG: fetch_kamis_price_period 등급 필터링 | part_name={part_name} | grade_code={grade_code} | is_domestic_beef={is_domestic_beef_for_filter} | product_rank_code={product_rank_code}")
    print(f"DEBUG: API 응답 items 수: {len(items)}")

    for item in items:
        if not isinstance(item, dict):
            continue
        
        # 등급 필터링: 국내 소고기이고 특정 등급을 요청한 경우
        # 주의: p_periodProductList 파라미터로 이미 등급별로 필터링된 데이터가 올 수 있지만,
        # API 응답에서 productrankcode가 없거나 다른 형식일 수 있으므로 완화된 필터링 적용
        if is_domestic_beef_for_filter and grade_code != "00" and product_rank_code != "00":
            item_productrankcode = str(item.get("productrankcode", "")).strip()
            # "1" -> "01", "2" -> "02" 등으로 정규화
            rankcode_map = {"1": "01", "2": "02", "3": "03", "0": "00", "": "00"}
            normalized_item_code = rankcode_map.get(item_productrankcode, item_productrankcode.zfill(2) if item_productrankcode else "00")
            
            # 등급코드가 명시적으로 다르면 스킵 (빈 문자열이나 "00"은 전체 평균이므로 허용하지 않음)
            if item_productrankcode and normalized_item_code != "00" and normalized_item_code != product_rank_code:
                print(f"DEBUG: 등급 필터링 스킵 | 요청등급={product_rank_code} | API등급코드={item_productrankcode}(정규화={normalized_item_code}) | price={item.get('price', 'N/A')}")
                continue
            # productrankcode가 없거나 "00"인 경우: p_periodProductList로 이미 필터링되었으므로 통과
            # (API가 p_periodProductList 파라미터로 이미 등급별로 필터링된 데이터를 반환)
            elif not item_productrankcode or normalized_item_code == "00":
                print(f"DEBUG: 등급 필터링 통과 (productrankcode 없음/00) | 요청등급={product_rank_code} | API등급코드={item_productrankcode} | price={item.get('price', 'N/A')} | p_periodProductList로 이미 필터링됨")
            else:
                print(f"DEBUG: 등급 필터링 통과 | 요청등급={product_rank_code} | API등급코드={item_productrankcode}(정규화={normalized_item_code}) | price={item.get('price', 'N/A')}")
        
        # countyname 필터링: "평균", "평년" 제외하고 실제 지역명만 사용
        countyname = str(item.get("countyname", "")).strip()
        if countyname in ("평균", "평년", ""):
            # 전국 조회가 아닌 경우, 평균/평년 데이터는 제외
            if region != "전국":
                continue
        # 특정 지역 조회 시 해당 지역명과 일치하는 데이터만 사용
        elif region != "전국" and region != "온라인":
            # 온라인은 특별 처리 (시장명으로 필터링)
            region_name_map = {
                "서울": "서울", "부산": "부산", "대구": "대구", "인천": "인천",
                "광주": "광주", "대전": "대전", "울산": "울산", "세종": "세종",
                "수원": "수원", "강릉": "강릉", "춘천": "춘천", "청주": "청주",
                "전주": "전주", "군산": "군산", "순천": "순천", "목포": "목포",
                "포항": "포항", "안동": "안동", "창원": "창원", "마산": "마산",
                "용인": "용인", "성남": "성남", "의정부": "의정부", "고양": "고양",
                "천안": "천안", "김해": "김해", "제주": "제주",
            }
            expected_countyname = region_name_map.get(region, region)
            if countyname != expected_countyname:
                continue
        elif region == "온라인":
            # 온라인은 시장명으로 필터링 (온라인몰A, 온라인몰B 등)
            marketname = str(item.get("marketname", "")).strip()
            if "온라인" not in marketname and "옥션" not in marketname:
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
        
        # 날짜별로 그룹화 (같은 날짜에 여러 항목이 있을 수 있음)
        # countyname 우선순위: 전국 > 특정 지역 > 평균
        countyname_priority = 0
        if countyname == "전국":
            countyname_priority = 0
        elif countyname in ("평균", "평년", ""):
            countyname_priority = 2
        else:
            countyname_priority = 1
        
        by_date[regday].append((item, countyname, price_value, countyname_priority))
        
        # Forward Fill: 가격이 0보다 크면 last_price 업데이트
        if price_value > 0:
            last_price = price_value
    
    # 각 날짜별로 가장 최신 항목만 선택 (실시간 가격 정보와 동일한 로직)
    # 우선순위: countyname_priority (전국=0, 특정지역=1, 평균=2) -> 가격이 큰 것
    result: list[dict[str, Any]] = []
    for regday, date_items in sorted(by_date.items()):
        # 같은 날짜의 항목들을 우선순위로 정렬: countyname_priority 오름차순, 가격 내림차순
        date_items.sort(key=lambda x: (x[3], -x[2]))  # countyname_priority 오름차순, 가격 내림차순
        selected_item, selected_countyname, selected_price, _ = date_items[0]
        
        # Forward Fill: 가격이 0이면 last_price 사용
        if selected_price <= 0 and last_price is not None:
            selected_price = last_price
        
        if selected_price > 0:
            result.append({"date": regday, "price": selected_price})
            # Forward Fill 업데이트
            last_price = selected_price

    result.sort(key=lambda x: x["date"])
    
    # 디버그: 최종 결과 확인
    print(f"DEBUG: fetch_kamis_price_period 최종 결과 | 등급코드={grade_code} | product_rank_code={product_rank_code} | 결과 수={len(result)}")
    if result:
        print(f"DEBUG: 최신 가격 | 날짜={result[-1]['date']} | 가격={result[-1]['price']}")
    else:
        print(f"DEBUG: ⚠️ 결과 없음 | 등급코드={grade_code} | product_rank_code={product_rank_code}")
    
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

