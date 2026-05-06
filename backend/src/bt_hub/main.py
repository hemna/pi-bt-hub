"""FastAPI application entry point for Pi BT Hub."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

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
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application startup and shutdown lifecycle."""
    settings = get_settings()

    # Start all services via lifecycle module
    services = await startup_services(settings)

    # Set deps singletons for backward compatibility with existing Depends() patterns
    set_device_store(services.device_store)
    set_event_bus(services.event_bus)
    set_bt_bridge_client(services.bt_bridge_client)
    if services.bridge_proxy:
        set_bridge_proxy(services.bridge_proxy)
    if services.systemd_service:
        set_bridge_service(services.systemd_service)
    if services.bluez_mgr:
        set_bluetooth_manager(services.bluez_mgr)

    # Templates
    templates = create_templates(bridge_enabled=settings.bridge_enabled)
    set_templates(templates)

    logger.info("Pi BT Hub started on %s:%d", settings.host, settings.port)

    yield

    await shutdown_services(services)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="Pi BT Hub",
        description="Unified Bluetooth management and bridge web UI",
        version="1.1.0",
        lifespan=lifespan,
    )

    static_dir = Path(__file__).parent.parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.exception_handler(BluetoothError)
    async def bluetooth_error_handler(request: Request, exc: BluetoothError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.error_code, "message": exc.error_message},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = exc.errors()
        messages = [
            f"{'.'.join(str(loc) for loc in e.get('loc', []))}: {e.get('msg', '')}" for e in errors
        ]
        return JSONResponse(
            status_code=422,
            content={"error": "validation_error", "message": "; ".join(messages)},
        )

    # Use existing module-level routers for standalone mode (backward compatibility)
    from bt_hub.api.adapter import router as adapter_router
    from bt_hub.api.devices import router as devices_router
    from bt_hub.api.logs import router as logs_router
    from bt_hub.api.settings import router as settings_router
    from bt_hub.api.websocket import router as websocket_router

    app.include_router(adapter_router)
    app.include_router(devices_router)
    app.include_router(websocket_router)
    app.include_router(settings_router)
    app.include_router(logs_router)

    # Conditionally include bridge routes
    if settings.bridge_enabled:
        from bt_hub.api.bridge import router as bridge_router

        app.include_router(bridge_router)

    return app


app = create_app()
