"""Application configuration using pydantic-settings."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    host: str = "0.0.0.0"
    port: int = 8080
    db_path: Path = Path("data/bt_hub.db")
    adapter: str | None = None
    log_level: str = "INFO"

    # Bridge integration
    bridge_enabled: bool = False
    bridge_url: str = "http://localhost:8081"

    model_config = SettingsConfigDict(
        env_prefix="BT_HUB_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return application settings singleton."""
    return Settings()
