# -*- coding: utf-8 -*-
"""영양정보 — 외부 API 우선, 실패 시 DB fallback. 등급별 + 세부부위별 그룹화."""
from __future__ import annotations

import re
from typing import Any

import httpx
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .. import apis
from ..config.settings import settings


def _extract_grade(food_nm: str) -> str:
    """
    food_nm에서 등급 추출.
    예: "소고기_한우(1++등급)_등심_생것" → "1++등급"
    "소고기_한우(1+등급)_등심_생것" → "1+등급"
    "소고기_한우(1등급)_등심_생것" → "1등급"
    등급 없으면 → "일반"
    """
    if not food_nm:
        return "일반"
    match = re.search(r"\((\d\+\+?등급|\d등급)\)", food_nm)
    if match:
        return match.group(1)
    return "일반"


def _extract_subpart(food_nm: str) -> str:
    """
    food_nm에서 세부부위 추출.
    예: "소고기_한우(1++등급)_갈비(토시살)_생것" → "토시살"
    "소고기_한우(1++등급)_갈비(참갈비)_생것" → "참갈비"
    "소고기_한우(1++등급)_갈비_생것" → "기본"
    """
    if not food_nm:
        return "기본"
    # 갈비(토시살), 등심(윗등심살) 같은 패턴 매칭
    match = re.search(r"_(갈비|등심|안심|채끝|목심|사태|양지|앞다리|우둔|설도)\(([^)]+)\)", food_nm)
    if match:
        return match.group(2)  # 괄호 안의 세부부위명
    return "기본"


def _grade_order(grade: str) -> int:
    """등급 순서 (낮을수록 높은 등급)."""
    order_map = {
        "1++등급": 0,
        "1+등급": 1,
        "1등급": 2,
        "2등급": 3,
        "3등급": 4,
        "일반": 5,
    }
    return order_map.get(grade, 99)


def _search_conditions(part_name: str) -> tuple[str, dict]:
    """
    part_name(예: Beef_Ribeye, 등심)으로 meat_nutrition 검색용
    WHERE 조건과 이름 있는 파라미터 dict를 반환합니다.
    """
    codes = apis._get_codes(part_name)
    food_nm = (codes.get("food_nm") or part_name or "").strip()
    if "/" in food_nm:
        animal, part = food_nm.split("/", 1)
        animal, part = animal.strip(), part.strip()
        animal_keywords = {"소": ["소고기", "쇠고기", "우육"], "돼지": ["돼지고기", "돈육"]}.get(
            animal, [animal + "고기"] if animal else []
        )
        if not animal_keywords and animal:
            animal_keywords = [animal + "고기"]
        parts = [part] if part else []
    else:
        animal_keywords = []
        parts = [food_nm] if food_nm else []

    conditions = []
    params: dict = {}
    if animal_keywords:
        cond_parts = " OR ".join([f"food_nm LIKE :p{i}" for i in range(len(animal_keywords))])
        conditions.append(f"({cond_parts})")
        for i, kw in enumerate(animal_keywords):
            params[f"p{i}"] = f"%{kw}%"
    param_idx = len(params)
    for p in parts:
        if p:
            conditions.append(f"food_nm LIKE :p{param_idx}")
            params[f"p{param_idx}"] = f"%{p}%"
            param_idx += 1
    if not conditions:
        conditions.append("food_nm LIKE :p0")
        params["p0"] = f"%{part_name}%"
    where_sql = " AND ".join(conditions)
    return where_sql, params


