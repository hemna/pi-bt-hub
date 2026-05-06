"""SQLite-based persistence for application settings.

Device history has been removed — the app now shows only live BlueZ discovery results.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import aiosqlite

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)

_CREATE_SETTINGS_TABLE = """
CREATE TABLE IF NOT EXISTS app_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    theme TEXT NOT NULL DEFAULT 'light',
    auto_connect_favorites INTEGER NOT NULL DEFAULT 0,
    scan_duration_seconds INTEGER NOT NULL DEFAULT 10,
    adapter_name TEXT
)
"""

_INSERT_DEFAULT_SETTINGS = """
INSERT OR IGNORE INTO app_settings (id, theme, auto_connect_favorites, scan_duration_seconds)
VALUES (1, 'light', 0, 10)
"""


class DeviceStore:
    """Async SQLite store for application settings only."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def init_db(self) -> None:
        """Initialize the database, creating tables if needed."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(str(self._db_path))
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute(_CREATE_SETTINGS_TABLE)
        await self._db.execute(_INSERT_DEFAULT_SETTINGS)
        await self._db.commit()
        logger.info("Database initialized at %s", self._db_path)

    async def close(self) -> None:
        """Close the database connection."""
        if self._db:
            await self._db.close()
            self._db = None

    @property
    def db(self) -> aiosqlite.Connection:
        """Return the active database connection."""
        if self._db is None:
            msg = "Database not initialized. Call init_db() first."
            raise RuntimeError(msg)
        return self._db

    # --- Settings operations ---

    async def get_settings(self) -> dict[str, object]:
        """Return the current application settings."""
        async with self.db.execute(
            "SELECT theme, auto_connect_favorites, scan_duration_seconds, adapter_name "
            "FROM app_settings WHERE id = 1"
        ) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return {
                    "theme": "light",
                    "auto_connect_favorites": False,
                    "scan_duration_seconds": 10,
                    "adapter_name": None,
                }
            result = dict(row)
            result["auto_connect_favorites"] = bool(result["auto_connect_favorites"])
            return result

    async def update_settings(
        self,
        *,
        theme: str | None = None,
        auto_connect_favorites: bool | None = None,
        scan_duration_seconds: int | None = None,
        adapter_name: str | None = None,
    ) -> dict[str, object]:
        """Update application settings. Only provided fields are changed."""
        updates: list[str] = []
        params: list[object] = []

        if theme is not None:
            updates.append("theme = ?")
            params.append(theme)
        if auto_connect_favorites is not None:
            updates.append("auto_connect_favorites = ?")
            params.append(int(auto_connect_favorites))
        if scan_duration_seconds is not None:
            updates.append("scan_duration_seconds = ?")
            params.append(scan_duration_seconds)
        if adapter_name is not None:
            updates.append("adapter_name = ?")
            params.append(adapter_name)

        if updates:
            query = f"UPDATE app_settings SET {', '.join(updates)} WHERE id = 1"
            await self.db.execute(query, params)
            await self.db.commit()

        return await self.get_settings()
