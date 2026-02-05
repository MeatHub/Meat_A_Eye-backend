"""축산물 이력제 API — fetch_traceability(history_no) 호환 레이어."""
from __future__ import annotations

from typing import Any

from .traceability_service import TraceabilityService

_trace_svc: TraceabilityService | None = None


def _get_service() -> TraceabilityService:
    global _trace_svc
    if _trace_svc is None:
        _trace_svc = TraceabilityService()
    return _trace_svc


async def fetch_traceability(history_no: str, part_name: str | None = None) -> list[dict[str, Any]]:
    """
    이력번호(OCR 결과)로 이력제 API 호출 후 정제된 JSON 리스트 반환.
    part_name: 국내육 cattle/pig 경로 선택용 (선택)
    하위 호환: list[dict] 반환 (api.py 등 기존 호출부)
    """
    svc = _get_service()
    result = await svc.fetch_traceability(history_no, part_name=part_name)
    if not result:
        return []
    return [result]