async def _fetch_from_api(part_name: str) -> dict[str, Any] | None:
    """
    외부 API(식품안전나라)에서 영양정보 조회.
    실패 시 None 반환 (DB fallback용).
    """
    api_key = (settings.safe_food_api_key or "").strip()
    api_url = (settings.safe_food_api_url or "").strip()
    
    print(f"🔍 [영양정보 API] 키 확인: {'있음' if api_key else '없음'}, URL: {api_url or '없음'}")
    
    if not api_key or not api_url:
        print(f"⚠️ [영양정보 API] API 키 또는 URL이 없어 API 호출 건너뜀 → DB fallback 예정")
        return None
    
    # URL이 api.data.go.kr이면 apis.data.go.kr로 자동 치환
    original_url = api_url
    if "api.data.go.kr" in api_url:
        api_url = api_url.replace("api.data.go.kr", "apis.data.go.kr")
        print(f"🔧 [영양정보 API] URL 자동 수정: {original_url} → {api_url}")
    
    codes = apis._get_codes(part_name)
    food_name = codes.get("food_nm", part_name)
    
    if "/" in food_name:
        animal, part = food_name.split("/", 1)
        search_name = f"{animal}고기 {part}" if animal in ["소", "돼지"] else food_name
    else:
        search_name = food_name
    
    params = {
        "serviceKey": api_key,
        "pageNo": "1",
        "numOfRows": "100",
        "type": "json",
        "foodNm": search_name,
    }
    
    try:
        print(f"🌐 [영양정보 API] 호출 시작: {api_url} | 검색어: {search_name}")
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            req = client.build_request("GET", api_url, params=params)
            print(f"🌐 [영양정보 API] Full URL: {req.url}")
            resp = await client.send(req)
            print(f"🌐 [영양정보 API] 응답 상태: {resp.status_code} | 본문 미리보기: {resp.text[:200]}...")
            resp.raise_for_status()
            data = resp.json()
            
            records: list[dict[str, Any]] = []
            response = data.get("response", {})
            if isinstance(response, dict):
                body = response.get("body", {})
                if isinstance(body, dict):
                    result_code = str(body.get("resultCode", "00"))
                    result_msg = body.get("resultMsg", "")
                    print(f"🌐 [영양정보 API] 응답 코드: {result_code} | 메시지: {result_msg}")
                    if result_code != "00":
                        print(f"⚠️ [영양정보 API] 오류 코드 {result_code} → DB fallback")
                        return None
                    items = body.get("items")
                    if isinstance(items, dict):
                        records = items.get("item", [])
                        if not isinstance(records, list):
                            records = [records] if records else []
                    elif isinstance(items, list):
                        records = items
            
            if not records:
                return None
            
            # 등급별 + 세부부위별로 분류
            by_grade: dict[str, dict[str, Any]] = {}
            
            def _to_number(value: Any) -> float | int | None:
                if value is None:
                    return None
                if isinstance(value, (int, float)):
                    return value
                text = str(value).strip().replace(",", "")
                if not text or text == "":
                    return None
                try:
                    parsed = float(text)
                    return int(parsed) if parsed.is_integer() else parsed
                except (TypeError, ValueError):
                    return None
            
            def _is_raw_meat(item: dict[str, Any]) -> bool:
                food_name_str = item.get("foodNm") or item.get("식품명") or ""
                processing = item.get("foodLv7Nm") or item.get("식품세분류명") or ""
                return "생것" in food_name_str or processing == "생것"
            
            for item in records:
                if not isinstance(item, dict):
                    continue
                if not _is_raw_meat(item):
                    continue
                
                food_name_str = item.get("foodNm") or item.get("식품명") or ""
                grade = _extract_grade(food_name_str)
                subpart = _extract_subpart(food_name_str)
                
                calories = _to_number(item.get("enerc") or item.get("에너지(kcal)"))
                protein = _to_number(item.get("prot") or item.get("단백질(g)"))
                fat = _to_number(item.get("fatce") or item.get("지방(g)"))
                carbohydrate = _to_number(item.get("chocdf") or item.get("탄수화물(g)"))
                
                if calories is not None or protein is not None or fat is not None or carbohydrate is not None:
                    if grade not in by_grade:
                        by_grade[grade] = {
                            "nutrition": None,  # 기본값 (나중에 설정)
                            "by_subpart": {},
                        }
                    
                    nutrition_data = {
                        "calories": int(calories) if isinstance(calories, (int, float)) else None,
                        "protein": float(protein) if protein is not None else None,
                        "fat": float(fat) if fat is not None else None,
                        "carbohydrate": float(carbohydrate) if carbohydrate is not None else None,
                        "grade": grade,
                        "subpart": subpart,
                        "source": "api",
                    }
                    
                    by_grade[grade]["by_subpart"][subpart] = nutrition_data
                    
                    # 기본값은 첫 번째 세부부위 또는 "기본"
                    if by_grade[grade]["nutrition"] is None:
                        by_grade[grade]["nutrition"] = nutrition_data
            
            if not by_grade:
                print(f"⚠️ [영양정보 API] 등급별 데이터 없음 → DB fallback")
                return None
            
            # 등급 순서 정렬 및 구조 변환
            sorted_grades = sorted(by_grade.keys(), key=_grade_order)
            result_by_grade = []
            
            for grade in sorted_grades:
                grade_data = by_grade[grade]
                by_subpart_list = [
                    {"subpart": subpart, "nutrition": nutrition}
                    for subpart, nutrition in sorted(grade_data["by_subpart"].items())
                ]
                
                result_by_grade.append({
                    "grade": grade,
                    "nutrition": grade_data["nutrition"],
                    "by_subpart": by_subpart_list,
                })
            
            default_nutrition = result_by_grade[0]["nutrition"] if result_by_grade else {
                "calories": None,
                "protein": None,
                "fat": None,
                "carbohydrate": None,
                "source": "api",
            }
            
            total_subparts = sum(len(g["by_subpart"]) for g in result_by_grade)
            print(f"✅ [영양정보 API] 성공: 등급 {len(result_by_grade)}개, 세부부위 {total_subparts}개")
            
            return {
                "by_grade": result_by_grade,
                "default": default_nutrition,
            }
    except Exception as e:
        print(f"🚨 [REAL ERROR] 영양정보 API 호출 실패: {e}")
        print(f"⚠️ [영양정보 API] 예외 발생 → DB fallback")
        return None


