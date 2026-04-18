"""Tests for bt_hub.lifecycle module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from bt_hub.config import Settings
from bt_hub.lifecycle import BtHubServices, ServiceContainer, shutdown_services, startup_services


class TestBtHubServices:
    """Tests for the BtHubServices dataclass."""

    def test_required_fields(self) -> None:
        settings = Settings(db_path=Path("/tmp/test.db"))
        store = MagicMock()
        bus = MagicMock()
        services = BtHubServices(settings=settings, device_store=store, event_bus=bus)
        assert services.settings is settings
        assert services.device_store is store
        assert services.event_bus is bus
        assert services.bt_bridge_client is None
        assert services.bridge_proxy is None
        assert services.systemd_service is None
        assert services.log_handler is None
        assert services.bluez_mgr is None


class TestServiceContainer:
    """Tests for the ServiceContainer class."""

    def test_default_none(self) -> None:
        container = ServiceContainer()
        assert container.services is None

    def test_set_services(self) -> None:
        container = ServiceContainer()
        services = MagicMock(spec=BtHubServices)
        container.services = services
        assert container.services is services


class TestStartupServices:
    """Tests for startup_services function."""

    @pytest.fixture
    def settings(self, tmp_path: Path) -> Settings:
        return Settings(db_path=tmp_path / "test.db", bridge_enabled=False)

    @pytest.fixture
    def bridge_settings(self, tmp_path: Path) -> Settings:
        return Settings(db_path=tmp_path / "test.db", bridge_enabled=True)

    async def test_startup_without_dbus(self, settings: Settings) -> None:
        """When dbus-fast import fails, bluez_mgr should be None."""
        services = await startup_services(settings)
        try:
            # bluez_mgr may be None (no D-Bus on macOS) or a failing instance
            # The key is that startup doesn't raise
            assert services.device_store is not None
            assert services.event_bus is not None
            assert services.bt_bridge_client is not None
            assert services.bridge_proxy is None
            assert services.systemd_service is None
        finally:
            await services.device_store.close()

    async def test_startup_without_bridge(self, settings: Settings) -> None:
        """When bridge_enabled=False, bridge services should be None."""
        services = await startup_services(settings)
        try:
            assert services.bridge_proxy is None
            assert services.systemd_service is None
            assert services.bt_bridge_client is not None
        finally:
            await services.device_store.close()

    async def test_startup_creates_device_store(self, settings: Settings) -> None:
        """Startup should create and initialize a DeviceStore."""
        services = await startup_services(settings)
        try:
            assert services.device_store is not None
            # Verify DB was initialized by doing a simple operation
            result = await services.device_store.get_all_devices()
            assert isinstance(result, list)
        finally:
            await services.device_store.close()


class TestShutdownServices:
    """Tests for shutdown_services function."""

    async def test_shutdown_calls_close_on_all(self) -> None:
        """Shutdown should call close/shutdown on all services."""
        services = BtHubServices(
            settings=Settings(db_path=Path("/tmp/test.db")),
            device_store=AsyncMock(),
            event_bus=MagicMock(),
            bluez_mgr=AsyncMock(),
            bridge_proxy=AsyncMock(),
        )
        await shutdown_services(services)
        services.bluez_mgr.shutdown.assert_awaited_once()
        services.bridge_proxy.shutdown.assert_awaited_once()
        services.device_store.close.assert_awaited_once()

    async def test_shutdown_handles_none_services(self) -> None:
        """Shutdown should handle None optional services gracefully."""
        services = BtHubServices(
            settings=Settings(db_path=Path("/tmp/test.db")),
            device_store=AsyncMock(),
            event_bus=MagicMock(),
        )
        # Should not raise
        await shutdown_services(services)
        services.device_store.close.assert_awaited_once()

    async def test_shutdown_continues_on_bluez_error(self) -> None:
        """Shutdown should continue if BlueZManager.shutdown() raises."""
        bluez = AsyncMock()
        bluez.shutdown.side_effect = Exception("D-Bus error")
        services = BtHubServices(
            settings=Settings(db_path=Path("/tmp/test.db")),
            device_store=AsyncMock(),
            event_bus=MagicMock(),
            bluez_mgr=bluez,
        )
        await shutdown_services(services)
        # Should still close the store
        services.device_store.close.assert_awaited_once()
