"""Shared FastAPI dependency providers.

This module breaks the circular dependency between main.py and API routers.
The singletons are set by main.py lifespan and accessed by API modules.
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response
    from starlette.templating import Jinja2Templates

    from bt_hub.services.bluetooth import BlueZManager
    from bt_hub.services.bridge_proxy import BridgeProxy
    from bt_hub.services.bt_bridge_client import BtBridgeClient
    from bt_hub.services.device_store import DeviceStore
    from bt_hub.services.event_bus import EventBus
    from bt_hub.services.systemd_service import SystemdService

_device_store: DeviceStore | None = None
_event_bus: EventBus | None = None
_templates: Jinja2Templates | None = None
_bt_bridge_client: BtBridgeClient | None = None
_bridge_proxy: BridgeProxy | None = None
_bridge_service: SystemdService | None = None
_bluetooth_manager: BlueZManager | None = None


def render_template(
    name: str,
    request: Request,
    context: dict[str, Any] | None = None,
    *,
    templates: Jinja2Templates | None = None,
    **kwargs: Any,
) -> Response:
    """Render a template with compatibility for both old and new Starlette versions.

    Starlette 0.36+ changed TemplateResponse signature to use `request` as a
    keyword argument instead of being part of the context dict.

    If ``templates`` is provided, it is used directly. Otherwise falls back to
    the module-level singleton (``get_templates()``).
    """
    if templates is None:
        templates = get_templates()
    ctx = context or {}
    ctx.update(kwargs)

    # Check if TemplateResponse accepts 'request' as keyword argument (Starlette 0.36+)
    sig = inspect.signature(templates.TemplateResponse)
    if "request" in sig.parameters:
        # New Starlette API (0.36+)
        return templates.TemplateResponse(request=request, name=name, context=ctx)
    else:
        # Old Starlette API (< 0.36)
        ctx["request"] = request
        return templates.TemplateResponse(name, ctx)


def get_device_store() -> DeviceStore:
    if _device_store is None:
        raise RuntimeError("DeviceStore not initialized — lifespan not completed")
    return _device_store


def set_device_store(store: DeviceStore) -> None:
    global _device_store
    _device_store = store


def get_event_bus() -> EventBus:
    if _event_bus is None:
        raise RuntimeError("EventBus not initialized — lifespan not completed")
    return _event_bus


def set_event_bus(bus: EventBus) -> None:
    global _event_bus
    _event_bus = bus


def get_templates() -> Jinja2Templates:
    if _templates is None:
        raise RuntimeError("Jinja2Templates not initialized — lifespan not completed")
    return _templates


def get_templates_optional() -> Jinja2Templates | None:
    """Return templates if configured, or None (for use in dual JSON/HTMX endpoints)."""
    return _templates


def set_templates(templates: Jinja2Templates) -> None:
    global _templates
    _templates = templates


def get_bt_bridge_client() -> BtBridgeClient:
    if _bt_bridge_client is None:
        raise RuntimeError("BtBridgeClient not initialized — lifespan not completed")
    return _bt_bridge_client


def set_bt_bridge_client(client: BtBridgeClient) -> None:
    global _bt_bridge_client
    _bt_bridge_client = client


def get_bridge_proxy() -> BridgeProxy:
    if _bridge_proxy is None:
        raise RuntimeError("BridgeProxy not initialized — lifespan not completed")
    return _bridge_proxy


def set_bridge_proxy(proxy: BridgeProxy) -> None:
    global _bridge_proxy
    _bridge_proxy = proxy


def get_bridge_service() -> SystemdService:
    if _bridge_service is None:
        raise RuntimeError("SystemdService not initialized — lifespan not completed")
    return _bridge_service


def set_bridge_service(service: SystemdService) -> None:
    global _bridge_service
    _bridge_service = service


def get_bluetooth_manager() -> BlueZManager:
    """Return the global BlueZManager instance."""
    from bt_hub.api import AdapterUnavailableError

    if _bluetooth_manager is None:
        raise AdapterUnavailableError("BlueZManager not initialized")
    return _bluetooth_manager


def set_bluetooth_manager(manager: BlueZManager) -> None:
    global _bluetooth_manager
    _bluetooth_manager = manager
