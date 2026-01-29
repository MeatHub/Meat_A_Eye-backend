"""AI 클래스명을 공공데이터 검색 키워드로 변환하는 매핑 테이블."""
from typing import Dict, List

# AI 클래스명 → 공공데이터 검색 키워드 매핑
AI_TO_PUBLIC_DATA_MAPPING: Dict[str, List[str]] = {
    # 소고기
    "Beef_Tenderloin": ["소고기", "안심", "생것"],
    "Beef_Ribeye": ["소고기", "등심", "생것"],
    "Beef_Sirloin": ["소고기", "채끝살", "생것"],
    "Beef_Chuck": ["소고기", "목심", "생것"],
    "Beef_Brisket": ["소고기", "양지", "생것"],
    "Beef_Shank": ["소고기", "사태", "생것"],
    "Beef_BottomRound": ["소고기", "우둔", "생것"],
    "Beef_TopRound": ["소고기", "설도", "생것"],
    "Beef_Flank": ["소고기", "갈비", "생것"],
    "Beef_ShortRib": ["소고기", "갈비살", "생것"],
    # 돼지고기
    "Pork_Belly": ["돼지고기", "삼겹살", "생것"],
    "Pork_Loin": ["돼지고기", "목살", "생것"],
    "Pork_Shoulder": ["돼지고기", "앞다리", "생것"],
    "Pork_Ham": ["돼지고기", "뒷다리", "생것"],
    "Pork_Neck": ["돼지고기", "목살", "생것"],
    "Pork_Rib": ["돼지고기", "갈비", "생것"],
    # 한글 부위명도 지원
    "한우 안심": ["소고기", "안심", "생것"],
    "한우 등심": ["소고기", "등심", "생것"],
    "한우 채끝살": ["소고기", "채끝살", "생것"],
    "삼겹살": ["돼지고기", "삼겹살", "생것"],
    "목살": ["돼지고기", "목살", "생것"],
    "돼지 갈비": ["돼지고기", "갈비", "생것"],
}


def map_ai_class_to_keywords(ai_class: str) -> List[str]:
    """
    AI 클래스명을 공공데이터 검색 키워드로 변환.
    
    Args:
        ai_class: AI가 반환한 부위명 (예: "Beef_Tenderloin")
    
    Returns:
        검색 키워드 리스트 (예: ["소고기", "안심", "생것"])
    """
    # 정확한 매칭
    if ai_class in AI_TO_PUBLIC_DATA_MAPPING:
        return AI_TO_PUBLIC_DATA_MAPPING[ai_class]
    
    # 부분 매칭 (대소문자 무시)
    ai_class_lower = ai_class.lower()
    for key, keywords in AI_TO_PUBLIC_DATA_MAPPING.items():
        if key.lower() in ai_class_lower or ai_class_lower in key.lower():
            return keywords
    
    # 기본값: 첫 번째 단어를 추출하여 사용
    # 예: "Beef_Tenderloin" -> ["소고기", "생것"]
    if "_" in ai_class:
        parts = ai_class.split("_")
        if parts[0].lower() == "beef":
            return ["소고기", "생것"]
        elif parts[0].lower() == "pork":
            return ["돼지고기", "생것"]
    
    # 최종 기본값
    return [ai_class, "생것"]


def get_search_query(ai_class: str) -> str:
    """
    AI 클래스명을 공공데이터 API 검색 쿼리 문자열로 변환.
    
    Args:
        ai_class: AI가 반환한 부위명
    
    Returns:
        검색 쿼리 문자열 (예: "소고기 안심 생것")
    """
    keywords = map_ai_class_to_keywords(ai_class)
    return " ".join(keywords)

