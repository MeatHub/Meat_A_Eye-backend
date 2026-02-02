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
    kamis_api_url: str = ""
    kamis_action: str = "periodProductList"
    safe_food_api_key: str = ""
    safe_food_api_url: str = ""
    traceability_api_key: str = ""
    traceability_api_url: str = ""
    import_meat_api_key: str = ""
    import_meat_api_url: str = ""

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
