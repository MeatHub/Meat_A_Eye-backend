# -*- coding: utf-8 -*-
"""
축산물 이력제 — DomesticService / ImportService. 실패 시 HTTPException.
"""
from __future__ import annotations

from fastapi import HTTPException

from .. import apis


def _is_domestic_pattern(trace_no: str) -> bool:
    """이력번호가 12자리 숫자이면 국내(Domestic), 아니면 수입(Import)."""
    t = (trace_no or "").strip()
    return len(t) == 12 and t.isdigit()


def _is_bundle_pattern(trace_no: str) -> bool:
    """수입육 묶음번호: A + 19~29자리 숫자면 묶음번호 API 사용."""
    return apis._is_bundle_no(trace_no)


class DomesticService:
    async def fetch(self, trace_no: str, part_name: str | None = None) -> dict:
        return await apis.fetch_domestic_traceability(trace_no, part_name)


class ImportService:
    async def fetch(self, trace_no: str) -> dict:
        if _is_bundle_pattern(trace_no):
            items = await apis.fetch_import_bundle_list(trace_no)
            return items[0] if items else await apis.fetch_import_traceability(trace_no)
        return await apis.fetch_import_traceability(trace_no)


class TraceabilityRouter:
    def __init__(self):
        self._domestic = DomesticService()
        self._import = ImportService()

    def _route(self, trace_no: str) -> str:
        return "domestic" if _is_domestic_pattern(trace_no) else "import"

    async def fetch(self, trace_no: str, part_name: str | None = None) -> dict:
        branch = self._route(trace_no)
        print(f"[TRACEABILITY] 분기: {'국내(Domestic)' if branch == 'domestic' else '수입(Import)'} | trace_no={trace_no}")

        if branch == "domestic":
            try:
                result = await self._domestic.fetch(trace_no, part_name)
                return result
            except HTTPException as e:
                if e.status_code == 503:
                    print("[TRACEABILITY] Domestic 503 → Import 재시도")
                    try:
                        return await self._import.fetch(trace_no)
                    except HTTPException as e2:
                        print(f"🚨 [REAL ERROR] {e2}")
                        raise HTTPException(status_code=503, detail="이력제 API 연결 실패. 잠시 후 다시 시도해 주세요.")
                print(f"🚨 [REAL ERROR] {e}")
                raise
        return await self._import.fetch(trace_no)


class TraceabilityService:
    def __init__(self):
        self._router = TraceabilityRouter()

    async def fetch_traceability(self, trace_no: str, part_name: str | None = None) -> dict:
        if not trace_no or not str(trace_no).strip():
            raise HTTPException(status_code=400, detail="이력번호가 필요합니다.")
        return await self._router.fetch(str(trace_no).strip(), part_name)
