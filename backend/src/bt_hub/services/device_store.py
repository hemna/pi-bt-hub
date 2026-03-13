"""SQLite-based persistence for Bluetooth devices and app settings."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import aiosqlite

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)

_CREATE_DEVICES_TABLE = """
CREATE TABLE IF NOT EXISTS devices (
    mac_address TEXT PRIMARY KEY,
    name TEXT,
    alias TEXT,
    device_type TEXT,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    last_connected TEXT,
    is_favorite INTEGER NOT NULL DEFAULT 0,
    notes TEXT
)
"""

_CREATE_SETTINGS_TABLE = """
CREATE TABLE IF NOT EXISTS app_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    theme TEXT NOT NULL DEFAULT 'light',
    auto_connect_favorites INTEGER NOT NULL DEFAULT 0,
    scan_duration_seconds INTEGER NOT NULL DEFAULT 10,
    adapter_name TEXT
)
"""

_CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_devices_last_seen ON devices(last_seen DESC)",
    (
        "CREATE INDEX IF NOT EXISTS idx_devices_is_favorite "
        "ON devices(is_favorite) WHERE is_favorite = 1"
    ),
]

_INSERT_DEFAULT_SETTINGS = """
INSERT OR IGNORE INTO app_settings (id, theme, auto_connect_favorites, scan_duration_seconds)
VALUES (1, 'light', 0, 10)
"""


class DeviceStore:
    """Async SQLite store for device history and application settings."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def init_db(self) -> None:
        """Initialize the database, creating tables if needed."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(str(self._db_path))
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute(_CREATE_DEVICES_TABLE)
        await self._db.execute(_CREATE_SETTINGS_TABLE)
        for idx_sql in _CREATE_INDEXES:
            await self._db.execute(idx_sql)
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

    # --- Device operations ---

    async def get_all_devices(
        self,
        *,
        filter_type: str = "all",
        sort_by: str = "last_seen",
    ) -> list[dict[str, object]]:
        """Return all stored devices, optionally filtered and sorted."""
        query = "SELECT * FROM devices"
        conditions: list[str] = []

        if filter_type == "favorites":
            conditions.append("is_favorite = 1")

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        sort_column = {
            "last_seen": "last_seen DESC",
            "name": "COALESCE(alias, name, mac_address) ASC",
            "last_connected": "last_connected DESC NULLS LAST",
        }.get(sort_by, "last_seen DESC")
        query += f" ORDER BY {sort_column}"

        async with self.db.execute(query) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_device(self, mac_address: str) -> dict[str, object] | None:
        """Return a single device by MAC address, or None if not found."""
        async with self.db.execute(
            "SELECT * FROM devices WHERE mac_address = ?",
            (mac_address,),
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def upsert_device(
        self,
        mac_address: str,
        *,
        name: str | None = None,
        device_type: str | None = None,
        rssi: int | None = None,
    ) -> dict[str, object]:
        """Insert a new device or update last_seen for an existing one."""
        now = datetime.now(UTC).isoformat()
        existing = await self.get_device(mac_address)

        if existing:
            await self.db.execute(
                "UPDATE devices SET last_seen = ?, name = COALESCE(?, name), "
                "device_type = COALESCE(?, device_type) WHERE mac_address = ?",
                (now, name, device_type, mac_address),
            )
        else:
            await self.db.execute(
                "INSERT INTO devices (mac_address, name, device_type, first_seen, last_seen) "
                "VALUES (?, ?, ?, ?, ?)",
                (mac_address, name, device_type, now, now),
            )
        await self.db.commit()

        result = await self.get_device(mac_address)
        assert result is not None
        return result

    async def update_device(
        self,
        mac_address: str,
        *,
        alias: str | None = None,
        is_favorite: bool | None = None,
        notes: str | None = None,
        last_connected: str | None = None,
    ) -> dict[str, object] | None:
        """Update user-editable fields on a device. Returns None if not found."""
        existing = await self.get_device(mac_address)
        if not existing:
            return None

        updates: list[str] = []
        params: list[object] = []

        if alias is not None:
            updates.append("alias = ?")
            params.append(alias)
        if is_favorite is not None:
            updates.append("is_favorite = ?")
            params.append(int(is_favorite))
        if notes is not None:
            updates.append("notes = ?")
            params.append(notes)
        if last_connected is not None:
            updates.append("last_connected = ?")
            params.append(last_connected)

        if updates:
            params.append(mac_address)
            query = f"UPDATE devices SET {', '.join(updates)} WHERE mac_address = ?"
            await self.db.execute(query, params)
            await self.db.commit()

        return await self.get_device(mac_address)

    async def delete_device(self, mac_address: str) -> bool:
        """Delete a device from the store. Returns True if deleted, False if not found."""
        existing = await self.get_device(mac_address)
        if not existing:
            return False
        await self.db.execute(
            "DELETE FROM devices WHERE mac_address = ?",
            (mac_address,),
        )
        await self.db.commit()
        return True

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
