"""
SOCMIntelligence - ortam ayarlari
.env dosyasindan tum platform token'larini ve redis URL'ini yukler.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Redis (Celery broker + backend)
    redis_url: str = "redis://redis:6379/0"

    # CORS
    cors_origins: list[str] = ["http://localhost", "http://localhost:8080", "http://localhost:3000"]

    # Platform tokenlari - auth gerektiren tool'lar icin buraya eklenir.
    # Simdilik hicbiri zorunlu degil. Token'sız tool'lar (GitHub, Reddit public)
    # cache + rate limit korumasiyla calisir.
    # reddit_client_id: str | None = None
    # reddit_client_secret: str | None = None
    # telegram_api_id: str | None = None
    # telegram_api_hash: str | None = None
    # youtube_api_key: str | None = None

    # Tool timeout'lari (saniye)
    tool_timeout_default: int = 60
    tool_timeout_github: int = 45


settings = Settings()
