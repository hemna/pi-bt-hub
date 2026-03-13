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
from fastapi.templating import Jinja2Templates

from bt_hub.api import BluetoothError
from bt_hub.config import get_settings
from bt_hub.deps import (
    get_device_store,
    get_event_bus,
    get_templates,
    set_bridge_proxy,
    set_bt_bridge_client,
    set_device_store,
    set_event_bus,
    set_templates,
)
from bt_hub.services.bt_bridge_client import BtBridgeClient
from bt_hub.services.device_store import DeviceStore
from bt_hub.services.event_bus import EventBus

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = logging.getLogger(__name__)

__all__ = ["app", "create_app", "get_device_store", "get_event_bus", "get_templates"]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application startup and shutdown lifecycle."""
    settings = get_settings()

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    from bt_hub.services.log_handler import setup_sse_logging
    setup_sse_logging(level=getattr(logging, settings.log_level.upper(), logging.INFO))

    store = DeviceStore(settings.db_path)
    await store.init_db()
    set_device_store(store)

    bus = EventBus()
    set_event_bus(bus)

    # Legacy bridge client (for dashboard status probe)
    bridge_client = BtBridgeClient(
        settings.bridge_url if settings.bridge_enabled else None
    )
    set_bt_bridge_client(bridge_client)

    # Bridge proxy (only when bridge is enabled)
    bridge_proxy = None
    if settings.bridge_enabled:
        from bt_hub.services.bridge_proxy import BridgeProxy
        bridge_proxy = BridgeProxy(settings.bridge_url)
        await bridge_proxy.startup()
        set_bridge_proxy(bridge_proxy)
        logger.info("Bridge proxy enabled: %s", settings.bridge_url)

    template_dir = Path(__file__).parent / "templates"
    templates = Jinja2Templates(directory=str(template_dir))
    templates.env.globals["bridge_enabled"] = settings.bridge_enabled
    set_templates(templates)

    from bt_hub.api.adapter import set_bluetooth_manager
    from bt_hub.services.bluetooth import BlueZManager

    adapter_name = settings.adapter or "hci0"
    bt_manager = BlueZManager(bus, adapter_name=adapter_name)
    try:
        await bt_manager.startup()
    except Exception:
        logger.warning(
            "BlueZManager failed to start - Bluetooth features will be unavailable",
            exc_info=True,
        )
    set_bluetooth_manager(bt_manager)

    logger.info("Pi BT Hub started on %s:%d", settings.host, settings.port)

    yield

    if bridge_proxy:
        await bridge_proxy.shutdown()
    await bt_manager.shutdown()
    await store.close()
    logger.info("Pi BT Hub shut down")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="Pi BT Hub",
        description="Unified Bluetooth management and bridge web UI",
        version="0.1.0",
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
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = exc.errors()
        messages = [
            f"{'.'.join(str(loc) for loc in e.get('loc', []))}: {e.get('msg', '')}"
            for e in errors
        ]
        return JSONResponse(
            status_code=422,
            content={"error": "validation_error", "message": "; ".join(messages)},
        )

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
