"""에러 핸들링 — 401, 403, 404, 422, 429, 500 등 HTTP 상태 코드 세분화."""
import logging

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    """전역 예외 핸들러 등록."""

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(_: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "detail": "요청 데이터 형식 오류",
                "errors": exc.errors(),
            },
        )

    @app.exception_handler(Exception)
    async def internal_error_handler(_: Request, exc: Exception):
        logger.exception("Unhandled exception: %s", exc)
        from ..config.settings import settings
        detail = "서버 내부 오류"
        if settings.debug:
            detail = f"{type(exc).__name__}: {str(exc)}"
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": detail},
        )
