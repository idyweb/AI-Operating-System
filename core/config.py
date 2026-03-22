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

    # Telegram
    telegram_bot_token: str = Field(default="")
    telegram_webhook_secret: str = Field(default="")
    allowed_telegram_user_ids: str = Field(default="")

    # OpenRouter
    openrouter_api_key: str = Field(default="")
    openrouter_base_url: str = Field(default="https://openrouter.ai/api/v1")
    llm_model: str = Field(default="")

    @property
    def free_models(self) -> list[str]:
        """
        Ordered list of free models to try.
        Why ordered: First is preferred, falls back down the list on failure.
        """
        return [
        "meta-llama/llama-3.3-70b-instruct:free",      # Best free model
        "google/gemma-3-27b-it:free",                   # Google, strong
        "mistralai/mistral-small-3.1-24b-instruct:free", # Mistral, reliable
        "nousresearch/hermes-3-llama-3.1-405b:free",   # Huge, powerful
        "qwen/qwen3-4b:free",                           # Fast fallback
    ]

    @property
    def allowed_user_ids(self) -> list[int]:
        """
        Parse comma-separated user IDs into a list of ints.
        Why: Security — only allow your own Telegram account to trigger workflows.
        """
        if not self.allowed_telegram_user_ids:
            return []
        return [int(uid.strip()) for uid in self.allowed_telegram_user_ids.split(",")]

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