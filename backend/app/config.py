"""Application configuration using pydantic-settings."""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    DATABASE_URL: str = "postgresql://sih_app:changeme_dev@localhost:5432/sih26261"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Security
    SECRET_KEY: str = "change_this_to_a_random_secret_key_32chars"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Storage
    STORAGE_ROOT: str = "./storage"

    # OCR
    OCR_FAST_FAIL_THRESHOLD: float = 0.60
    OCR_DPI: int = 300
    OCR_MIN_TEXT_CHARS: int = 20  # min chars to consider native PDF text layer sufficient

    # ClamAV
    CLAMAV_ENABLED: bool = False
    CLAMAV_HOST: str = "localhost"
    CLAMAV_PORT: int = 3310

    # LLM for RAG
    LLM_PROVIDER: str = ""  # gemini | groq | claude | ""
    GEMINI_API_KEY: str = ""
    GROQ_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""

    OFFLINE_ONLY: bool = False

    # Upload limits
    MAX_FILE_SIZE_MB: int = 50
    MAX_PAGES: int = 200


@lru_cache
def get_settings() -> Settings:
    return Settings()
