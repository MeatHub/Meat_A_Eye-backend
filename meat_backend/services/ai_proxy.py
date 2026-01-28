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
        """이미지 전송, type=ocr|vision에 따라 분기."""
        url = f"{self.base_url}/analyze"
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                files = {"image": (filename, image_bytes)}
                data = {"type": mode}
                r = await client.post(url, files=files, data=data)
                r.raise_for_status()
                out = r.json()
        except httpx.TimeoutException:
            logger.warning("AI server timeout")
            return {"partName": None, "confidence": None, "historyNo": None, "error": "AI 서버 응답 지연"}
        except Exception as e:
            logger.exception("AI proxy error: %s", e)
            return {"partName": None, "confidence": None, "historyNo": None, "error": str(e)}

        # 정제: AI 서버 응답 → 우리 스키마 (partName, confidence, historyNo)
        part_name = out.get("part_name") or out.get("partName")
        confidence = out.get("confidence_score") or out.get("confidence")
        history_no = out.get("history_no") or out.get("historyNo")
        return {
            "partName": part_name,
            "confidence": float(confidence) if confidence is not None else None,
            "historyNo": history_no,
            "raw": out,
        }
