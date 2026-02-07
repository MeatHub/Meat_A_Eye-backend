"""
KAMIS API 연결 상태 테스트 스크립트
"""
import asyncio
import sys
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
sys.path.insert(0, str(Path(__file__).parent))

from meat_backend.apis import fetch_kamis_price, fetch_kamis_price_period


async def test_api_connection():
    """API 연결 상태 테스트"""
    print("=" * 60)
    print("KAMIS API 연결 상태 테스트")
    print("=" * 60)
    
    test_cases = [
        {
            "name": "소고기 - 전체 평균 (전국)",
            "part": "Beef_Tenderloin",
            "region": "전국",
            "grade": "00",
        },
        {
            "name": "소고기 - 1++등급 (서울)",
            "part": "Beef_Tenderloin",
            "region": "서울",
            "grade": "01",
        },
        {
            "name": "소고기 - 1++등급 (대구)",
            "part": "Beef_Tenderloin",
            "region": "대구",
            "grade": "01",
        },
        {
            "name": "돼지 - 전체 평균 (전국)",
            "part": "Pork_Belly",
            "region": "전국",
            "grade": "00",
        },
        {
            "name": "돼지 - 전체 평균 (서울)",
            "part": "Pork_Belly",
            "region": "서울",
            "grade": "00",
        },
    ]
    
    results = []
    
    for i, test in enumerate(test_cases, 1):
        print(f"\n[{i}/{len(test_cases)}] {test['name']}")
        print("-" * 60)
        
        try:
            # 실시간 가격 조회 테스트
            result = await fetch_kamis_price(
                part_name=test["part"],
                region=test["region"],
                grade_code=test["grade"],
            )
            
            if result and result.get("currentPrice", 0) > 0:
                print(f"[SUCCESS] 성공")
                print(f"   가격: {result['currentPrice']:,}원")
                print(f"   날짜: {result.get('priceDate', 'N/A')}")
                print(f"   등급: {result.get('grade', 'N/A')}")
                results.append({
                    "test": test["name"],
                    "status": "성공",
                    "price": result["currentPrice"],
                    "date": result.get("priceDate"),
                })
            else:
                print(f"[FAIL] 실패: 데이터 없음")
                results.append({
                    "test": test["name"],
                    "status": "실패",
                    "error": "데이터 없음",
                })
        except Exception as e:
            print(f"[FAIL] 실패: {str(e)}")
            results.append({
                "test": test["name"],
                "status": "실패",
                "error": str(e),
            })
    
    # 주별 가격 이력 테스트
    print(f"\n[추가 테스트] 주별 가격 이력 조회")
    print("-" * 60)
    try:
        history_result = await fetch_kamis_price_period(
            part_name="Beef_Tenderloin",
            region="전국",
            grade_code="00",
            weeks=1,
        )
        if history_result and len(history_result) > 0:
            print(f"[SUCCESS] 성공: {len(history_result)}개 데이터 포인트")
            print(f"   최신 데이터: {history_result[-1]}")
            results.append({
                "test": "주별 가격 이력",
                "status": "성공",
                "count": len(history_result),
            })
        else:
            print(f"[FAIL] 실패: 데이터 없음")
            results.append({
                "test": "주별 가격 이력",
                "status": "실패",
                "error": "데이터 없음",
            })
    except Exception as e:
        print(f"[FAIL] 실패: {str(e)}")
        results.append({
            "test": "주별 가격 이력",
            "status": "실패",
            "error": str(e),
        })
    
    # 결과 요약
    print("\n" + "=" * 60)
    print("테스트 결과 요약")
    print("=" * 60)
    
    success_count = sum(1 for r in results if r["status"] == "성공")
    total_count = len(results)
    
    for result in results:
        status_icon = "[OK]" if result["status"] == "성공" else "[FAIL]"
        print(f"{status_icon} {result['test']}: {result['status']}")
        if result["status"] == "성공" and "price" in result:
            print(f"   가격: {result['price']:,}원")
        elif result["status"] == "실패":
            print(f"   오류: {result.get('error', '알 수 없음')}")
    
    print(f"\n총 {total_count}개 테스트 중 {success_count}개 성공 ({success_count/total_count*100:.1f}%)")
    
    if success_count == total_count:
        print("\n[SUCCESS] 모든 테스트 통과!")
        return 0
    else:
        print(f"\n[WARNING] {total_count - success_count}개 테스트 실패")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(test_api_connection())
    sys.exit(exit_code)
