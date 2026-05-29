"""Device API endpoints.

Shows only live BlueZ discovery results — no persistence or history.
"""

from __future__ import annotations

import dataclasses
import logging

from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response
from starlette.routing import Route, Router

from bt_hub.api import (
    BluetoothError,
    DeviceNotFoundError,
    InvalidMacAddressError,
)
from bt_hub.deps import (
    get_bluetooth_manager,
    get_templates_optional,
    render_template,
)
from bt_hub.models.device import (
    ConnectionState,
    DeviceActionResponse,
    DeviceRuntimeState,
    DeviceType,
    validate_mac_address,
)

logger = logging.getLogger(__name__)


def _validate_mac(mac_address: str) -> str:
    """Validate MAC address, raising InvalidMacAddressError on failure."""
    try:
        return validate_mac_address(mac_address)
    except ValueError:
        raise InvalidMacAddressError(mac_address) from None


def _build_runtime_state(mac: str, live: dict) -> DeviceRuntimeState:
    """Build a DeviceRuntimeState from live BlueZ properties."""
    connected = live.get("connected", False)
    device_type = None
    if live.get("device_type"):
        try:
            device_type = DeviceType(live["device_type"])
        except ValueError:
            device_type = DeviceType.OTHER

    return DeviceRuntimeState(
        mac_address=mac,
        name=live.get("name"),
        device_type=device_type,
        paired=live.get("paired", False),
        connected=connected,
        trusted=live.get("trusted", False),
        rssi=live.get("rssi"),
        connection_state=ConnectionState.CONNECTED if connected else ConnectionState.DISCONNECTED,
    )


def _htmx_device_response(
    request: Request,
    device: DeviceRuntimeState,
) -> Response | None:
    """Return an HTMX HTML partial if the request has HX-Request header."""
    templates = get_templates_optional()
    if "hx-request" not in request.headers or templates is None:
        return None

    target = request.headers.get("hx-target", "")
    if target.startswith("device-row-"):
        return render_template("partials/device_row.html", request, device=device)
    if target == "body":
        return Response(
            status_code=200,
            headers={"HX-Redirect": f"/devices/{device.mac_address}"},
        )
    return render_template("partials/device_card.html", request, device=device)


async def list_devices(request: Request) -> JSONResponse:
    """List all devices currently known to BlueZ."""
    bt = get_bluetooth_manager()
    try:
        live_states = await bt.get_all_device_states()
    except BluetoothError:
        live_states = {}

    devices = [_build_runtime_state(mac, live) for mac, live in live_states.items()]
    devices.sort(key=lambda d: (not d.connected, not d.paired, (d.name or d.mac_address).lower()))
    return JSONResponse({"devices": [dataclasses.asdict(d) for d in devices], "count": len(devices)})


async def get_device(request: Request) -> JSONResponse:
    """Get a single device by MAC address."""
    bt = get_bluetooth_manager()
    mac = _validate_mac(request.path_params["mac_address"])

    try:
        live = await bt.get_device_state(mac)
    except DeviceNotFoundError:
        raise
    except BluetoothError:
        raise DeviceNotFoundError(mac) from None

    if live is None:
        raise DeviceNotFoundError(mac)

    return JSONResponse(dataclasses.asdict(_build_runtime_state(mac, live)))


async def pair_device(request: Request) -> object:
    """Pair with a device."""
    bt = get_bluetooth_manager()
    mac = _validate_mac(request.path_params["mac_address"])
    logger.info("Pairing with device %s", mac)
    await bt.pair_device(mac)

    try:
        live = await bt.get_device_state(mac)
    except (DeviceNotFoundError, BluetoothError):
        live = {}

    device = _build_runtime_state(mac, live or {})
    htmx_resp = _htmx_device_response(request, device)
    if htmx_resp is not None:
        return htmx_resp
    return JSONResponse(dataclasses.asdict(DeviceActionResponse(mac_address=mac, status="paired")))


