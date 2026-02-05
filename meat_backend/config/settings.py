"""환경 변수 및 앱 설정."""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """앱 설정 (env 로드)."""

    # App
    app_name: str = "Meat-A-Eye API"
    debug: bool = False
    port: int = 8000

    # MySQL
    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = ""
    mysql_database: str = "meat_eye"

    # JWT
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_expire_minutes: int = 60 * 24 * 7  # 7일
    jwt_guest_expire_minutes: int = 60 * 24  # 게스트 1일

    # CORS (프론트엔드)
    cors_origins: str = "http://localhost:3000,https://meat-a-eye.com,https://meat-a-eye.vercel.app"

    # AI 서버 (중계용)
    ai_server_url: str = "http://localhost:8001"

    # KAMIS / 식품영양정보 / 축산물이력제 (공공 API)
    kamis_api_key: str = ""
    kamis_cert_id: str = "meat-a-eye"
    kamis_api_url: str = ""
    kamis_action: str = "periodProductList"
    safe_food_api_key: str = ""
    safe_food_api_url: str = ""
    traceability_api_key: str = ""
    traceability_api_url: str = ""
    import_meat_api_key: str = ""
    import_meat_api_url: str = ""
    # 국내육 이력제 (MTRACE REST - api.mtrace.go.kr)
    mtrace_base_url: str = "http://api.mtrace.go.kr/rest"
    mtrace_user_id: str = ""
    mtrace_api_key: str = ""
    mtrace_call_type: str = "1"
    mtrace_proc_type: str = "1"
    # 수입육 이력제 (meatwatch REST) — SYS_ID에 API키 사용
    meatwatch_base_url: str = "http://www.meatwatch.go.kr/rest"
    meatwatch_sys_id: str = "test2000"  # IMPORT_MEAT_API_KEY 또는 SYS_ID

    # Web Push (VAPID)
    vapid_public_key: str = ""
    vapid_private_key: str = ""

    @property
    def database_url(self) -> str:
        return (
            f"mysql+aiomysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
        )

    @property
    def cors_origin_list(self) -> list[str]:
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
