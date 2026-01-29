"""uvicorn 실행 엔트리포인트."""
import uvicorn
from meat_backend.config.settings import settings

if __name__ == "__main__":
    uvicorn.run(
        "meat_backend.main:app",
        host="0.0.0.0",
        port=settings.port,
        reload=settings.debug,
    )
