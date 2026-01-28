"""uvicorn 실행 엔트리포인트."""
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "meat_backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
