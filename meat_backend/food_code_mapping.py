# -*- coding: utf-8 -*-
"""
고기 부위명을 식품코드로 매핑하는 모듈.
JSON 파일에서 식품코드를 로드하여 매핑 딕셔너리 생성.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# 고기 부위명 -> 식품코드 매핑 (기본값, JSON 파일이 없을 경우 사용)
DEFAULT_FOOD_CODE_MAPPING: dict[str, str] = {
    # 소고기
    "소/등심": "R209-027068301-0000",
    "소/안심": "R209-027068201-0000",
    "소/채끝": "R209-027068401-0000",
    "소/목심": "R209-027068501-0000",
    "소/갈비": "R209-027074101-0000",
    "소/양지": "R209-027068601-0000",
    "소/사태": "R209-027068701-0000",
    "소/앞다리": "R209-027068801-0000",
    "소/우둔": "R209-027068901-0000",
    "소/설도": "R209-027069001-0000",
    # 돼지고기
    "돼지/삼겹살": "R209-028074101-0000",
    "돼지/목심": "R209-028074201-0000",
    "돼지/갈비": "R209-028074301-0000",
    "돼지/앞다리": "R209-028074401-0000",
}

# 부위명 매칭을 위한 키워드 매핑
PART_NAME_KEYWORDS: dict[str, list[str]] = {
    "소/등심": ["등심", "소/등심", "소등심"],
    "소/안심": ["안심", "소/안심", "소안심"],
    "소/채끝": ["채끝", "소/채끝", "소채끝"],
    "소/목심": ["목심", "소/목심", "소목심"],
    "소/갈비": ["갈비", "소/갈비", "소갈비"],
    "소/양지": ["양지", "소/양지", "소양지"],
    "소/사태": ["사태", "소/사태", "소사태"],
    "소/앞다리": ["앞다리", "소/앞다리", "소앞다리"],
    "소/우둔": ["우둔", "소/우둔", "소우둔"],
    "소/설도": ["설도", "소/설도", "소설도"],
    "돼지/삼겹살": ["삼겹살", "돼지/삼겹살", "돼지삼겹살"],
    "돼지/목심": ["목심", "돼지/목심", "돼지목심"],
    "돼지/갈비": ["갈비", "돼지/갈비", "돼지갈비"],
    "돼지/앞다리": ["앞다리", "돼지/앞다리", "돼지앞다리"],
}

_food_code_cache: dict[str, str] | None = None


def _load_food_code_mapping() -> dict[str, str]:
    """JSON 파일에서 식품코드 매핑을 로드합니다."""
    global _food_code_cache
    
    if _food_code_cache is not None:
        return _food_code_cache
    
    _food_code_cache = DEFAULT_FOOD_CODE_MAPPING.copy()
    
    # JSON 파일 경로 (다운로드 폴더)
    json_paths = [
        Path.home() / "Downloads" / "전국통합식품영양성분정보_원재료성식품_표준데이터.json",
        Path.home() / "Downloads" / "농촌진흥청_국립식량과학원_통합식품영양성분정보(원재료성식품)_20251223.csv",
    ]
    
    for json_path in json_paths:
        if json_path.exists() and json_path.suffix == ".json":
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    records = data.get("records", [])
                    
                    # 고기 부위별로 매핑 생성
                    for record in records:
                        food_name = record.get("식품명", "")
                        food_code = record.get("식품코드", "")
                        
                        if not food_name or not food_code:
                            continue
                        
                        # 소고기 부위 매칭
                        if "소고기" in food_name and "생것" in food_name:
                            if "등심" in food_name and "소/등심" not in _food_code_cache:
                                _food_code_cache["소/등심"] = food_code
                            elif "안심" in food_name and "소/안심" not in _food_code_cache:
                                _food_code_cache["소/안심"] = food_code
                            elif "채끝" in food_name and "소/채끝" not in _food_code_cache:
                                _food_code_cache["소/채끝"] = food_code
                            elif "목심" in food_name and "소/목심" not in _food_code_cache:
                                _food_code_cache["소/목심"] = food_code
                            elif "갈비" in food_name and "소/갈비" not in _food_code_cache:
                                _food_code_cache["소/갈비"] = food_code
                            elif "양지" in food_name and "소/양지" not in _food_code_cache:
                                _food_code_cache["소/양지"] = food_code
                            elif "사태" in food_name and "소/사태" not in _food_code_cache:
                                _food_code_cache["소/사태"] = food_code
                            elif "앞다리" in food_name and "소/앞다리" not in _food_code_cache:
                                _food_code_cache["소/앞다리"] = food_code
                            elif "우둔" in food_name and "소/우둔" not in _food_code_cache:
                                _food_code_cache["소/우둔"] = food_code
                            elif "설도" in food_name and "소/설도" not in _food_code_cache:
                                _food_code_cache["소/설도"] = food_code
                        
                        # 돼지고기 부위 매칭
                        elif "돼지고기" in food_name or ("돼지" in food_name and "생것" in food_name):
                            if "삼겹살" in food_name and "돼지/삼겹살" not in _food_code_cache:
                                _food_code_cache["돼지/삼겹살"] = food_code
                            elif "목심" in food_name and "돼지/목심" not in _food_code_cache:
                                _food_code_cache["돼지/목심"] = food_code
                            elif "갈비" in food_name and "돼지/갈비" not in _food_code_cache:
                                _food_code_cache["돼지/갈비"] = food_code
                            elif "앞다리" in food_name and "돼지/앞다리" not in _food_code_cache:
                                _food_code_cache["돼지/앞다리"] = food_code
                
                break  # 첫 번째 파일만 로드
            except Exception:
                # JSON 파일 로드 실패 시 기본값 사용
                pass
    
    return _food_code_cache


def _get_part_key(part_name: str) -> str | None:
    """부위명을 표준 키로 변환 (예: "Beef_Ribeye" -> "소/등심")"""
    part_lower = part_name.lower()
    
    # 영어 부위명 매칭
    if "beef" in part_lower:
        if "ribeye" in part_lower or "등심" in part_name:
            return "소/등심"
        elif "tenderloin" in part_lower or "안심" in part_name:
            return "소/안심"
        elif "sirloin" in part_lower or "채끝" in part_name:
            return "소/채끝"
        elif "chuck" in part_lower or "목심" in part_name:
            return "소/목심"
        elif "rib" in part_lower or "갈비" in part_name:
            return "소/갈비"
        elif "brisket" in part_lower or "양지" in part_name:
            return "소/양지"
        elif "shank" in part_lower or "사태" in part_name:
            return "소/사태"
        elif "shoulder" in part_lower or "앞다리" in part_name:
            return "소/앞다리"
        elif "round" in part_lower or "우둔" in part_name:
            return "소/우둔"
        elif "bottomround" in part_lower or "설도" in part_name:
            return "소/설도"
    elif "pork" in part_lower:
        if "belly" in part_lower or "삼겹" in part_name:
            return "돼지/삼겹살"
        elif "loin" in part_lower or ("목심" in part_name and "돼지" in part_name):
            return "돼지/목심"
        elif "rib" in part_lower or ("갈비" in part_name and "돼지" in part_name):
            return "돼지/갈비"
        elif "shoulder" in part_lower or ("앞다리" in part_name and "돼지" in part_name):
            return "돼지/앞다리"
    
    # 키워드 매칭
    for key, keywords in PART_NAME_KEYWORDS.items():
        for keyword in keywords:
            if keyword.lower() in part_lower or part_lower in keyword.lower():
                return key
    
    # 직접 매칭
    if part_name in PART_NAME_KEYWORDS:
        return part_name
    
    return None


def get_food_code(part_name: str) -> str | None:
    """
    고기 부위명을 식품코드로 변환합니다 (첫 번째 매칭만 반환).
    
    Args:
        part_name: 고기 부위명 (예: "소/등심", "등심", "Beef_Ribeye")
    
    Returns:
        식품코드 문자열 또는 None
    """
    part_key = _get_part_key(part_name)
    if not part_key:
        return None
    
    mapping = _load_food_code_mapping()
    return mapping.get(part_key)


def get_food_codes(part_name: str) -> list[dict[str, str]]:
    """
    고기 부위명에 해당하는 모든 등급의 식품코드를 반환합니다.
    
    Args:
        part_name: 고기 부위명 (예: "소/등심", "등심", "Beef_Ribeye")
    
    Returns:
        [{"food_code": "...", "grade": "1등급", "food_name": "..."}, ...] 리스트
    """
    part_key = _get_part_key(part_name)
    if not part_key:
        return []
    
    results: list[dict[str, str]] = []
    
    # JSON 파일에서 해당 부위의 모든 등급 찾기
    json_paths = [
        Path.home() / "Downloads" / "전국통합식품영양성분정보_원재료성식품_표준데이터.json",
    ]
    
    for json_path in json_paths:
        if json_path.exists() and json_path.suffix == ".json":
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    records = data.get("records", [])
                    
                    # 부위명 추출 (예: "소/등심" -> "등심")
                    part_korean = part_key.split("/")[-1] if "/" in part_key else part_key
                    animal = "소고기" if "소" in part_key else "돼지고기"
                    
                    for record in records:
                        food_name = record.get("식품명", "")
                        food_code = record.get("식품코드", "")
                        grade_name = record.get("식품중분류명", "")  # 예: "한우(1등급)"
                        sub_part = record.get("식품소분류명", "")  # 예: "등심"
                        processing = record.get("식품세분류명", "")  # 예: "생것"
                        
                        # 조건 확인: 동물 종류, 부위명, 생것 여부
                        if (animal in food_name and 
                            part_korean in sub_part and 
                            processing == "생것"):
                            
                            # 등급 추출
                            grade = "일반"
                            if "1++등급" in grade_name or "1++" in grade_name:
                                grade = "1++등급"
                            elif "1+등급" in grade_name or "1+" in grade_name:
                                grade = "1+등급"
                            elif "1등급" in grade_name:
                                grade = "1등급"
                            elif "2등급" in grade_name:
                                grade = "2등급"
                            elif "3등급" in grade_name:
                                grade = "3등급"
                            
                            # 중복 제거 (같은 등급, 같은 식품코드)
                            if not any(r["food_code"] == food_code for r in results):
                                results.append({
                                    "food_code": food_code,
                                    "grade": grade,
                                    "food_name": food_name,
                                })
                
                break  # 첫 번째 파일만 로드
            except Exception:
                pass
    
    # 등급 순서 정렬 (1++등급 > 1+등급 > 1등급 > 2등급 > 3등급 > 일반)
    grade_order = {"1++등급": 0, "1+등급": 1, "1등급": 2, "2등급": 3, "3등급": 4, "일반": 5}
    results.sort(key=lambda x: grade_order.get(x["grade"], 99))
    
    return results
