"""Adapter and scan API endpoints."""

from __future__ import annotations

import contextlib
import dataclasses
import logging
from typing import TYPE_CHECKING

from starlette.responses import JSONResponse
from starlette.routing import Route, Router

if TYPE_CHECKING:
    from starlette.requests import Request

from bt_hub.config import get_settings
from bt_hub.deps import (
    get_bluetooth_manager,
    get_bridge_service,
    get_bt_bridge_client,
    get_device_store,
    render_template,
)
from bt_hub.models.device import ScanResponse

logger = logging.getLogger(__name__)


async def get_adapter(request: Request) -> JSONResponse:
    """Return the current Bluetooth adapter state."""
    bt = get_bluetooth_manager()
    state = await bt.get_adapter_state()
    logger.debug("Adapter state: powered=%s discovering=%s", state.powered, state.discovering)
    return JSONResponse(dataclasses.asdict(state))


async def set_adapter_power(request: Request) -> object:
    """Toggle adapter power on or off."""
    bt = get_bluetooth_manager()

    # Try form data first, then JSON body
    power_value: bool = False
    content_type = request.headers.get("content-type", "")
    if "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
        form = await request.form()
        raw = form.get("powered")
        if raw is not None:
            power_value = str(raw).lower() in ("true", "1", "on")
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
    return JSONResponse(dataclasses.asdict(state))


async def start_scan(request: Request) -> object:
    """Start Bluetooth discovery scan."""
    bt = get_bluetooth_manager()
    store = get_device_store()

    try:
        duration = int(request.query_params.get("duration", 0)) or None
    except (ValueError, TypeError):
        duration = None

    if duration is None:
        settings = await store.get_settings()
        duration = int(settings.get("scan_duration_seconds", 10))

    logger.info("Starting scan for %d seconds", duration)
    await bt.start_discovery(duration_seconds=duration)

    if "hx-request" in request.headers:
        return render_template("partials/scan_progress.html", request, duration=duration)
    resp = ScanResponse(status="scanning", duration_seconds=duration)
    return JSONResponse(dataclasses.asdict(resp))


async def stop_scan(request: Request) -> object:
    """Stop Bluetooth discovery scan."""
    bt = get_bluetooth_manager()
    logger.info("Stopping scan")
    await bt.stop_discovery()

    if "hx-request" in request.headers:
        return render_template("partials/scan_stopped.html", request)
    return JSONResponse(dataclasses.asdict(ScanResponse(status="stopped")))


async def index_page(request: Request) -> object:
    """Serve the combined dashboard + devices page."""
    from bt_hub.api.devices import _build_runtime_state

    bt = get_bluetooth_manager()
    settings = get_settings()

    try:
        adapter = await bt.get_adapter_state()
    except Exception:
        adapter = None

    bridge_status = None
    service_status = None
    if settings.bridge_enabled:
        bridge_client = get_bt_bridge_client()
        if bridge_client:
            bridge_status = await bridge_client.get_status()
        with contextlib.suppress(Exception):
            bridge_service = get_bridge_service()
            service_status = await bridge_service.status()

    try:
        live_states = await bt.get_all_device_states()
    except Exception:
        live_states = {}

    devices = [_build_runtime_state(mac, live) for mac, live in live_states.items()]
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


router = Router(
    routes=[
        Route("/api/adapter", get_adapter, methods=["GET"]),
        Route("/api/adapter/power", set_adapter_power, methods=["POST"]),
        Route("/api/scan/start", start_scan, methods=["POST"]),
        Route("/api/scan/stop", stop_scan, methods=["POST"]),
        Route("/", index_page, methods=["GET"]),
    ]
)
