"""Adapter and scan API endpoints."""

from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING, Annotated

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
    # Handle form data from HTMX (hx-vals sends form-encoded data)
    power_value: bool = False
    if powered is not None:
        power_value = powered
    else:
        # Try to get from JSON body for API clients
        try:
            body = await request.json()
            power_value = bool(body.get("powered", False))
        except Exception:
            power_value = False

    logger.info("Setting adapter power to %s", power_value)
    state = await bt.set_powered(power_value)

    # Return HTML partial for HTMX, or JSON for API clients
    if "hx-request" in request.headers:
        return render_template("partials/adapter_status.html", request, adapter=state)
    return state


@router.post("/api/scan/start")
async def start_scan(
    request: Request,
    bt: Annotated[BlueZManager, Depends(get_bluetooth_manager)],
    store: Annotated[DeviceStore, Depends(get_device_store)],
    templates: Annotated[Jinja2Templates, Depends(get_templates)],
    duration: int = 10,
) -> object:
    """Start Bluetooth discovery scan."""
    logger.info("Starting scan for %d seconds", duration)
    await bt.start_discovery(duration_seconds=duration)

    # Upsert all BlueZ-known devices into the store immediately so they
    # persist even after StopDiscovery removes transient devices.
    try:
        live_states = await bt.get_all_device_states()
        for mac, props in live_states.items():
            await store.upsert_device(
                mac,
                name=props.get("name"),
                device_type=props.get("device_type"),
            )
    except Exception:
        logger.debug("Failed to upsert devices at scan start", exc_info=True)

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

    # Return HTML partial for HTMX, or JSON for API clients
    if "hx-request" in request.headers:
        return render_template("partials/scan_stopped.html", request)
    return ScanResponse(status="stopped")


# --- HTML page endpoint ---


@router.get("/")
async def index_page(
    request: Request,
    bt: Annotated[BlueZManager, Depends(get_bluetooth_manager)],
    store: Annotated[DeviceStore, Depends(get_device_store)],
    templates: Annotated[Jinja2Templates, Depends(get_templates)],
    bridge_client: Annotated[BtBridgeClient, Depends(get_bt_bridge_client)],
) -> object:
    """Serve the main index page with adapter state and device summary."""
    try:
        adapter = await bt.get_adapter_state()
    except Exception:
        adapter = None

    # Probe BT Bridge if enabled (graceful fallback)
    bridge_status = None
    service_status = None
    settings = get_settings()
    if settings.bridge_enabled:
        bridge_status = await bridge_client.get_status()
        # Get systemd service status
        try:
            bridge_service = get_bridge_service()
            service_status = await bridge_service.status()
        except Exception:
            pass  # Service not available

    # Get device counts (exclude ignored from main count)
    all_devices = await store.get_all_devices(include_ignored=True)
    devices = [d for d in all_devices if not d.get("is_ignored", False)]

    # Get live states to count paired/connected
    try:
        live_states = await bt.get_all_device_states()
    except Exception:
        live_states = {}

    paired_count = 0
    connected_count = 0
    favorite_count = 0
    ignored_count = 0

    for d in all_devices:
        mac = str(d["mac_address"])
        live = live_states.get(mac, {})
        if d.get("is_ignored", False):
            ignored_count += 1
            continue  # Don't count ignored devices in other stats
        if live.get("paired", False):
            paired_count += 1
        if live.get("connected", False):
            connected_count += 1
        if d.get("is_favorite", False):
            favorite_count += 1

    return render_template(
        "index.html",
        request,
        adapter=adapter,
        device_count=len(devices),
        paired_count=paired_count,
        connected_count=connected_count,
        favorite_count=favorite_count,
        ignored_count=ignored_count,
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
        duration: int = 10,
    ) -> object:
        assert container.services is not None
        bt = container.services.bluez_mgr
        store = container.services.device_store
        if bt is None:
            raise AdapterUnavailableError("BlueZManager not initialized")
        logger.info("Starting scan for %d seconds", duration)
        await bt.start_discovery(duration_seconds=duration)
        try:
            live_states = await bt.get_all_device_states()
            for mac, props in live_states.items():
                await store.upsert_device(
                    mac,
                    name=props.get("name"),
                    device_type=props.get("device_type"),
                )
        except Exception:
            logger.debug("Failed to upsert devices at scan start", exc_info=True)
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
        assert container.services is not None
        bt = container.services.bluez_mgr
        store = container.services.device_store

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

        all_devices = await store.get_all_devices(include_ignored=True)
        devices = [d for d in all_devices if not d.get("is_ignored", False)]

        try:
            live_states = await bt.get_all_device_states() if bt else {}
        except Exception:
            live_states = {}

        paired_count = 0
        connected_count = 0
        favorite_count = 0
        ignored_count = 0

        for d in all_devices:
            mac = str(d["mac_address"])
            live = live_states.get(mac, {})
            if d.get("is_ignored", False):
                ignored_count += 1
                continue
            if live.get("paired", False):
                paired_count += 1
            if live.get("connected", False):
                connected_count += 1
            if d.get("is_favorite", False):
                favorite_count += 1

        return render_template(
            "index.html",
            request,
            adapter=adapter,
            device_count=len(devices),
            paired_count=paired_count,
            connected_count=connected_count,
            favorite_count=favorite_count,
            ignored_count=ignored_count,
            bridge_status=bridge_status,
            bridge_enabled=settings.bridge_enabled,
            service_status=service_status,
            active_page=active_page_prefix,
        )

    return pages
