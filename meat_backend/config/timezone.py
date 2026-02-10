"""한국 시간(KST) 기준 현재 시각. DB 저장·표시용."""
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))


def now_kst() -> datetime:
    """현재 시각을 한국 시간(KST)으로 반환. DB에 저장할 때 사용 (naive datetime)."""
    return datetime.now(KST).replace(tzinfo=None)
