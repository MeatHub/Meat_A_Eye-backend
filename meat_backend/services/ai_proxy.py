"""AI 서버(FastAPI 등) 연동 — 이미지 중계, Vision/OCR 분기."""
import logging
from pathlib import Path
from typing import Any

import httpx

from ..config.settings import settings

logger = logging.getLogger(__name__)


class AIProxyService:
    """프론트 이미지 → AI 서버 전달, 결과 정제 반환."""

    def __init__(self) -> None:
        self.base_url = settings.ai_server_url.rstrip("/")

    async def analyze(
        self,
        image_bytes: bytes,
        *,
        filename: str = "image.jpg",
        mode: str = "vision",
    ) -> dict[str, Any]:
        """이미지 전송, mode=ocr|vision에 따라 분기."""
        # AI 서버 엔드포인트: /ai/analyze
        url = f"{self.base_url}/ai/analyze"
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                files = {"file": (filename, image_bytes, "image/jpeg")}
                data = {"mode": mode}
                r = await client.post(url, files=files, data=data)
                r.raise_for_status()
                out = r.json()
        except httpx.TimeoutException:
            logger.warning("AI server timeout")
            return {"partName": None, "confidence": None, "historyNo": None, "error": "AI 서버 응답 지연"}
        except Exception as e:
            logger.exception("AI proxy error: %s", e)
            return {"partName": None, "confidence": None, "historyNo": None, "error": str(e)}

        # AI 서버 응답 형식에 맞게 정제
        # vision 모드: {"status": "success", "data": {"category": "...", "probability": 95.5, ...}}
        # ocr 모드: {"status": "success", "data": {"trace_number": "...", ...}}
        if out.get("status") != "success":
            error_msg = out.get("message") or out.get("error_code") or "AI 서버 오류"
            return {"partName": None, "confidence": None, "historyNo": None, "error": error_msg}

        data = out.get("data", {})
        
        if mode == "vision":
            # 부위명 추출 (category 또는 category_en)
            part_name = data.get("category") or data.get("category_en") or data.get("part_name")
            # 신뢰도 추출 (probability는 0-100 범위)
            confidence = data.get("probability")
            if confidence is not None:
                confidence = float(confidence) / 100.0  # 0-1 범위로 변환
            else:
                confidence = None
            history_no = None
        else:  # ocr 모드
            part_name = None
            confidence = None
            history_no = data.get("trace_number") or data.get("history_no") or data.get("historyNo")

        return {
            "partName": part_name,
            "confidence": confidence,
            "historyNo": history_no,
            "raw": out,
        }
