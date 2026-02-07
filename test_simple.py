"""간단한 API 연결 테스트"""
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from meat_backend.apis import fetch_kamis_price

async def test():
    print("Test 1: 소고기 1++등급 (서울)")
    try:
        result = await fetch_kamis_price("Beef_Tenderloin", "서울", "01")
        print(f"SUCCESS - 가격: {result.get('currentPrice', 0):,}원")
    except Exception as e:
        print(f"FAIL - {e}")
    
    print("\nTest 2: 소고기 1++등급 (대구)")
    try:
        result = await fetch_kamis_price("Beef_Tenderloin", "대구", "01")
        print(f"SUCCESS - 가격: {result.get('currentPrice', 0):,}원")
    except Exception as e:
        print(f"FAIL - {e}")
    
    print("\nTest 3: 돼지 전체 평균 (서울)")
    try:
        result = await fetch_kamis_price("Pork_Belly", "서울", "00")
        print(f"SUCCESS - 가격: {result.get('currentPrice', 0):,}원")
    except Exception as e:
        print(f"FAIL - {e}")

if __name__ == "__main__":
    asyncio.run(test())
