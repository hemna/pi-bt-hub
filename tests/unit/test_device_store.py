"""Unit tests for SQLite device store."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest_asyncio

from bt_hub.services.device_store import DeviceStore

if TYPE_CHECKING:
    from pathlib import Path


@pytest_asyncio.fixture
async def store(tmp_path: Path) -> DeviceStore:
    """Provide a clean device store for each test."""
    s = DeviceStore(tmp_path / "test.db")
    await s.init_db()
    return s


class TestInitDb:
    """Tests for database initialization."""

    async def test_init_creates_tables(self, store: DeviceStore) -> None:
        async with store.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ) as cursor:
            tables = [row[0] for row in await cursor.fetchall()]
        assert "devices" in tables
        assert "app_settings" in tables

    async def test_init_creates_default_settings(self, store: DeviceStore) -> None:
        settings = await store.get_settings()
        assert settings["theme"] == "light"
        assert settings["auto_connect_favorites"] is False
        assert settings["scan_duration_seconds"] == 10
        assert settings["adapter_name"] is None


class TestUpsertDevice:
    """Tests for upserting devices."""

    async def test_upsert_new_device(self, store: DeviceStore) -> None:
        device = await store.upsert_device(
            "AA:BB:CC:DD:EE:FF",
            name="Test Speaker",
            device_type="audio",
        )
        assert device["mac_address"] == "AA:BB:CC:DD:EE:FF"
        assert device["name"] == "Test Speaker"
        assert device["device_type"] == "audio"
        assert device["first_seen"] is not None
        assert device["last_seen"] is not None

    async def test_upsert_existing_device_updates_last_seen(self, store: DeviceStore) -> None:
        first = await store.upsert_device("AA:BB:CC:DD:EE:FF", name="Speaker")
        first_seen = first["first_seen"]
        first_last_seen = first["last_seen"]

        second = await store.upsert_device("AA:BB:CC:DD:EE:FF", name="Speaker v2")
        assert second["first_seen"] == first_seen  # Unchanged
        assert second["last_seen"] >= first_last_seen  # type: ignore[operator]
        assert second["name"] == "Speaker v2"  # Updated

    async def test_upsert_preserves_alias(self, store: DeviceStore) -> None:
        await store.upsert_device("AA:BB:CC:DD:EE:FF", name="Speaker")
        await store.update_device("AA:BB:CC:DD:EE:FF", alias="My Speaker")
        updated = await store.upsert_device("AA:BB:CC:DD:EE:FF", name="Speaker")
        assert updated["alias"] == "My Speaker"


class TestGetDevices:
    """Tests for retrieving devices."""

    async def test_get_all_devices_empty(self, store: DeviceStore) -> None:
        devices = await store.get_all_devices()
        assert devices == []

    async def test_get_all_devices_returns_stored(self, store: DeviceStore) -> None:
        await store.upsert_device("AA:BB:CC:DD:EE:FF", name="Device 1")
        await store.upsert_device("11:22:33:44:55:66", name="Device 2")
        devices = await store.get_all_devices()
        assert len(devices) == 2

    async def test_get_all_devices_filter_favorites(self, store: DeviceStore) -> None:
        await store.upsert_device("AA:BB:CC:DD:EE:FF", name="Fav")
        await store.upsert_device("11:22:33:44:55:66", name="Not Fav")
        await store.update_device("AA:BB:CC:DD:EE:FF", is_favorite=True)
        devices = await store.get_all_devices(filter_type="favorites")
        assert len(devices) == 1
        assert devices[0]["mac_address"] == "AA:BB:CC:DD:EE:FF"

    async def test_get_device_by_mac(self, store: DeviceStore) -> None:
        await store.upsert_device("AA:BB:CC:DD:EE:FF", name="Speaker")
        device = await store.get_device("AA:BB:CC:DD:EE:FF")
        assert device is not None
        assert device["name"] == "Speaker"

    async def test_get_device_not_found(self, store: DeviceStore) -> None:
        device = await store.get_device("AA:BB:CC:DD:EE:FF")
        assert device is None


class TestUpdateDevice:
    """Tests for updating device fields."""

    async def test_update_alias(self, store: DeviceStore) -> None:
        await store.upsert_device("AA:BB:CC:DD:EE:FF", name="Speaker")
        updated = await store.update_device("AA:BB:CC:DD:EE:FF", alias="My Speaker")
        assert updated is not None
        assert updated["alias"] == "My Speaker"

    async def test_update_favorite(self, store: DeviceStore) -> None:
        await store.upsert_device("AA:BB:CC:DD:EE:FF", name="Speaker")
        updated = await store.update_device("AA:BB:CC:DD:EE:FF", is_favorite=True)
        assert updated is not None
        assert updated["is_favorite"] == 1  # SQLite stores as integer

    async def test_update_notes(self, store: DeviceStore) -> None:
        await store.upsert_device("AA:BB:CC:DD:EE:FF", name="Speaker")
        updated = await store.update_device("AA:BB:CC:DD:EE:FF", notes="Great audio")
        assert updated is not None
        assert updated["notes"] == "Great audio"

    async def test_update_nonexistent_device(self, store: DeviceStore) -> None:
        result = await store.update_device("AA:BB:CC:DD:EE:FF", alias="Phantom")
        assert result is None

    async def test_update_last_connected(self, store: DeviceStore) -> None:
        await store.upsert_device("AA:BB:CC:DD:EE:FF", name="Speaker")
        ts = "2026-03-10T14:30:00+00:00"
        updated = await store.update_device("AA:BB:CC:DD:EE:FF", last_connected=ts)
        assert updated is not None
        assert updated["last_connected"] == ts


class TestDeleteDevice:
    """Tests for deleting devices."""

    async def test_delete_existing_device(self, store: DeviceStore) -> None:
        await store.upsert_device("AA:BB:CC:DD:EE:FF", name="Speaker")
        deleted = await store.delete_device("AA:BB:CC:DD:EE:FF")
        assert deleted is True
        device = await store.get_device("AA:BB:CC:DD:EE:FF")
        assert device is None

    async def test_delete_nonexistent_device(self, store: DeviceStore) -> None:
        deleted = await store.delete_device("AA:BB:CC:DD:EE:FF")
        assert deleted is False


class TestSettings:
    """Tests for application settings operations."""

    async def test_get_default_settings(self, store: DeviceStore) -> None:
        settings = await store.get_settings()
        assert settings["theme"] == "light"
        assert settings["auto_connect_favorites"] is False
        assert settings["scan_duration_seconds"] == 10

    async def test_update_theme(self, store: DeviceStore) -> None:
        settings = await store.update_settings(theme="dark")
        assert settings["theme"] == "dark"

    async def test_update_scan_duration(self, store: DeviceStore) -> None:
        settings = await store.update_settings(scan_duration_seconds=30)
        assert settings["scan_duration_seconds"] == 30

    async def test_update_auto_connect(self, store: DeviceStore) -> None:
        settings = await store.update_settings(auto_connect_favorites=True)
        assert settings["auto_connect_favorites"] is True

    async def test_partial_update_preserves_other_fields(self, store: DeviceStore) -> None:
        await store.update_settings(theme="dark")
        settings = await store.update_settings(scan_duration_seconds=20)
        assert settings["theme"] == "dark"  # Preserved
        assert settings["scan_duration_seconds"] == 20  # Updated
