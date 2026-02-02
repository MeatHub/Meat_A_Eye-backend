"""AI 클래스명을 각 공공 API가 요구하는 코드/키워드로 변환하는 매핑 테이블."""
from typing import Dict, List, Any

# AI 클래스명 → API별 코드/키워드 매핑
# kamis_code: KAMIS p_item_code (부위코드)
# food_safety_nm: 식품안전나라/영양정보 API 검색용 한글 식품명
# category_code: KAMIS p_item_category_code (100:식량, 200:채소, 500:축산물 등)
AI_TO_API_MAPPING: Dict[str, Dict[str, Any]] = {
    # 소고기
    "Beef_Tenderloin": {
        "kamis_code": "502",
        "food_safety_nm": "소고기 안심",
        "category_code": "500",
    },
    "Beef_Ribeye": {
        "kamis_code": "501",
        "food_safety_nm": "소고기 등심",
        "category_code": "500",
    },
    "Beef_Sirloin": {
        "kamis_code": "503",
        "food_safety_nm": "소고기 채끝살",
        "category_code": "500",
    },
    "Beef_Chuck": {
        "kamis_code": "504",
        "food_safety_nm": "소고기 목심",
        "category_code": "500",
    },
    "Beef_Brisket": {
        "kamis_code": "505",
        "food_safety_nm": "소고기 양지",
        "category_code": "500",
    },
    "Beef_Shank": {
        "kamis_code": "506",
        "food_safety_nm": "소고기 사태",
        "category_code": "500",
    },
    "Beef_BottomRound": {
        "kamis_code": "507",
        "food_safety_nm": "소고기 우둔",
        "category_code": "500",
    },
    "Beef_TopRound": {
        "kamis_code": "508",
        "food_safety_nm": "소고기 설도",
        "category_code": "500",
    },
    "Beef_Flank": {
        "kamis_code": "509",
        "food_safety_nm": "소고기 갈비",
        "category_code": "500",
    },
    "Beef_ShortRib": {
        "kamis_code": "510",
        "food_safety_nm": "소고기 갈비살",
        "category_code": "500",
    },
    "Beef_Rib": {
        "kamis_code": "509",
        "food_safety_nm": "소고기 갈비",
        "category_code": "500",
    },
    "Beef_Round": {
        "kamis_code": "507",
        "food_safety_nm": "소고기 우둔",
        "category_code": "500",
    },
    "Beef_Shoulder": {
        "kamis_code": "504",
        "food_safety_nm": "소고기 목심",
        "category_code": "500",
    },
    # 돼지고기
    "Pork_Belly": {
        "kamis_code": "601",
        "food_safety_nm": "돼지고기 삼겹살",
        "category_code": "600",
    },
    "Pork_Loin": {
        "kamis_code": "602",
        "food_safety_nm": "돼지고기 목살",
        "category_code": "600",
    },
    "Pork_Shoulder": {
        "kamis_code": "603",
        "food_safety_nm": "돼지고기 앞다리",
        "category_code": "600",
    },
    "Pork_Ham": {
        "kamis_code": "604",
        "food_safety_nm": "돼지고기 뒷다리",
        "category_code": "600",
    },
    "Pork_Neck": {
        "kamis_code": "602",
        "food_safety_nm": "돼지고기 목살",
        "category_code": "600",
    },
    "Pork_Rib": {
        "kamis_code": "605",
        "food_safety_nm": "돼지고기 갈비",
        "category_code": "600",
    },
    # 한글 부위명
    "한우 안심": {"kamis_code": "502", "food_safety_nm": "소고기 안심", "category_code": "500"},
    "한우 등심": {"kamis_code": "501", "food_safety_nm": "소고기 등심", "category_code": "500"},
    "한우 채끝살": {"kamis_code": "503", "food_safety_nm": "소고기 채끝살", "category_code": "500"},
    "삼겹살": {"kamis_code": "601", "food_safety_nm": "돼지고기 삼겹살", "category_code": "600"},
    "목살": {"kamis_code": "602", "food_safety_nm": "돼지고기 목살", "category_code": "600"},
    "돼지 갈비": {"kamis_code": "605", "food_safety_nm": "돼지고기 갈비", "category_code": "600"},
}


def map_ai_class_to_api_codes(ai_class: str) -> Dict[str, Any]:
    """
    AI 클래스명을 각 API가 요구하는 코드/키워드로 변환.

    Args:
        ai_class: AI가 반환한 부위명 (예: "Beef_Tenderloin")

    Returns:
        {"kamis_code", "food_safety_nm", "category_code"}
    """
    if ai_class in AI_TO_API_MAPPING:
        return AI_TO_API_MAPPING[ai_class].copy()

    ai_class_lower = ai_class.lower()
    for key, value in AI_TO_API_MAPPING.items():
        if key.lower() in ai_class_lower or ai_class_lower in key.lower():
            return value.copy()

    if "_" in ai_class:
        parts = ai_class.split("_")
        if parts[0].lower() == "beef":
            return {"kamis_code": "500", "food_safety_nm": "소고기 생것", "category_code": "500"}
        elif parts[0].lower() == "pork":
            return {"kamis_code": "600", "food_safety_nm": "돼지고기 생것", "category_code": "600"}

    return {"kamis_code": "500", "food_safety_nm": ai_class, "category_code": "500"}


def map_ai_class_to_keywords(ai_class: str) -> List[str]:
    """AI 클래스명을 공공데이터 검색 키워드 리스트로 변환 (하위 호환)."""
    codes = map_ai_class_to_api_codes(ai_class)
    nm = codes.get("food_safety_nm", ai_class)
    return [x.strip() for x in nm.split() if x.strip()] or [ai_class, "생것"]


def get_search_query(ai_class: str) -> str:
    """AI 클래스명을 영양정보 API FOOD_NM 파라미터용 한글 검색어로 변환."""
    codes = map_ai_class_to_api_codes(ai_class)
    return codes.get("food_safety_nm", ai_class)
