"""Router aggregation for library usage.

Provides top-level factory functions that aggregate per-module routers into
a single API router, page router, or WebSocket router. Used by host apps
(e.g., digipi-web) to mount all bt-hub routes at once.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter

from bt_hub.api import adapter, bridge, devices, logs, websocket
from bt_hub.api import settings as settings_mod

if TYPE_CHECKING:
    from fastapi.templating import Jinja2Templates

    from bt_hub.lifecycle import ServiceContainer


def create_api_routers(container: ServiceContainer) -> APIRouter:
    """Aggregate all API routers into a single APIRouter.

    All routes are always registered; individual handlers check whether
    the relevant service is available (e.g., bridge_proxy is not None).
    """
    router = APIRouter()
    router.include_router(adapter.create_api_router(container), tags=["adapter"])
    router.include_router(devices.create_api_router(container), tags=["devices"])
    router.include_router(bridge.create_api_router(container), tags=["bridge"])
    router.include_router(settings_mod.create_api_router(container), tags=["settings"])
    router.include_router(logs.create_api_router(container), tags=["logs"])
    return router


def create_page_routers(
    container: ServiceContainer,
    templates: Jinja2Templates,
    active_page_prefix: str = "bluetooth",
) -> APIRouter:
    """Aggregate all page routers into a single APIRouter."""
    router = APIRouter()
    router.include_router(
        adapter.create_page_router(container, templates, active_page_prefix),
        tags=["pages"],
    )
    router.include_router(
        devices.create_page_router(container, templates, active_page_prefix),
        tags=["pages"],
    )
    router.include_router(
        bridge.create_page_router(container, templates, active_page_prefix),
        tags=["pages"],
    )
    router.include_router(
        settings_mod.create_page_router(container, templates, active_page_prefix),
        tags=["pages"],
    )
    router.include_router(
        logs.create_page_router(container, templates, active_page_prefix),
        tags=["pages"],
    )
    return router


def create_ws_router(
    container: ServiceContainer,
    path: str = "/ws",
) -> APIRouter:
    """Create the WebSocket router. Delegates to websocket.create_ws_router."""
    return websocket.create_ws_router(container, path=path)
