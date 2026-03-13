"""Pydantic models for application settings."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class ThemeChoice(StrEnum):
    """Available UI theme options."""

    LIGHT = "light"
    DARK = "dark"
    AUTO = "auto"


class AppSettings(BaseModel):
    """Application configuration stored as a singleton row in SQLite."""

    theme: ThemeChoice = ThemeChoice.LIGHT
    auto_connect_favorites: bool = False
    scan_duration_seconds: int = Field(default=10, ge=5, le=60)
    adapter_name: str | None = None


class AppSettingsUpdate(BaseModel):
    """Partial update for application settings."""

    theme: ThemeChoice | None = None
    auto_connect_favorites: bool | None = None
    scan_duration_seconds: int | None = Field(default=None, ge=5, le=60)
    adapter_name: str | None = None
