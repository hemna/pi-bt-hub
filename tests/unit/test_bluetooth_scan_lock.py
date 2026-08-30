"""Tests for BlueZManager scan lifecycle concurrency (issues #2, #13)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import bt_hub.services.bluetooth as bt_module
from bt_hub.api import AlreadyScanningError
from bt_hub.services.bluetooth import BlueZManager
from bt_hub.services.event_bus import EventBus


def _make_manager() -> BlueZManager:
    """Create a BlueZManager with a real event bus and a mocked D-Bus."""
    bus = EventBus()
    mgr = BlueZManager(event_bus=bus, adapter_name="hci0")
    return mgr


@pytest.fixture
def manager() -> BlueZManager:
    return _make_manager()


# ---------------------------------------------------------------------------
# Helpers: patch the D-Bus heavy-lifters so tests don't touch hardware
# ---------------------------------------------------------------------------

def _patch_dbus(mgr: BlueZManager) -> tuple[AsyncMock, AsyncMock, AsyncMock]:
    """Return (call_method, stop_bridge, restart_bridge) mocks.

    Also patches module-level Variant (which is None when dbus_fast isn't installed)
    so that the SetDiscoveryFilter body-construction doesn't crash.
    """
    call_method = AsyncMock(return_value=[])
    stop_bridge = AsyncMock(return_value=False)
    restart_bridge = AsyncMock()
    mgr._call_method = call_method  # type: ignore[method-assign]
    mgr._stop_bridge_for_scan = stop_bridge  # type: ignore[method-assign]
    mgr._restart_bridge_after_scan = restart_bridge  # type: ignore[method-assign]
    # Silence hcitool subprocess
    mgr._hcitool_classic_scan = AsyncMock()  # type: ignore[method-assign]
    mgr.get_all_device_states = AsyncMock(return_value={})  # type: ignore[method-assign]

    # Patch Variant at the module level so body-list construction doesn't crash
    # when dbus_fast is not installed (Variant = None in that case).
    if bt_module.Variant is None:
        bt_module.Variant = MagicMock(return_value=object())  # type: ignore[assignment]

    return call_method, stop_bridge, restart_bridge


# ---------------------------------------------------------------------------
# Issue #2: scan lock prevents double-start
# ---------------------------------------------------------------------------

async def test_second_concurrent_start_raises_already_scanning(
    manager: BlueZManager,
) -> None:
    """Two concurrent start_discovery calls: second must raise AlreadyScanningError."""
    _patch_dbus(manager)

    # First call starts the scan (cancels the auto-stop task immediately)
    await manager.start_discovery(duration_seconds=5)
    assert manager.is_scanning is True

    # Second call must raise AlreadyScanningError — scan is already in progress
    with pytest.raises(AlreadyScanningError):
        await manager.start_discovery(duration_seconds=5)

    # Clean up
    await manager.stop_discovery()
    assert manager.is_scanning is False


async def test_stop_discovery_releases_lock_for_next_scan(
    manager: BlueZManager,
) -> None:
    """After stop_discovery(), a subsequent start_discovery() must succeed."""
    _patch_dbus(manager)

    await manager.start_discovery(duration_seconds=5)
    assert manager.is_scanning is True

    await manager.stop_discovery()
    assert manager.is_scanning is False

    # Second scan must succeed (lock released)
    await manager.start_discovery(duration_seconds=5)
    assert manager.is_scanning is True

    await manager.stop_discovery()
    assert manager.is_scanning is False


async def test_concurrent_starts_only_one_succeeds(
    manager: BlueZManager,
) -> None:
    """Truly concurrent start_discovery tasks: exactly one succeeds, one raises."""
    _patch_dbus(manager)

    results: list[Exception | None] = []

    async def _try_start() -> None:
        try:
            await manager.start_discovery(duration_seconds=5)
            results.append(None)  # success
        except AlreadyScanningError as exc:
            results.append(exc)

    # Launch both tasks concurrently
    await asyncio.gather(_try_start(), _try_start())

    successes = [r for r in results if r is None]
    failures = [r for r in results if isinstance(r, AlreadyScanningError)]

    assert len(successes) == 1, f"Expected exactly 1 success, got {successes}"
    assert len(failures) == 1, f"Expected exactly 1 failure, got {failures}"

    # Clean up
    await manager.stop_discovery()


# ---------------------------------------------------------------------------
# Issue #13: signal handler must NOT mutate _is_scanning
# ---------------------------------------------------------------------------

async def test_signal_handler_does_not_mutate_is_scanning(
    manager: BlueZManager,
) -> None:
    """PropertiesChanged signal for Discovering=False must NOT clear _is_scanning."""
    _patch_dbus(manager)

    await manager.start_discovery(duration_seconds=5)
    assert manager.is_scanning is True

    # Simulate BlueZ emitting PropertiesChanged{Discovering: False}.
    # We call _handle_properties_changed directly with already-unwrapped props
    # (simulating what _unwrap_props would produce) so we don't need dbus_fast types.
    from bt_hub.services.bluetooth import ADAPTER_INTERFACE

    # Patch _unwrap_props to return the dict as-is (no dbus_fast Variant wrapping)
    with patch("bt_hub.services.bluetooth._unwrap_props", side_effect=lambda d: d):
        await manager._handle_properties_changed(
            path=manager._adapter_path,
            body=[ADAPTER_INTERFACE, {"Discovering": False}, []],
        )

    # _is_scanning must still be True — the signal handler is not the owner
    assert manager.is_scanning is True, (
        "_is_scanning was mutated by the signal handler; only stop_discovery should clear it"
    )

    await manager.stop_discovery()
    assert manager.is_scanning is False
