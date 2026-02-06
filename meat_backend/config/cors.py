"""CORS 설정 — 프론트(Next.js) ↔ 백엔드(Express/FastAPI) 도메인 차이 해결."""
from fastapi.middleware.cors import CORSMiddleware
from .settings import settings


def setup_cors(app):
    """FastAPI 앱에 CORS 미들웨어 적용."""
    origins = settings.cors_origin_list.copy()
    
    # 개발 환경: DEBUG 모드이면 모든 origin 허용 (모바일 테스트 편의)
    # 프로덕션: .env의 CORS_ORIGINS에 명시된 origin만 허용
    if settings.debug:
        # DEBUG 모드: 모든 origin 허용 (개발 편의성, 보안 주의!)
        allow_origins = ["*"]
        allow_credentials = False  # "*"와 credentials 동시 사용 불가
    else:
        # 프로덕션: 명시된 origin만 허용
        allow_origins = origins
        allow_credentials = True
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=allow_credentials,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
        expose_headers=["*"],
    )
