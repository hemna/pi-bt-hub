"""Shared FastAPI dependency providers.

This module breaks the circular dependency between main.py and API routers.
The singletons are set by main.py lifespan and accessed by API modules.
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any

from starlette.requests import Request
from starlette.responses import Response

if TYPE_CHECKING:
    from fastapi.templating import Jinja2Templates

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


def render_template(
    name: str,
    request: Request,
    context: dict[str, Any] | None = None,
    **kwargs: Any,
) -> Response:
    """Render a template with compatibility for both old and new Starlette versions.

    Starlette 0.36+ changed TemplateResponse signature to use `request` as a
    keyword argument instead of being part of the context dict.
    """
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


def get_bridge_service() -> SystemdService:
    assert _bridge_service is not None
    return _bridge_service


def set_bridge_service(service: SystemdService) -> None:
    global _bridge_service
    _bridge_service = service
