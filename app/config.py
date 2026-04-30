from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
  model_config = SettingsConfigDict(
    env_file=".env",
    env_file_encoding="utf-8",
    case_sensitive=True,
    extra="ignore",
  )

  # secrets — required, no default
  OPENAI_API_KEY: str = Field(default="", min_length=1)
  EXA_API_KEY: str = Field(default="", min_length=1)

  # storage
  DATABASE_URL: str = "sqlite:///./app.db"

  # ingestion defaults (overridable per-request via query params)
  DEFAULT_HISTORY_DAYS: int = 90
  DEFAULT_MIN_PCT: float = 2.0
  MOVEMENT_LOOKBACK_DAYS: int = 5

  # news fetching
  NEWS_BUFFER_BEFORE_DAYS: int = 2
  NEWS_BUFFER_AFTER_DAYS: int = 1
  NEWS_PER_QUERY: int = 10

  # llm
  RELEVANCE_MODEL: str = "gpt-4.1-mini"
  CHAT_MODEL: str = "gpt-4.1"
  RELEVANCE_THRESHOLD: float = Field(default=0.3, ge=0.0, le=1.0)

  # caching
  TICKER_PROFILE_TTL_DAYS: int = 30

  # concurrency
  INGEST_CONCURRENCY: int = Field(default=5, ge=1, le=20)


@lru_cache
def get_settings() -> Settings:
  return Settings()


settings = get_settings()