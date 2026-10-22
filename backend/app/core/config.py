"""
Application configuration for Opsboard.
Loads from environment variables or .env file with safe defaults.
"""

from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Opsboard configuration parameters."""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    MONGODB_URI: str = "mongodb://localhost:27017/?directConnection=true"
    MONGODB_DB: str = "opsboard"
    MONGO_MAX_POOL: int = 20
    MONGO_MIN_POOL: int = 5

    # Security & Sessions
    SESSION_SECRET: str = "dev-secret-key-opsboard-super-secure-change-in-prod-32chars"
    SESSION_TTL_HOURS: int = 24
    COOKIE_NAME: str = "opsboard_session"
    COOKIE_SECURE: bool = False
    COOKIE_SAMESITE: str = "lax"
    APP_ORIGIN: str = "http://localhost:3000"

    # Worker & Outbox
    WORKER_POLL_INTERVAL_MS: int = 1000
    OUTBOX_MAX_ATTEMPTS: int = 6
    OUTBOX_LEASE_SECONDS: int = 30
    RUN_WORKER: bool = False

    # AI & Search Configuration
    AI_ENABLED: bool = True
    EMBEDDING_PROVIDER: str = "fake"  # 'fastembed' or 'fake'
    EMBEDDING_MODEL: str = "BAAI/bge-small-en-v1.5"
    LLM_PROVIDER: str = "fake"        # 'anthropic', 'openai', 'fake', or 'none'
    ANTHROPIC_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    LLM_MODEL: str = "claude-3-5-sonnet-20241022"
    AI_RATE_LIMIT_PER_MIN: int = 10

    # Observability
    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: str = "development"


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance to avoid re-reading environment variables."""
    return Settings()
