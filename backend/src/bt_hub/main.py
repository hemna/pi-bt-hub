"""Starlette application entry point for Pi BT Hub."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles

from bt_hub.api import BluetoothError
from bt_hub.config import get_settings
from bt_hub.deps import (
    get_device_store,
    get_event_bus,
    get_templates,
    set_bluetooth_manager,
    set_bridge_proxy,
    set_bridge_service,
    set_bt_bridge_client,
    set_device_store,
    set_event_bus,
    set_templates,
)
from bt_hub.lifecycle import create_templates, shutdown_services, startup_services

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = logging.getLogger(__name__)

__all__ = ["app", "create_app", "get_device_store", "get_event_bus", "get_templates"]


@asynccontextmanager
async def lifespan(app: Starlette) -> AsyncIterator[None]:
    """Application startup and shutdown lifecycle."""
    settings = get_settings()

    services = await startup_services(settings)

    set_device_store(services.device_store)
    set_event_bus(services.event_bus)
    set_bt_bridge_client(services.bt_bridge_client)
    if services.bridge_proxy:
        set_bridge_proxy(services.bridge_proxy)
    if services.systemd_service:
        set_bridge_service(services.systemd_service)
    if services.bluez_mgr:
        set_bluetooth_manager(services.bluez_mgr)

    templates = create_templates(bridge_enabled=settings.bridge_enabled)
    set_templates(templates)

    logger.info("Pi BT Hub started on %s:%d", settings.host, settings.port)

    yield

    await shutdown_services(services)


async def _bluetooth_error_handler(request: Request, exc: BluetoothError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.error_code, "message": exc.error_message},
    )


def create_app() -> Starlette:
    """Create and configure the Starlette application."""
    from bt_hub.api.adapter import router as adapter_router
    from bt_hub.api.devices import router as devices_router
    from bt_hub.api.logs import router as logs_router
    from bt_hub.api.settings import router as settings_router
    from bt_hub.api.websocket import router as websocket_router

    settings = get_settings()

    # Flatten all routes from each router into a single list
    routes = list(adapter_router.routes)
    routes += list(devices_router.routes)
    routes += list(websocket_router.routes)
    routes += list(settings_router.routes)
    routes += list(logs_router.routes)

    if settings.bridge_enabled:
        from bt_hub.api.bridge import router as bridge_router
        routes += list(bridge_router.routes)

    static_dir = Path(__file__).parent.parent / "static"
    if static_dir.exists():
        routes.append(Mount("/static", app=StaticFiles(directory=str(static_dir)), name="static"))

    return Starlette(
        lifespan=lifespan,
        routes=routes,
        exception_handlers={BluetoothError: _bluetooth_error_handler},  # type: ignore[dict-item]
    )


app = create_app()