async def connect_device(request: Request) -> object:
    """Connect to a paired device."""
    bt = get_bluetooth_manager()
    mac = _validate_mac(request.path_params["mac_address"])
    logger.info("Connecting to device %s", mac)
    await bt.connect_device(mac)

    try:
        live = await bt.get_device_state(mac)
    except (DeviceNotFoundError, BluetoothError):
        live = {}

    device = _build_runtime_state(mac, live or {})
    htmx_resp = _htmx_device_response(request, device)
    if htmx_resp is not None:
        return htmx_resp
    return JSONResponse(dataclasses.asdict(DeviceActionResponse(mac_address=mac, status="connected")))


async def disconnect_device(request: Request) -> object:
    """Disconnect from a device."""
    bt = get_bluetooth_manager()
    mac = _validate_mac(request.path_params["mac_address"])
    logger.info("Disconnecting device %s", mac)
    await bt.disconnect_device(mac)

    try:
        live = await bt.get_device_state(mac)
    except (DeviceNotFoundError, BluetoothError):
        live = {}

    device = _build_runtime_state(mac, live or {})
    htmx_resp = _htmx_device_response(request, device)
    if htmx_resp is not None:
        return htmx_resp
    return JSONResponse(dataclasses.asdict(DeviceActionResponse(mac_address=mac, status="disconnected")))


async def trust_device(request: Request) -> object:
    """Trust a device."""
    bt = get_bluetooth_manager()
    mac = _validate_mac(request.path_params["mac_address"])
    logger.info("Trusting device %s", mac)
    await bt.trust_device(mac)

    try:
        live = await bt.get_device_state(mac)
    except (DeviceNotFoundError, BluetoothError):
        live = {}

    device = _build_runtime_state(mac, live or {})
    htmx_resp = _htmx_device_response(request, device)
    if htmx_resp is not None:
        return htmx_resp
    return JSONResponse(dataclasses.asdict(device))


async def untrust_device(request: Request) -> object:
    """Untrust a device."""
    bt = get_bluetooth_manager()
    mac = _validate_mac(request.path_params["mac_address"])
    logger.info("Untrusting device %s", mac)
    await bt.untrust_device(mac)

    try:
        live = await bt.get_device_state(mac)
    except (DeviceNotFoundError, BluetoothError):
        live = {}

    device = _build_runtime_state(mac, live or {})
    htmx_resp = _htmx_device_response(request, device)
    if htmx_resp is not None:
        return htmx_resp
    return JSONResponse(dataclasses.asdict(device))


async def remove_device(request: Request) -> object:
    """Remove a device from BlueZ."""
    bt = get_bluetooth_manager()
    mac = _validate_mac(request.path_params["mac_address"])
    logger.info("Removing device %s from BlueZ", mac)
    await bt.remove_device(mac)

    if "hx-request" in request.headers:
        return Response(content="", status_code=200, media_type="text/html")
    return JSONResponse({"status": "removed", "mac_address": mac})


async def devices_page(request: Request) -> RedirectResponse:
    """Redirect /devices to / (combined page)."""
    return RedirectResponse(url="/", status_code=302)


async def device_detail_page(request: Request) -> object:
    """Serve the device detail page."""
    bt = get_bluetooth_manager()
    mac = _validate_mac(request.path_params["mac_address"])

    try:
        live = await bt.get_device_state(mac)
    except (DeviceNotFoundError, BluetoothError):
        live = None

    if live is None:
        raise DeviceNotFoundError(mac)

    return render_template("device.html", request, device=_build_runtime_state(mac, live))


router = Router(
    routes=[
        Route("/api/devices", list_devices, methods=["GET"]),
        Route("/api/devices/{mac_address}", get_device, methods=["GET"]),
        Route("/api/devices/{mac_address}/pair", pair_device, methods=["POST"]),
        Route("/api/devices/{mac_address}/connect", connect_device, methods=["POST"]),
        Route("/api/devices/{mac_address}/disconnect", disconnect_device, methods=["POST"]),
        Route("/api/devices/{mac_address}/trust", trust_device, methods=["POST"]),
        Route("/api/devices/{mac_address}/untrust", untrust_device, methods=["POST"]),
        Route("/api/devices/{mac_address}/remove", remove_device, methods=["POST"]),
        Route("/devices", devices_page, methods=["GET"]),
        Route("/devices/{mac_address}", device_detail_page, methods=["GET"]),
    ]
)
