"""MEAT-01~03: 실시간 시세, 부위 상세 정보, 부위명으로 통합 정보 조회. MEAT-04: 이력/묶음번호 조회."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...config.database import get_db
from ...models.meat_info import MeatInfo
from ...models.market_price import MarketPrice
from ...schemas.meat import MeatPriceResponse, MeatInfoResponse, MeatInfoByPartNameResponse
from ...schemas.ai import TraceabilityInfo
from ... import apis
from ...apis import KamisService
from ...services.nutrition_service import NutritionService
from ...services.price_service import PriceService
from ...services.traceability_service import TraceabilityService

router = APIRouter()
kamis = KamisService()
nutrition_service = NutritionService()
price_service = PriceService()
traceability_service = TraceabilityService()


@router.get(
    "/prices",
    response_model=MeatPriceResponse,
    summary="MEAT-01 실시간 시세 조회",
    responses={
        404: {"description": "데이터 없음"},
        503: {"description": "KAMIS API 연동 지연"},
    },
)
async def meat_prices(
    partName: str,
    region: str = "seoul",
):
    # 1) DB market_prices 최신 데이터
    # 2) 없으면 KAMIS API 호출
    data = await kamis.fetch_current_price(part_name=partName, region=region)
    return MeatPriceResponse(
        currentPrice=data.get("currentPrice", 0),
        unit=data.get("unit", "100g"),
        trend=data.get("trend", "flat"),
    )


@router.get(
    "/info/list",
    response_model=list[MeatInfoResponse],
    summary="MEAT-01b 고기 정보 목록 조회 (부위 선택용)",
)
async def meat_info_list(
    category: str | None = Query(None, description="카테고리 필터 (beef/pork)"),
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
):
    """고기 부위 목록을 반환합니다. 냉장고 아이템 수정 시 부위 선택에 사용됩니다.
    part_name이 17개 영문만 반환 (DB에 한글·영문 혼재 시 중복 방지)."""
    q = select(MeatInfo).where(MeatInfo.part_name.in_(apis.MEAT_INFO_PART_NAMES))
    if category:
        q = q.where(MeatInfo.category == category)
    q = q.order_by(MeatInfo.category, MeatInfo.part_name)
    result = await db.execute(q)
    rows = result.scalars().all()
    return [
        MeatInfoResponse(
            id=r.id,
            name=r.part_name,
            displayName=apis.get_part_display_name(r.part_name) or r.part_name,
            category=r.category,
            calories=r.calories,
            protein=float(r.protein) if r.protein else None,
            fat=float(r.fat) if r.fat else None,
            storageGuide=r.storage_guide,
        )
        for r in rows
    ]


@router.get(
    "/nutrition",
    summary="MEAT-05 영양정보 조회 (부위명과 등급 기반)",
    responses={
        404: {"description": "영양정보 없음"},
        503: {"description": "API/DB 조회 실패"},
    },
)
async def meat_nutrition(
    part_name: str = Query(..., description="부위명 (예: 등심, 갈비)"),
    grade: str | None = Query(None, description="등급 (예: 1++등급, 1+등급, 1등급, 2등급, 3등급, 일반)"),
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
):
    """
    부위명과 등급을 기반으로 영양정보를 조회합니다.
    등급이 지정되면 해당 등급의 영양정보만 반환하고, 없으면 모든 등급의 정보를 반환합니다.
    """
    nutrition_data = await nutrition_service.fetch_nutrition(part_name, grade=grade, db=db)
    return nutrition_data


@router.get(
    "/info/{meat_id}",
    response_model=MeatInfoResponse,
    summary="MEAT-02 부위 상세 정보",
    responses={404: {"description": "육류 ID 오류"}},
)
async def meat_info(
    meat_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    row = await db.get(MeatInfo, meat_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="육류 ID 오류")
    extra = await nutrition_service.fetch_nutrition(row.part_name, db=db)
    default_nutrition = extra.get("default") or {}
    recipes = extra.get("recipes") or []
    cal = row.calories if row.calories is not None else default_nutrition.get("calories")
    prot = float(row.protein) if row.protein is not None else default_nutrition.get("protein")
    fat_val = float(row.fat) if row.fat is not None else default_nutrition.get("fat")
    return MeatInfoResponse(
        id=row.id,
        name=row.part_name,
        displayName=apis.get_part_display_name(row.part_name) or row.part_name,
        category=row.category,
        calories=cal,
        protein=prot,
        fat=fat_val,
        recipes=recipes,
        storageGuide=row.storage_guide,
    )


@router.get(
    "/info/part/{part_name}",
    response_model=MeatInfoByPartNameResponse,
    summary="MEAT-03 부위명으로 통합 정보 조회 (영양정보 + 가격정보)",
    responses={404: {"description": "부위 정보 없음"}},
)
async def meat_info_by_part_name(
    part_name: str,
    region: str = "seoul",
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
):
    """
    AI가 판별한 부위명으로 영양정보와 가격정보를 통합 조회.
    가격은 '가격 제공 부위'(소 5, 돼지 4, 수입 소·돼지)와 일치할 때만 조회하며,
    나머지 17부위는 가격 없음(0)으로 반환 → UI에서 "가격정보를 제공하지 않습니다" 표시.
    """
    # 1. 영양정보 조회
    nutrition_data = await nutrition_service.fetch_nutrition(part_name, db=db)
    
    # 2. 가격정보: 가격 제공 부위일 때만 KAMIS 조회, 아니면 0 반환
    price_data: dict = {
        "currentPrice": 0,
        "unit": "100g",
        "trend": "flat",
        "price_date": None,
        "source": "unavailable",
        "gradePrices": [],
    }
    if part_name in apis.PRICE_AVAILABLE_PARTS:
        try:
            price_data = await price_service.fetch_current_price(
                part_name=part_name,
                region=region,
                db=db,
            )
            price_data = dict(price_data)
            price_data.setdefault("gradePrices", [])
        except (HTTPException, Exception):
            price_data = {
                "currentPrice": 0,
                "unit": "100g",
                "trend": "flat",
                "price_date": None,
                "source": "unavailable",
                "gradePrices": [],
            }
    
    # 3. DB에서 기본 정보 조회 (선택)
    meat_info_record = None
    if db:
        result = await db.execute(
            select(MeatInfo).where(MeatInfo.part_name == part_name).limit(1)
        )
        meat_info_record = result.scalar_one_or_none()
    
    # 4. 응답 구성 (DB 데이터 우선, 없으면 영양 DB 데이터)
    default_nutrition = nutrition_data.get("default") or {}
    calories = (
        meat_info_record.calories
        if meat_info_record and meat_info_record.calories
        else default_nutrition.get("calories")
    )
    protein = (
        float(meat_info_record.protein)
        if meat_info_record and meat_info_record.protein
        else default_nutrition.get("protein")
    )
    fat = (
        float(meat_info_record.fat)
        if meat_info_record and meat_info_record.fat
        else default_nutrition.get("fat")
    )
    
    display_name = apis.get_part_display_name(part_name) or part_name
    return MeatInfoByPartNameResponse(
        partName=part_name,
        displayName=display_name,
        calories=calories,
        protein=protein,
        fat=fat,
        carbohydrate=default_nutrition.get("carbohydrate"),
        currentPrice=price_data.get("currentPrice", 0),
        priceUnit=price_data.get("unit", "100g"),
        priceTrend=price_data.get("trend", "flat"),
        priceDate=price_data.get("price_date"),
        priceSource=price_data.get("source", "api"),
        gradePrices=price_data.get("gradePrices", []),
        storageGuide=meat_info_record.storage_guide if meat_info_record else None,
    )


@router.get(
    "/traceability",
    response_model=TraceabilityInfo,
    summary="MEAT-04 이력번호/묶음번호로 이력제 조회 (국내/수입 자동 분기)",
    responses={
        400: {"description": "번호 없음"},
        502: {"description": "이력제에서 조회 실패"},
        503: {"description": "이력제 API 연결 실패"},
    },
)
async def meat_traceability_by_number(
    number: Annotated[str, Query(description="이력번호(12자리) 또는 수입 묶음번호(A+숫자)")],
    source: Annotated[str | None, Query(description="강제 분기: 'import' 또는 'domestic' (수입 묶음번호에서 나온 12자리 이력번호 처리용)")] = None,
):
    """
    이력번호 또는 수입육 묶음번호를 입력하면 이력제 정보를 반환합니다.
    - 국내: 12자리 숫자 → MTRACE
    - 수입 이력번호: 그 외 → meatwatch 이력정보(Detail)
    - 수입 묶음번호: A + 19~29자리 → meatwatch 묶음정보(List) 첫 건
    - source='import': 수입 묶음번호에서 나온 12자리 이력번호를 수입으로 강제 처리
    """
    if not number or not str(number).strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="이력번호 또는 묶음번호가 필요합니다.")
    data = await traceability_service.fetch_traceability(str(number).strip(), part_name=None, source=source)
    return TraceabilityInfo(
        historyNo=data.get("historyNo"),
        blNo=data.get("blNo"),
        partName=data.get("partName"),
        origin=data.get("origin"),
        slaughterDate=data.get("slaughterDate"),
        slaughterDateFrom=data.get("slaughterDateFrom"),
        slaughterDateTo=data.get("slaughterDateTo"),
        processingDateFrom=data.get("processingDateFrom"),
        processingDateTo=data.get("processingDateTo"),
        exporter=data.get("exporter"),
        importer=data.get("importer"),
        importDate=data.get("importDate"),
        partCode=data.get("partCode"),
        companyName=data.get("companyName"),
        recommendedExpiry=data.get("recommendedExpiry"),
        limitFromDt=data.get("limitFromDt"),
        limitToDt=data.get("limitToDt"),
        refrigCnvrsAt=data.get("refrigCnvrsAt"),
        refrigDistbPdBeginDe=data.get("refrigDistbPdBeginDe"),
        refrigDistbPdEndDe=data.get("refrigDistbPdEndDe"),
        birth_date=data.get("birth_date"),
        grade=data.get("grade"),
        source=data.get("source", "api"),
        server_maintenance=data.get("server_maintenance", False),
    )


@router.get(
    "/traceability/bundle",
    response_model=list[TraceabilityInfo],
    summary="MEAT-05 수입육 묶음번호로 이력 목록 조회 (클릭 시 상세는 /traceability?number=이력번호)",
    responses={
        400: {"description": "묶음번호 아님"},
        502: {"description": "묶음 조회 실패"},
        503: {"description": "API 연결 실패"},
    },
)
async def meat_traceability_bundle_list(
    number: Annotated[str, Query(description="수입 묶음번호 (A+숫자)")],
):
    """묶음번호 입력 시 해당 묶음에 속한 이력 목록을 반환. 각 이력번호로 GET /traceability?number= 이력번호 호출 시 상세 조회."""
    if not number or not str(number).strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="묶음번호가 필요합니다.")
    num = str(number).strip()
    if not apis._is_bundle_no(num):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="묶음번호 형식이 아닙니다. (A로 시작하는 20자리 이상)",
        )
    items = await apis.fetch_import_bundle_list(num)
    return [
        TraceabilityInfo(
            historyNo=d.get("historyNo"),
            blNo=d.get("blNo"),
            partName=d.get("partName"),
            origin=d.get("origin"),
            slaughterDate=d.get("slaughterDate"),
            slaughterDateFrom=d.get("slaughterDateFrom"),
            slaughterDateTo=d.get("slaughterDateTo"),
            processingDateFrom=d.get("processingDateFrom"),
            processingDateTo=d.get("processingDateTo"),
            exporter=d.get("exporter"),
            importer=d.get("importer"),
            importDate=d.get("importDate"),
            partCode=d.get("partCode"),
            companyName=d.get("companyName"),
            recommendedExpiry=d.get("recommendedExpiry"),
            limitFromDt=d.get("limitFromDt"),
            limitToDt=d.get("limitToDt"),
            refrigCnvrsAt=d.get("refrigCnvrsAt"),
            refrigDistbPdBeginDe=d.get("refrigDistbPdBeginDe"),
            refrigDistbPdEndDe=d.get("refrigDistbPdEndDe"),
            birth_date=d.get("birth_date"),
            grade=d.get("grade"),
            source=d.get("source", "api"),
            server_maintenance=d.get("server_maintenance", False),
        )
        for d in items
    ]
