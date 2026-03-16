"""Shared FastAPI dependency providers.

This module breaks the circular dependency between main.py and API routers.
The singletons are set by main.py lifespan and accessed by API modules.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi.templating import Jinja2Templates

    from bt_hub.services.bridge_proxy import BridgeProxy
    from bt_hub.services.bt_bridge_client import BtBridgeClient
    from bt_hub.services.device_store import DeviceStore
    from bt_hub.services.event_bus import EventBus

_device_store: DeviceStore | None = None
_event_bus: EventBus | None = None
_templates: Jinja2Templates | None = None
_bt_bridge_client: BtBridgeClient | None = None
_bridge_proxy: BridgeProxy | None = None


def get_device_store() -> DeviceStore:
    assert _device_store is not None
    return _device_store


def set_device_store(store: DeviceStore) -> None:
    global _device_store
    _device_store = store


def get_event_bus() -> EventBus:
    assert _event_bus is not None
    return _event_bus


def set_event_bus(bus: EventBus) -> None:
    global _event_bus
    _event_bus = bus


def get_templates() -> Jinja2Templates:
    assert _templates is not None
    return _templates


def get_templates_optional() -> Jinja2Templates | None:
    """Return templates if configured, or None (for use in dual JSON/HTMX endpoints)."""
    return _templates


def set_templates(templates: Jinja2Templates) -> None:
    global _templates
    _templates = templates


def get_bt_bridge_client() -> BtBridgeClient:
    assert _bt_bridge_client is not None
    return _bt_bridge_client


def set_bt_bridge_client(client: BtBridgeClient) -> None:
    global _bt_bridge_client
    _bt_bridge_client = client


def get_bridge_proxy() -> BridgeProxy:
    assert _bridge_proxy is not None
    return _bridge_proxy


def set_bridge_proxy(proxy: BridgeProxy) -> None:
    global _bridge_proxy
    _bridge_proxy = proxy
