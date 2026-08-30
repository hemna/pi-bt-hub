"""Dataclasses for application settings."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ThemeChoice(StrEnum):
    """Available UI theme options."""

    LIGHT = "light"
    DARK = "dark"
    AUTO = "auto"


@dataclass
class AppSettings:
    """Application configuration stored as a singleton row in SQLite."""

    theme: ThemeChoice = ThemeChoice.LIGHT
    auto_connect_favorites: bool = False
    scan_duration_seconds: int = 10
    adapter_name: str | None = None

    def __post_init__(self) -> None:
        # Clamp scan duration to valid range
        self.scan_duration_seconds = max(5, min(60, self.scan_duration_seconds))
        # Coerce theme string to enum
        if isinstance(self.theme, str):
            self.theme = ThemeChoice(self.theme)


@dataclass
class AppSettingsUpdate:
    """Partial update for application settings."""

    theme: ThemeChoice | None = None
    auto_connect_favorites: bool | None = None
    scan_duration_seconds: int | None = None
    adapter_name: str | None = None

    def __post_init__(self) -> None:
        if self.scan_duration_seconds is not None and not 5 <= self.scan_duration_seconds <= 60:
            msg = (
                f"scan_duration_seconds must be between 5 and 60, got {self.scan_duration_seconds}"
            )
            raise ValueError(msg)
        if isinstance(self.theme, str):
            self.theme = ThemeChoice(self.theme)  # raises ValueError for invalid values
