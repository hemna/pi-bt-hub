"""Tests for deps.py getter guards (issue #1).

Verifies that getter functions raise RuntimeError (not AssertionError)
when their corresponding global singleton is None, and that they return
the value correctly once set.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import bt_hub.deps as deps_module
from bt_hub.deps import (
    get_bridge_proxy,
    get_bridge_service,
    get_bt_bridge_client,
    get_device_store,
    get_event_bus,
    get_templates,
    set_bridge_proxy,
    set_bridge_service,
    set_bt_bridge_client,
    set_device_store,
    set_event_bus,
    set_templates,
)


def _clear_all() -> None:
    """Reset all module-level singletons to None between tests."""
    deps_module._device_store = None
    deps_module._event_bus = None
    deps_module._templates = None
    deps_module._bt_bridge_client = None
    deps_module._bridge_proxy = None
    deps_module._bridge_service = None
    deps_module._bluetooth_manager = None


@pytest.fixture(autouse=True)
def reset_deps() -> None:
    """Ensure a clean slate for every test."""
    _clear_all()
    yield
    _clear_all()


# ---------------------------------------------------------------------------
# Each getter raises RuntimeError (not AssertionError) when global is None
# ---------------------------------------------------------------------------


def test_get_device_store_raises_runtime_error_when_none() -> None:
    with pytest.raises(RuntimeError, match="DeviceStore not initialized"):
        get_device_store()


def test_get_event_bus_raises_runtime_error_when_none() -> None:
    with pytest.raises(RuntimeError, match="EventBus not initialized"):
        get_event_bus()


def test_get_templates_raises_runtime_error_when_none() -> None:
    with pytest.raises(RuntimeError, match="Jinja2Templates not initialized"):
        get_templates()


def test_get_bt_bridge_client_raises_runtime_error_when_none() -> None:
    with pytest.raises(RuntimeError, match="BtBridgeClient not initialized"):
        get_bt_bridge_client()


def test_get_bridge_proxy_raises_runtime_error_when_none() -> None:
    with pytest.raises(RuntimeError, match="BridgeProxy not initialized"):
        get_bridge_proxy()


def test_get_bridge_service_raises_runtime_error_when_none() -> None:
    with pytest.raises(RuntimeError, match="SystemdService not initialized"):
        get_bridge_service()


# ---------------------------------------------------------------------------
# Guards raise RuntimeError, not AssertionError (would survive -O flag)
# ---------------------------------------------------------------------------


def test_get_device_store_raises_not_assert_error() -> None:
    exc = None
    try:
        get_device_store()
    except RuntimeError as e:
        exc = e
    assert exc is not None
    assert not isinstance(exc, AssertionError)


# ---------------------------------------------------------------------------
# Each getter returns the value once set via set_*
# ---------------------------------------------------------------------------


def test_get_device_store_returns_value_when_set() -> None:
    mock = MagicMock()
    set_device_store(mock)
    assert get_device_store() is mock


def test_get_event_bus_returns_value_when_set() -> None:
    mock = MagicMock()
    set_event_bus(mock)
    assert get_event_bus() is mock


def test_get_templates_returns_value_when_set() -> None:
    mock = MagicMock()
    set_templates(mock)
    assert get_templates() is mock


def test_get_bt_bridge_client_returns_value_when_set() -> None:
    mock = MagicMock()
    set_bt_bridge_client(mock)
    assert get_bt_bridge_client() is mock


def test_get_bridge_proxy_returns_value_when_set() -> None:
    mock = MagicMock()
    set_bridge_proxy(mock)
    assert get_bridge_proxy() is mock


def test_get_bridge_service_returns_value_when_set() -> None:
    mock = MagicMock()
    set_bridge_service(mock)
    assert get_bridge_service() is mock


# ---------------------------------------------------------------------------
# get_bluetooth_manager already raises AdapterUnavailableError (not RuntimeError)
# — ensure that behaviour is preserved
# ---------------------------------------------------------------------------


def test_get_bluetooth_manager_raises_adapter_unavailable_when_none() -> None:
    from bt_hub.api import AdapterUnavailableError
    from bt_hub.deps import get_bluetooth_manager

    with pytest.raises(AdapterUnavailableError):
        get_bluetooth_manager()


def test_get_bluetooth_manager_does_not_raise_assert_error() -> None:
    from bt_hub.api import AdapterUnavailableError
    from bt_hub.deps import get_bluetooth_manager

    try:
        get_bluetooth_manager()
    except AdapterUnavailableError:
        pass  # expected
    except AssertionError:
        pytest.fail(
            "get_bluetooth_manager raised AssertionError instead of AdapterUnavailableError"
        )
