"""Meat-A-Eye FastAPI 앱 — CORS, JWT, /api/v1, Swagger."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from .config.settings import settings
from .config.database import init_db
from .config.cors import setup_cors
from .middleware.errors import register_exception_handlers
from .routes.v1 import router as v1_router

# SQLAlchemy 모델 등록 (init_db 시 create_all용)
from . import models  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 기동/종료 시 DB 초기화 등."""
    await init_db()
    yield
    # shutdown: connection pool 정리 등


def custom_openapi(app: FastAPI):
    """Swagger UI용 OpenAPI 스키마 — CORS, 에러 코드 명시."""
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=settings.app_name,
        version="1.0.0",
        description="Meat-A-Eye 웹/앱 백엔드 API. 인증, 냉장고, AI 분석, 시세 조회.",
        routes=app.routes,
    )
    openapi_schema["servers"] = [{"url": "/", "description": "Current"}]
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app = FastAPI(
    title=settings.app_name,
    description="Meat-A-Eye REST API — Auth, Fridge, AI, Meat",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

setup_cors(app)
register_exception_handlers(app)
app.include_router(v1_router)
app.openapi = lambda: custom_openapi(app)


@app.get("/health")
async def health():
    return {"status": "ok", "service": settings.app_name}
