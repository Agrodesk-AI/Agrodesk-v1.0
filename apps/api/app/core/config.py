from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "local"
    # Runtime role: must be NOSUPERUSER NOBYPASSRLS or tenant RLS is silently off.
    database_url: str = "postgresql+asyncpg://agrodesk_app:agrodesk_app@localhost:5433/agrodesk"
    # Owner role used only by alembic (DDL, extensions). Falls back to database_url.
    migrations_database_url: str | None = None
    # Escape hatch for the startup RLS guard; honoured only when env == "local".
    allow_rls_bypass_role: bool = False
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
    overdue_threshold_hours: int = 2
    stale_lead_days: int = 14
    whatsapp_provider: str = "fake"
    whatsapp_webhook_secret: str = "dev-whatsapp-secret"
    whatsapp_session_window_hours: int = 24
    outbox_max_attempts: int = 6
    # Knowledge base
    embedding_provider: str = "fake"  # fake | openai | voyage | cohere | …
    embedding_dims: int = 384
    kb_chunk_size: int = 800
    kb_chunk_overlap: int = 100
    kb_max_upload_bytes: int = 4 * 1024 * 1024
    # Lead routing (design §3.3)
    lead_routing_sla_hours: float = 4.0  # business hours before re-route
    lead_routing_max_reroutes: int = 3
    lead_routing_candidates: int = 4  # ranked list kept per interest
    farmer_interest_daily_limit: int = 3


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
