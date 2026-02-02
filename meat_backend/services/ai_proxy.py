"""AI 서버(8001) 연동 — /predict 호출, Vision/OCR 분기, Fallback."""
import logging
import random
from typing import Any

import httpx

from ..config.settings import settings
from ..constants.meat_data import get_mock_analyze_response

logger = logging.getLogger(__name__)


class AIProxyService:
    """프론트 이미지 → AI 서버 /predict 또는 /ai/analyze 전달, 결과 정제 반환."""

    def __init__(self) -> None:
        self.base_url = (settings.ai_server_url or "").rstrip("/")

    async def analyze(
        self,
        image_bytes: bytes,
        *,
        filename: str = "image.jpg",
        mode: str = "vision",
    ) -> dict[str, Any]:
        """
        이미지 전송, mode=vision|ocr에 따라 분기.
        vision: /predict 호출 (EfficientNet-B2 + Grad-CAM)
        ocr: /ai/analyze 호출 (기존 OCR)
        """
        if not self.base_url:
            logger.warning("AI 서버 URL 없음 → Fallback")
            return self._fallback_response(mode)

        if mode == "vision":
            return await self._predict_vision(image_bytes, filename)
        return await self._analyze_ocr(image_bytes, filename)

    async def _predict_vision(
        self, image_bytes: bytes, filename: str
    ) -> dict[str, Any]:
        """AI 서버 /predict 호출 (B2 + Grad-CAM)."""
        url = f"{self.base_url}/predict"
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                files = {"file": (filename, image_bytes, "image/jpeg")}
                r = await client.post(url, files=files)
                r.raise_for_status()
                out = r.json()
        except httpx.TimeoutException:
            logger.warning("AI server /predict timeout")
            return self._fallback_response("vision")
        except Exception as e:
            logger.exception("AI proxy /predict error: %s", e)
            return self._fallback_response("vision")

        if out.get("status") != "success":
            return self._fallback_response("vision")

        return {
            "partName": out.get("class_name"),
            "confidence": out.get("confidence"),
            "historyNo": None,
            "heatmap_image": out.get("heatmap_image"),
            "raw": out,
        }

    async def _analyze_ocr(
        self, image_bytes: bytes, filename: str
    ) -> dict[str, Any]:
        """AI 서버 /ai/analyze (OCR 모드) 호출."""
        url = f"{self.base_url}/ai/analyze"
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                files = {"file": (filename, image_bytes, "image/jpeg")}
                data = {"mode": "ocr"}
                r = await client.post(url, files=files, data=data)
                r.raise_for_status()
                out = r.json()
        except httpx.TimeoutException:
            logger.warning("AI server /ai/analyze timeout")
            return {"partName": None, "confidence": None, "historyNo": None, "error": "AI 서버 응답 지연"}
        except Exception as e:
            logger.exception("AI proxy OCR error: %s", e)
            return {"partName": None, "confidence": None, "historyNo": None, "error": str(e)}

        if out.get("status") != "success":
            error_msg = out.get("message") or out.get("error_code") or "AI 서버 오류"
            return {"partName": None, "confidence": None, "historyNo": None, "error": error_msg}

        data = out.get("data", {})
        history_no = data.get("trace_number") or data.get("history_no") or data.get("historyNo")
        return {
            "partName": None,
            "confidence": None,
            "historyNo": history_no,
            "heatmap_image": None,
            "raw": out,
        }

    def _fallback_response(self, mode: str) -> dict[str, Any]:
        """AI 서버 미동작 시 meat_data Mock 사용."""
        mock = get_mock_analyze_response()
        return {
            "partName": mock["partName"],
            "confidence": mock["confidence"],
            "historyNo": mock["historyNo"],
            "heatmap_image": mock.get("heatmap_image"),
            "raw": mock["raw"],
            "error": None,
        }
