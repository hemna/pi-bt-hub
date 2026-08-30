"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """Application settings loaded from environment variables.

    All settings are read from environment variables with the BT_HUB_ prefix.
    """

    host: str = field(default_factory=lambda: os.getenv("BT_HUB_HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(os.getenv("BT_HUB_PORT", "8080")))
    db_path: Path = field(
        default_factory=lambda: Path(os.getenv("BT_HUB_DB_PATH", "data/bt_hub.db"))
    )
    adapter: str | None = field(default_factory=lambda: os.getenv("BT_HUB_ADAPTER"))
    log_level: str = field(default_factory=lambda: os.getenv("BT_HUB_LOG_LEVEL", "INFO"))
    bridge_enabled: bool = field(
        default_factory=lambda: os.getenv("BT_HUB_BRIDGE_ENABLED", "false").lower() == "true"
    )
    bridge_url: str = field(
        default_factory=lambda: os.getenv("BT_HUB_BRIDGE_URL", "http://localhost:8081")
    )


@lru_cache
def get_settings() -> Settings:
    """Return application settings singleton."""
    return Settings()
