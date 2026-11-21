from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "local"
    database_url: str = "postgresql+asyncpg://agrodesk:agrodesk@localhost:5432/agrodesk"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60
    refresh_token_days: int = 30
    otp_length: int = 6
    otp_ttl_minutes: int = 5
    otp_max_per_hour: int = 3
    otp_max_attempts: int = 5
    default_phone_region: str = "IN"
    sms_provider: str = "fake"
    # Planner defaults (IST). Beat schedule in celery_app.py is UTC.
    overdue_threshold_hours: int = 2
    stale_lead_days: int = 14


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
