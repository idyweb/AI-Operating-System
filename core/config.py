"""
Application configuration via Pydantic Settings.
Why: Single source of truth for all env vars. Fails fast on startup
if required vars are missing — no silent misconfigs in production.
"""
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    app_env: str = Field(default="development")
    app_secret_key: str = Field(default="change-me")

    # Anthropic
    anthropic_api_key: str = Field(...)

    # Postgres
    postgres_host: str = Field(default="localhost")
    postgres_port: int = Field(default=5432)
    postgres_db: str = Field(default="second_brain")
    postgres_user: str = Field(default="second_brain_user")
    postgres_password: str = Field(default="localdevpassword")

    # Redis
    redis_url: str = Field(default="redis://localhost:6379/0")
    celery_broker_url: str = Field(default="redis://localhost:6379/0")
    celery_result_backend: str = Field(default="redis://localhost:6379/1")

    # Langfuse
    langfuse_public_key: str = Field(default="")
    langfuse_secret_key: str = Field(default="")
    langfuse_host: str = Field(default="https://cloud.langfuse.com")

    # Mission context — injected into every Claude call
    mission_goal_annual_usd: int = Field(default=50000)
    mission_owner: str = Field(default="iinyang")

    @property
    def database_url(self) -> str:
        """Async SQLAlchemy connection string."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:"
            f"{self.postgres_password}@{self.postgres_host}:"
            f"{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    """
    Cached settings instance.
    Why lru_cache: Settings object is expensive to build (reads .env,
    validates all fields). Cache it so we pay that cost once per process.
    """
    return Settings()