async def _fetch_from_db(part_name: str, db: AsyncSession) -> dict[str, Any]:
    """
    DB meat_nutrition에서 등급별 + 세부부위별 영양정보 조회.
    """
    where_sql, params = _search_conditions(part_name)
    sql = f"SELECT id, food_nm, calories, protein, fat, carbs FROM meat_nutrition WHERE {where_sql} LIMIT 200"
    
    print(f"🗄️ [영양정보 DB] 조회 시작: {part_name}")
    print(f"🗄️ [영양정보 DB] SQL: {sql}")
    print(f"🗄️ [영양정보 DB] 파라미터: {params}")
    
    try:
        result = await db.execute(text(sql), params)
        rows = result.mappings().all()
        print(f"🗄️ [영양정보 DB] 조회 결과: {len(rows)}건")
    except Exception as e:
        print(f"🚨 [REAL ERROR] 영양정보 DB 조회 실패: {e}")
        raise HTTPException(status_code=502, detail=f"영양정보 DB 조회 실패: {e}") from e
    
    if not rows:
        print(f"⚠️ [영양정보 DB] 데이터 없음")
        raise HTTPException(
            status_code=404,
            detail=f"'{part_name}'에 해당하는 영양정보를 찾을 수 없습니다.",
        )
    
    # 등급별 + 세부부위별로 그룹화
    by_grade: dict[str, dict[str, Any]] = {}
    
    for row in rows:
        food_nm = row.get("food_nm") or ""
        grade = _extract_grade(food_nm)
        subpart = _extract_subpart(food_nm)
        
        calories = row.get("calories")
        protein = float(row["protein"]) if row.get("protein") is not None else None
        fat = float(row["fat"]) if row.get("fat") is not None else None
        carbs = float(row["carbs"]) if row.get("carbs") is not None else None
        
        if grade not in by_grade:
            by_grade[grade] = {
                "nutrition": None,  # 기본값 (나중에 설정)
                "by_subpart": {},
            }
        
        nutrition_data = {
            "calories": int(calories) if calories is not None else None,
            "protein": protein,
            "fat": fat,
            "carbohydrate": carbs,
            "grade": grade,
            "subpart": subpart,
            "source": "db",
        }
        
        by_grade[grade]["by_subpart"][subpart] = nutrition_data
        
        # 기본값은 첫 번째 세부부위 또는 "기본"
        if by_grade[grade]["nutrition"] is None:
            by_grade[grade]["nutrition"] = nutrition_data
    
    print(f"🗄️ [영양정보 DB] 그룹화 완료: 등급 {len(by_grade)}개")
    for grade, data in by_grade.items():
        print(f"  - {grade}: 세부부위 {len(data['by_subpart'])}개 ({', '.join(data['by_subpart'].keys())})")
    
    if not by_grade:
        # 등급 추출 실패 시 첫 번째 행을 "일반"으로 사용
        first_row = rows[0]
        default_nutrition = {
            "calories": int(first_row["calories"]) if first_row.get("calories") is not None else None,
            "protein": float(first_row["protein"]) if first_row.get("protein") is not None else None,
            "fat": float(first_row["fat"]) if first_row.get("fat") is not None else None,
            "carbohydrate": float(first_row["carbs"]) if first_row.get("carbs") is not None else None,
            "grade": "일반",
            "subpart": "기본",
            "source": "db",
        }
        return {
            "by_grade": [{"grade": "일반", "nutrition": default_nutrition, "by_subpart": [{"subpart": "기본", "nutrition": default_nutrition}]}],
            "default": default_nutrition,
        }
    
    # 등급 순서 정렬 및 구조 변환
    sorted_grades = sorted(by_grade.keys(), key=_grade_order)
    result_by_grade = []
    
    for grade in sorted_grades:
        grade_data = by_grade[grade]
        by_subpart_list = [
            {"subpart": subpart, "nutrition": nutrition}
            for subpart, nutrition in sorted(grade_data["by_subpart"].items())
        ]
        
        result_by_grade.append({
            "grade": grade,
            "nutrition": grade_data["nutrition"],
            "by_subpart": by_subpart_list,
        })
    
    default_nutrition = result_by_grade[0]["nutrition"] if result_by_grade else {
        "calories": None,
        "protein": None,
        "fat": None,
        "carbohydrate": None,
        "grade": "일반",
        "subpart": "기본",
        "source": "db",
    }
    
    return {
        "by_grade": result_by_grade,
        "default": default_nutrition,
    }


