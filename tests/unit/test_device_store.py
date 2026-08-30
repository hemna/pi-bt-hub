"""Tests for DeviceStore — SQL allowlist and aiosqlite.Error wrapping (#3, #4)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

import aiosqlite
import pytest

from bt_hub.services.device_store import DeviceStore

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
async def store(tmp_path: Path) -> DeviceStore:
    s = DeviceStore(tmp_path / "test.db")
    await s.init_db()
    yield s
    await s.close()


class TestGetSettings:
    """Tests for DeviceStore.get_settings."""

    async def test_returns_defaults_on_empty_db(self, store: DeviceStore) -> None:
        """get_settings returns sensible defaults when the row exists (from INSERT OR IGNORE)."""
        result = await store.get_settings()
        assert result["theme"] == "light"
        assert result["auto_connect_favorites"] is False
        assert result["scan_duration_seconds"] == 10
        assert result["adapter_name"] is None

    async def test_wraps_aiosqlite_error_in_runtime_error(self, store: DeviceStore) -> None:
        """get_settings wraps aiosqlite.Error in RuntimeError (#4)."""
        with (
            patch.object(
                store.db,
                "execute",
                side_effect=aiosqlite.Error("disk full"),
            ),
            pytest.raises(RuntimeError, match="Database error reading settings"),
        ):
            await store.get_settings()


class TestUpdateSettings:
    """Tests for DeviceStore.update_settings — SQL allowlist and error wrapping."""

    async def test_update_theme(self, store: DeviceStore) -> None:
        """update_settings persists a new theme value."""
        result = await store.update_settings(theme="dark")
        assert result["theme"] == "dark"

    async def test_update_scan_duration(self, store: DeviceStore) -> None:
        """update_settings persists scan_duration_seconds."""
        result = await store.update_settings(scan_duration_seconds=30)
        assert result["scan_duration_seconds"] == 30

    async def test_update_auto_connect_favorites(self, store: DeviceStore) -> None:
        """update_settings persists auto_connect_favorites as bool."""
        result = await store.update_settings(auto_connect_favorites=True)
        assert result["auto_connect_favorites"] is True

    async def test_update_noop_when_all_none(self, store: DeviceStore) -> None:
        """update_settings with all None args is a no-op (no DB write)."""
        before = await store.get_settings()
        result = await store.update_settings()
        assert result == before

    async def test_column_allowlist_only_has_known_columns(self) -> None:
        """_SETTINGS_COLUMNS only references columns present in the schema (#3)."""
        known_columns = {
            "theme",
            "auto_connect_favorites",
            "scan_duration_seconds",
            "adapter_name",
        }
        assert set(DeviceStore._SETTINGS_COLUMNS.values()) == known_columns

    async def test_wraps_aiosqlite_error_in_runtime_error(self, store: DeviceStore) -> None:
        """update_settings wraps aiosqlite.Error in RuntimeError (#4)."""
        with (
            patch.object(
                store.db,
                "execute",
                side_effect=aiosqlite.Error("disk full"),
            ),
            pytest.raises(RuntimeError, match="Database error updating settings"),
        ):
            await store.update_settings(theme="dark")
