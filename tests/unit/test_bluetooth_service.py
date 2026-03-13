"""Unit tests for BlueZManager service (T020, T038).

Since we can't use real D-Bus on macOS, we mock dbus_fast internals.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from bt_hub.api import (
    AdapterUnavailableError,
    AlreadyPairedError,
    AlreadyScanningError,
    NotPairedError,
    PairingFailedError,
)
from bt_hub.models.device import AdapterState
from bt_hub.services.bluetooth import BlueZManager
from bt_hub.services.event_bus import EventBus


def _make_reply(body: list[Any] | None = None, error: bool = False) -> MagicMock:
    """Create a mock D-Bus reply message."""
    reply = MagicMock()
    reply.body = body or []
    reply.message_type.name = "ERROR" if error else "METHOD_RETURN"
    reply.error_name = "org.bluez.Error.Failed" if error else None
    return reply


@pytest.fixture
def event_bus() -> EventBus:
    return EventBus()


@pytest.fixture
def manager(event_bus: EventBus) -> BlueZManager:
    """Create a BlueZManager with a mocked D-Bus bus."""
    mgr = BlueZManager(event_bus, adapter_name="hci0")
    # Inject a mocked bus so we skip real D-Bus connection
    mock_bus = MagicMock()
    mock_bus.call = AsyncMock()
    mock_bus.make_method_message = MagicMock(return_value=MagicMock())
    mock_bus.add_message_handler = MagicMock()
    mock_bus.disconnect = MagicMock()
    mgr._bus = mock_bus
    return mgr


class TestGetAdapterState:
    """Tests for get_adapter_state."""

    async def test_returns_adapter_state(self, manager: BlueZManager) -> None:
        """get_adapter_state returns AdapterState when adapter exists."""
        adapter_props = {
            "Address": "AA:BB:CC:DD:EE:FF",
            "Name": "hci0",
            "Powered": True,
            "Discovering": False,
            "Discoverable": False,
        }
        manager._bus.call = AsyncMock(return_value=_make_reply([adapter_props]))

        state = await manager.get_adapter_state()

        assert isinstance(state, AdapterState)
        assert state.address == "AA:BB:CC:DD:EE:FF"
        assert state.name == "hci0"
        assert state.powered is True
        assert state.discovering is False
        assert state.discoverable is False

    async def test_raises_when_no_adapter(self, manager: BlueZManager) -> None:
        """get_adapter_state raises AdapterUnavailableError on D-Bus error."""
        manager._bus.call = AsyncMock(side_effect=Exception("No adapter"))

        with pytest.raises(AdapterUnavailableError):
            await manager.get_adapter_state()


class TestDiscovery:
    """Tests for start_discovery and stop_discovery."""

    async def test_start_discovery_publishes_event(
        self, manager: BlueZManager, event_bus: EventBus
    ) -> None:
        """start_discovery publishes scan_started event."""
        manager._bus.call = AsyncMock(return_value=_make_reply())
        sub_id, queue = event_bus.subscribe()

        await manager.start_discovery(duration_seconds=10)

        assert manager.is_scanning is True
        event = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert event.event == "scan_started"
        assert event.data["duration_seconds"] == 10

        event_bus.unsubscribe(sub_id)
        # Clean up scan task
        if manager._scan_task:
            manager._scan_task.cancel()

    async def test_start_discovery_already_scanning(self, manager: BlueZManager) -> None:
        """start_discovery raises AlreadyScanningError when already scanning."""
        manager._is_scanning = True

        with pytest.raises(AlreadyScanningError):
            await manager.start_discovery()

    async def test_stop_discovery_stops_scanning(
        self, manager: BlueZManager, event_bus: EventBus
    ) -> None:
        """stop_discovery sets is_scanning to False and publishes event."""
        manager._is_scanning = True
        manager._bus.call = AsyncMock(return_value=_make_reply())
        sub_id, queue = event_bus.subscribe()

        await manager.stop_discovery()

        assert manager.is_scanning is False
        event = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert event.event == "scan_stopped"
        event_bus.unsubscribe(sub_id)


class TestIsScanning:
    """Tests for is_scanning property."""

    def test_is_scanning_default_false(self, manager: BlueZManager) -> None:
        assert manager.is_scanning is False

    def test_is_scanning_reflects_internal_state(self, manager: BlueZManager) -> None:
        manager._is_scanning = True
        assert manager.is_scanning is True


class TestPairDevice:
    """Tests for pair_device."""

    async def test_pair_device_calls_pair(self, manager: BlueZManager) -> None:
        """pair_device calls the Pair D-Bus method."""
        # First call: GetAll (properties check) - device not paired
        props_reply = _make_reply([{"Paired": False, "Connected": False}])
        # Second call: Pair method
        pair_reply = _make_reply()
        manager._bus.call = AsyncMock(side_effect=[props_reply, pair_reply])

        await manager.pair_device("11:22:33:44:55:66")

        assert manager._bus.call.call_count == 2

    async def test_pair_already_paired_raises(self, manager: BlueZManager) -> None:
        """pair_device raises AlreadyPairedError when device is already paired."""
        props_reply = _make_reply([{"Paired": True}])
        manager._bus.call = AsyncMock(return_value=props_reply)

        with pytest.raises(AlreadyPairedError):
            await manager.pair_device("11:22:33:44:55:66")

    async def test_pairing_failure_raises(self, manager: BlueZManager) -> None:
        """pair_device raises PairingFailedError on D-Bus error during Pair."""
        from bt_hub.api import BluetoothError

        props_reply = _make_reply([{"Paired": False}])
        manager._bus.call = AsyncMock(
            side_effect=[
                props_reply,
                BluetoothError(error="dbus_error", message="Auth failed", status_code=502),
            ]
        )

        with pytest.raises(PairingFailedError):
            await manager.pair_device("11:22:33:44:55:66")


class TestConnectDevice:
    """Tests for connect_device."""

    async def test_connect_device_calls_connect(self, manager: BlueZManager) -> None:
        """connect_device calls the Connect D-Bus method."""
        props_reply = _make_reply([{"Paired": True, "Connected": False}])
        connect_reply = _make_reply()
        manager._bus.call = AsyncMock(side_effect=[props_reply, connect_reply])

        await manager.connect_device("11:22:33:44:55:66")

        assert manager._bus.call.call_count == 2

    async def test_connect_not_paired_raises(self, manager: BlueZManager) -> None:
        """connect_device raises NotPairedError when device is not paired."""
        props_reply = _make_reply([{"Paired": False, "Connected": False}])
        manager._bus.call = AsyncMock(return_value=props_reply)

        with pytest.raises(NotPairedError):
            await manager.connect_device("11:22:33:44:55:66")


class TestDisconnectDevice:
    """Tests for disconnect_device."""

    async def test_disconnect_device_calls_disconnect(self, manager: BlueZManager) -> None:
        """disconnect_device calls the Disconnect D-Bus method."""

        props_reply = _make_reply([{"Connected": True}])
        disconnect_reply = _make_reply()
        manager._bus.call = AsyncMock(side_effect=[props_reply, disconnect_reply])

        await manager.disconnect_device("11:22:33:44:55:66")

        assert manager._bus.call.call_count == 2

    async def test_disconnect_already_disconnected_raises(self, manager: BlueZManager) -> None:
        from bt_hub.api import AlreadyDisconnectedError

        props_reply = _make_reply([{"Connected": False}])
        manager._bus.call = AsyncMock(return_value=props_reply)

        with pytest.raises(AlreadyDisconnectedError):
            await manager.disconnect_device("11:22:33:44:55:66")


class TestTrustDevice:
    """Tests for trust_device."""

    async def test_trust_device_sets_property(self, manager: BlueZManager) -> None:
        """trust_device calls Set on Trusted property."""
        manager._bus.call = AsyncMock(return_value=_make_reply())

        await manager.trust_device("11:22:33:44:55:66")

        assert manager._bus.call.called


class TestRemoveDevice:
    """Tests for remove_device."""

    async def test_remove_device_calls_remove(self, manager: BlueZManager) -> None:
        """remove_device calls RemoveDevice on the adapter."""
        manager._bus.call = AsyncMock(return_value=_make_reply())

        await manager.remove_device("11:22:33:44:55:66")

        assert manager._bus.call.called
