"""CORS 설정 — 프론트(Next.js) ↔ 백엔드(Express/FastAPI) 도메인 차이 해결."""
from fastapi.middleware.cors import CORSMiddleware
from .settings import settings


def setup_cors(app):
    """FastAPI 앱에 CORS 미들웨어 적용."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
        expose_headers=["*"],
    )
