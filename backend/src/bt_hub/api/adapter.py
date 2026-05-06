"""Adapter and scan API endpoints."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING, Annotated, Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.templating import Jinja2Templates  # noqa: TC002

from bt_hub.api import AdapterUnavailableError
from bt_hub.config import get_settings
from bt_hub.deps import (
    get_bluetooth_manager,
    get_bridge_service,
    get_bt_bridge_client,
    get_device_store,
    get_templates,
    render_template,
)
from bt_hub.models.device import (
    AdapterState,
    ScanResponse,
)
from bt_hub.services.bluetooth import BlueZManager  # noqa: TC001
from bt_hub.services.bt_bridge_client import BtBridgeClient  # noqa: TC001
from bt_hub.services.device_store import DeviceStore  # noqa: TC001

if TYPE_CHECKING:
    from bt_hub.lifecycle import ServiceContainer

logger = logging.getLogger(__name__)

router = APIRouter()


# --- JSON API endpoints ---


@router.get("/api/adapter", response_model=AdapterState)
async def get_adapter(
    bt: Annotated[BlueZManager, Depends(get_bluetooth_manager)],
) -> AdapterState:
    """Return the current Bluetooth adapter state."""
    state = await bt.get_adapter_state()
    logger.debug("Adapter state: powered=%s discovering=%s", state.powered, state.discovering)
    return state


@router.post("/api/adapter/power", response_model=AdapterState)
async def set_adapter_power(
    request: Request,
    bt: Annotated[BlueZManager, Depends(get_bluetooth_manager)],
    templates: Annotated[Jinja2Templates, Depends(get_templates)],
    powered: Annotated[bool | None, Form()] = None,
) -> object:
    """Toggle adapter power on or off."""
    power_value: bool = False
    if powered is not None:
        power_value = powered
    else:
        try:
            body = await request.json()
            power_value = bool(body.get("powered", False))
        except Exception:
            power_value = False

    logger.info("Setting adapter power to %s", power_value)
    state = await bt.set_powered(power_value)

    if "hx-request" in request.headers:
        return render_template("partials/adapter_status.html", request, adapter=state)
    return state


@router.post("/api/scan/start")
async def start_scan(
    request: Request,
    bt: Annotated[BlueZManager, Depends(get_bluetooth_manager)],
    store: Annotated[DeviceStore, Depends(get_device_store)],
    templates: Annotated[Jinja2Templates, Depends(get_templates)],
    duration: Optional[int] = None,
) -> object:
    """Start Bluetooth discovery scan."""
    if duration is None:
        settings = await store.get_settings()
        duration = int(settings.get("scan_duration_seconds", 10))
    logger.info("Starting scan for %d seconds", duration)

    # Launch discovery in background so the UI responds instantly
    asyncio.create_task(bt.start_discovery(duration_seconds=duration))

    # Return HTML partial for HTMX, or JSON for API clients
    if "hx-request" in request.headers:
        return render_template("partials/scan_progress.html", request, duration=duration)
    return ScanResponse(status="scanning", duration_seconds=duration)


@router.post("/api/scan/stop")
async def stop_scan(
    request: Request,
    bt: Annotated[BlueZManager, Depends(get_bluetooth_manager)],
    templates: Annotated[Jinja2Templates, Depends(get_templates)],
) -> object:
    """Stop Bluetooth discovery scan."""
    logger.info("Stopping scan")
    await bt.stop_discovery()

    if "hx-request" in request.headers:
        return render_template("partials/scan_stopped.html", request)
    return ScanResponse(status="stopped")


# --- HTML page endpoint ---


@router.get("/")
async def index_page(
    request: Request,
    bt: Annotated[BlueZManager, Depends(get_bluetooth_manager)],
    templates: Annotated[Jinja2Templates, Depends(get_templates)],
    bridge_client: Annotated[BtBridgeClient, Depends(get_bt_bridge_client)],
) -> object:
    """Serve the combined dashboard + devices page."""
    from bt_hub.api.devices import _build_runtime_state
    from bt_hub.models.device import DeviceRuntimeState

    try:
        adapter = await bt.get_adapter_state()
    except Exception:
        adapter = None

    # Probe BT Bridge if enabled
    bridge_status = None
    service_status = None
    settings = get_settings()
    if settings.bridge_enabled:
        bridge_status = await bridge_client.get_status()
        try:
            bridge_service = get_bridge_service()
            service_status = await bridge_service.status()
        except Exception:
            pass

    # Get live devices from BlueZ
    try:
        live_states = await bt.get_all_device_states()
    except Exception:
        live_states = {}

    devices: list[DeviceRuntimeState] = []
    for mac, live in live_states.items():
        devices.append(_build_runtime_state(mac, live))

    # Sort: connected first, then paired, then by name/MAC
    devices.sort(key=lambda d: (not d.connected, not d.paired, (d.name or d.mac_address).lower()))

    return render_template(
        "index.html",
        request,
        adapter=adapter,
        devices=devices,
        device_count=len(devices),
        is_scanning=bt.is_scanning,
        bridge_status=bridge_status,
        bridge_enabled=settings.bridge_enabled,
        service_status=service_status,
    )


# --- Factory functions for library usage ---


def create_api_router(container: ServiceContainer) -> APIRouter:
    """Create an APIRouter with adapter/scan API endpoints using the ServiceContainer."""
    api = APIRouter()

    @api.get("/api/adapter", response_model=AdapterState)
    async def get_adapter_factory() -> AdapterState:
        assert container.services is not None
        bt = container.services.bluez_mgr
        if bt is None:
            raise AdapterUnavailableError("BlueZManager not initialized")
        state = await bt.get_adapter_state()
        logger.debug("Adapter state: powered=%s discovering=%s", state.powered, state.discovering)
        return state

    @api.post("/api/adapter/power", response_model=AdapterState)
    async def set_adapter_power_factory(
        request: Request,
        powered: Annotated[bool | None, Form()] = None,
    ) -> object:
        assert container.services is not None
        bt = container.services.bluez_mgr
        if bt is None:
            raise AdapterUnavailableError("BlueZManager not initialized")
        power_value: bool = False
        if powered is not None:
            power_value = powered
        else:
            try:
                body = await request.json()
                power_value = bool(body.get("powered", False))
            except Exception:
                power_value = False
        logger.info("Setting adapter power to %s", power_value)
        state = await bt.set_powered(power_value)
        if "hx-request" in request.headers:
            return render_template("partials/adapter_status.html", request, adapter=state)
        return state

    @api.post("/api/scan/start")
    async def start_scan_factory(
        request: Request,
        duration: Optional[int] = None,
    ) -> object:
        assert container.services is not None
        bt = container.services.bluez_mgr
        store = container.services.device_store
        if bt is None:
            raise AdapterUnavailableError("BlueZManager not initialized")
        if duration is None:
            settings = await store.get_settings()
            duration = int(settings.get("scan_duration_seconds", 10))
        logger.info("Starting scan for %d seconds", duration)
        asyncio.create_task(bt.start_discovery(duration_seconds=duration))
        if "hx-request" in request.headers:
            return render_template("partials/scan_progress.html", request, duration=duration)
        return ScanResponse(status="scanning", duration_seconds=duration)

    @api.post("/api/scan/stop")
    async def stop_scan_factory(request: Request) -> object:
        assert container.services is not None
        bt = container.services.bluez_mgr
        if bt is None:
            raise AdapterUnavailableError("BlueZManager not initialized")
        logger.info("Stopping scan")
        await bt.stop_discovery()
        if "hx-request" in request.headers:
            return render_template("partials/scan_stopped.html", request)
        return ScanResponse(status="stopped")

    return api


def create_page_router(
    container: ServiceContainer,
    templates: Jinja2Templates,
    active_page_prefix: str = "bluetooth",
) -> APIRouter:
    """Create an APIRouter with the index page endpoint using the ServiceContainer."""
    pages = APIRouter()

    @pages.get("/")
    async def index_page_factory(request: Request) -> object:
        from bt_hub.api.devices import _build_runtime_state
        from bt_hub.models.device import DeviceRuntimeState

        assert container.services is not None
        bt = container.services.bluez_mgr

        try:
            adapter = await bt.get_adapter_state() if bt else None
        except Exception:
            adapter = None

        bridge_status = None
        service_status = None
        settings = container.services.settings
        if settings.bridge_enabled and container.services.bt_bridge_client:
            bridge_status = await container.services.bt_bridge_client.get_status()
            if container.services.systemd_service:
                with contextlib.suppress(Exception):
                    service_status = await container.services.systemd_service.status()

        # Get live devices from BlueZ
        try:
            live_states = await bt.get_all_device_states() if bt else {}
        except Exception:
            live_states = {}

        devices: list[DeviceRuntimeState] = []
        for mac, live in live_states.items():
            devices.append(_build_runtime_state(mac, live))

        devices.sort(
            key=lambda d: (not d.connected, not d.paired, (d.name or d.mac_address).lower())
        )

        return render_template(
            "index.html",
            request,
            adapter=adapter,
            devices=devices,
            device_count=len(devices),
            is_scanning=bt.is_scanning if bt else False,
            bridge_status=bridge_status,
            bridge_enabled=settings.bridge_enabled,
            service_status=service_status,
            active_page=active_page_prefix,
        )

    return pages
