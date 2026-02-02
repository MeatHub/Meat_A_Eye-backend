"""부위별 평균 영양성분 데이터 (Fallback용)."""
from typing import Dict, Any

# 부위별 평균 영양성분 (100g당)
MEAT_NUTRITION_FALLBACK: Dict[str, Dict[str, Any]] = {
    # 소고기
    "Beef_Tenderloin": {
        "calories": 200,
        "protein": 22.0,
        "fat": 11.0,
        "carbohydrate": 0.0,
    },
    "Beef_Ribeye": {
        "calories": 250,
        "protein": 20.0,
        "fat": 18.0,
        "carbohydrate": 0.0,
    },
    "Beef_Sirloin": {
        "calories": 220,
        "protein": 21.0,
        "fat": 14.0,
        "carbohydrate": 0.0,
    },
    "Beef_Chuck": {
        "calories": 230,
        "protein": 19.0,
        "fat": 16.0,
        "carbohydrate": 0.0,
    },
    "Beef_Brisket": {
        "calories": 250,
        "protein": 18.0,
        "fat": 19.0,
        "carbohydrate": 0.0,
    },
    "Beef_Shank": {
        "calories": 180,
        "protein": 20.0,
        "fat": 9.0,
        "carbohydrate": 0.0,
    },
    "Beef_Rib": {
        "calories": 240,
        "protein": 19.0,
        "fat": 17.0,
        "carbohydrate": 0.0,
    },
    "Beef_Round": {
        "calories": 195,
        "protein": 21.0,
        "fat": 10.0,
        "carbohydrate": 0.0,
    },
    "Beef_Shoulder": {
        "calories": 235,
        "protein": 18.5,
        "fat": 17.0,
        "carbohydrate": 0.0,
    },
    "Beef_BottomRound": {
        "calories": 190,
        "protein": 21.0,
        "fat": 10.0,
        "carbohydrate": 0.0,
    },
    "Beef_TopRound": {
        "calories": 200,
        "protein": 22.0,
        "fat": 10.0,
        "carbohydrate": 0.0,
    },
    # 돼지고기
    "Pork_Belly": {
        "calories": 330,
        "protein": 14.0,
        "fat": 30.0,
        "carbohydrate": 0.0,
    },
    "Pork_Loin": {
        "calories": 240,
        "protein": 20.0,
        "fat": 17.0,
        "carbohydrate": 0.0,
    },
    "Pork_Shoulder": {
        "calories": 250,
        "protein": 19.0,
        "fat": 18.0,
        "carbohydrate": 0.0,
    },
    "Pork_Ham": {
        "calories": 220,
        "protein": 20.0,
        "fat": 15.0,
        "carbohydrate": 0.0,
    },
    "Pork_Neck": {
        "calories": 230,
        "protein": 19.0,
        "fat": 16.0,
        "carbohydrate": 0.0,
    },
    # 한글 부위명
    "한우 안심": {
        "calories": 200,
        "protein": 22.0,
        "fat": 11.0,
        "carbohydrate": 0.0,
    },
    "한우 등심": {
        "calories": 250,
        "protein": 20.0,
        "fat": 18.0,
        "carbohydrate": 0.0,
    },
    "삼겹살": {
        "calories": 330,
        "protein": 14.0,
        "fat": 30.0,
        "carbohydrate": 0.0,
    },
    "목살": {
        "calories": 240,
        "protein": 20.0,
        "fat": 17.0,
        "carbohydrate": 0.0,
    },
}

# 부위별 평균 가격 (100g당, 원)
MEAT_PRICE_FALLBACK: Dict[str, int] = {
    "Beef_Tenderloin": 15000,
    "Beef_Ribeye": 12000,
    "Beef_Sirloin": 10000,
    "Beef_Chuck": 8000,
    "Beef_Brisket": 7000,
    "Beef_Shank": 6000,
    "Beef_Rib": 9000,
    "Beef_Round": 5800,
    "Beef_Shoulder": 7500,
    "Beef_BottomRound": 5500,
    "Beef_TopRound": 5000,
    "Pork_Belly": 5000,
    "Pork_Loin": 4500,
    "Pork_Shoulder": 4000,
    "Pork_Ham": 4000,
    "Pork_Neck": 4500,
    "한우 안심": 20000,
    "한우 등심": 15000,
    "삼겹살": 5000,
    "목살": 4500,
}


def get_nutrition_fallback(part_name: str) -> Dict[str, Any]:
    """
    부위명에 대한 Fallback 영양성분 데이터 반환.
    
    Args:
        part_name: 부위명
    
    Returns:
        영양성분 딕셔너리 (calories, protein, fat, carbohydrate)
    """
    # 정확한 매칭
    if part_name in MEAT_NUTRITION_FALLBACK:
        return MEAT_NUTRITION_FALLBACK[part_name].copy()
    
    # 부분 매칭
    part_lower = part_name.lower()
    for key, value in MEAT_NUTRITION_FALLBACK.items():
        if key.lower() in part_lower or part_lower in key.lower():
            return value.copy()
    
    # 기본값 (소고기 평균)
    return {
        "calories": 220,
        "protein": 20.0,
        "fat": 14.0,
        "carbohydrate": 0.0,
    }


# AI 서버 Fallback용 Mock 부위 목록 (vision 모드)
MOCK_PART_OPTIONS = [
    "Beef_Tenderloin",
    "Beef_Ribeye",
    "Beef_Sirloin",
    "Beef_Chuck",
    "Beef_Brisket",
    "Beef_Rib",
    "Beef_Round",
    "Beef_Shank",
    "Beef_Shoulder",
    "Beef_BottomRound",
]


def get_mock_analyze_response(part_name: str | None = None) -> dict:
    """
    AI 서버 장애 시 Fallback용 Mock 응답.
    part_name이 없으면 랜덤 선택.
    """
    import random
    part = part_name or random.choice(MOCK_PART_OPTIONS)
    return {
        "partName": part,
        "confidence": 0.95,
        "historyNo": None,
        "heatmap_image": None,  # Mock에는 히트맵 없음
        "raw": {
            "status": "success",
            "data": {
                "category": part,
                "probability": 95.0,
                "is_valid": True,
            },
        },
    }


def get_traceability_fallback(trace_no: str | None = None) -> dict:
    """이력제 API 실패 시 Fallback (도축일자, 등급 등 기본값)."""
    return {
        "birth_date": None,
        "slaughterDate": None,
        "grade": "1++",
        "origin": "국내산",
        "partName": None,
        "companyName": None,
        "historyNo": trace_no or "",
        "source": "fallback",
    }


def get_price_fallback(part_name: str) -> int:
    """
    부위명에 대한 Fallback 가격 데이터 반환.
    
    Args:
        part_name: 부위명
    
    Returns:
        가격 (100g당, 원)
    """
    # 정확한 매칭
    if part_name in MEAT_PRICE_FALLBACK:
        return MEAT_PRICE_FALLBACK[part_name]
    
    # 부분 매칭
    part_lower = part_name.lower()
    for key, value in MEAT_PRICE_FALLBACK.items():
        if key.lower() in part_lower or part_lower in key.lower():
            return value
    
    # 기본값
    return 8000