class NutritionService:
    """영양정보 조회: 외부 API 우선, 실패 시 DB fallback. 등급별 + 세부부위별 그룹화."""

    async def fetch_nutrition(self, part_name: str, db: AsyncSession | None = None) -> dict[str, Any]:
        """
        부위명으로 영양정보 조회 (외부 API 우선 → 실패 시 DB).
        반환 형식:
        {
            "by_grade": [
                {
                    "grade": "1++등급",
                    "nutrition": {...},  # 기본값
                    "by_subpart": [
                        {"subpart": "토시살", "nutrition": {...}},
                        {"subpart": "참갈비", "nutrition": {...}},
                        ...
                    ]
                },
                ...
            ],
            "default": {...}
        }
        """
        # 1. 외부 API 시도 (API 키가 있으면)
        print(f"=" * 60)
        print(f"🔍 [영양정보] 조회 시작: {part_name}")
        print(f"=" * 60)
        api_result = await _fetch_from_api(part_name)
        if api_result:
            subpart_count = sum(len(g.get("by_subpart", [])) for g in api_result.get("by_grade", []))
            print(f"✅ [영양정보] API 성공: {part_name} (등급 {len(api_result['by_grade'])}개, 세부부위 {subpart_count}개)")
            print(f"=" * 60)
            return api_result
        
        # 2. API 실패 시 DB fallback
        if not db:
            print(f"🚨 [영양정보] DB 세션 없음")
            raise HTTPException(
                status_code=503,
                detail="영양정보 조회를 위해 DB 세션이 필요합니다.",
            )
        
        print(f"⚠️ [영양정보] API 실패 → DB fallback: {part_name}")
        db_result = await _fetch_from_db(part_name, db)
        subpart_count = sum(len(g.get("by_subpart", [])) for g in db_result.get("by_grade", []))
        print(f"✅ [영양정보] DB 성공: {part_name} (등급 {len(db_result['by_grade'])}개, 세부부위 {subpart_count}개)")
        print(f"=" * 60)
        return db_result
