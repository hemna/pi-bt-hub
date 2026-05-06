"""Device API endpoints.

Shows only live BlueZ discovery results — no persistence or history.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from fastapi.templating import Jinja2Templates  # noqa: TC002

from bt_hub.api import (
    BluetoothError,
    DeviceNotFoundError,
    InvalidMacAddressError,
)
from bt_hub.deps import (
    get_bluetooth_manager,
    get_templates,
    get_templates_optional,
    render_template,
)
from bt_hub.models.device import (
    ConnectionState,
    DeviceActionResponse,
    DeviceListResponse,
    DeviceRuntimeState,
    DeviceType,
    validate_mac_address,
)
from bt_hub.services.bluetooth import BlueZManager  # noqa: TC001

if TYPE_CHECKING:
    from bt_hub.lifecycle import ServiceContainer

logger = logging.getLogger(__name__)

router = APIRouter()


def _validate_mac(mac_address: str) -> str:
    """Validate MAC address, raising InvalidMacAddressError on failure."""
    try:
        return validate_mac_address(mac_address)
    except ValueError:
        raise InvalidMacAddressError(mac_address) from None


def _build_runtime_state(mac: str, live: dict) -> DeviceRuntimeState:
    """Build a DeviceRuntimeState from live BlueZ properties."""
    paired = live.get("paired", False)
    connected = live.get("connected", False)
    trusted = live.get("trusted", False)
    rssi = live.get("rssi")
    connection_state = ConnectionState.CONNECTED if connected else ConnectionState.DISCONNECTED

    # Parse device type
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
        paired=paired,
        connected=connected,
        trusted=trusted,
        rssi=rssi,
        connection_state=connection_state,
    )


# --- JSON API endpoints ---


@router.get("/api/devices", response_model=DeviceListResponse)
async def list_devices(
    bt: Annotated[BlueZManager, Depends(get_bluetooth_manager)],
) -> DeviceListResponse:
    """List all devices currently known to BlueZ."""
    try:
        live_states = await bt.get_all_device_states()
    except BluetoothError:
        live_states = {}

    devices: list[DeviceRuntimeState] = []
    for mac, live in live_states.items():
        devices.append(_build_runtime_state(mac, live))

    # Sort by name (with fallback to MAC), then connected first
    devices.sort(key=lambda d: (not d.connected, not d.paired, (d.name or d.mac_address).lower()))

    return DeviceListResponse(devices=devices, count=len(devices))


@router.get("/api/devices/{mac_address}", response_model=DeviceRuntimeState)
async def get_device(
    mac_address: str,
    bt: Annotated[BlueZManager, Depends(get_bluetooth_manager)],
) -> DeviceRuntimeState:
    """Get a single device by MAC address."""
    mac = _validate_mac(mac_address)

    try:
        live = await bt.get_device_state(mac)
    except DeviceNotFoundError:
        raise
    except BluetoothError:
        raise DeviceNotFoundError(mac) from None

    if live is None:
        raise DeviceNotFoundError(mac)

    return _build_runtime_state(mac, live)


def _htmx_device_response(
    request: Request,
    templates: Jinja2Templates | None,
    device: DeviceRuntimeState,
) -> Response | None:
    """If the request came from HTMX, return the appropriate HTML partial.

    Returns None if this is a regular API call (no HX-Request header)
    or if templates are not available.
    """
    if "hx-request" not in request.headers or templates is None:
        return None

    target = request.headers.get("hx-target", "")
    if target.startswith("device-row-"):
        template_name = "partials/device_row.html"
    elif target == "body":
        mac = device.mac_address
        return Response(
            status_code=200,
            headers={"HX-Redirect": f"/devices/{mac}"},
        )
    else:
        template_name = "partials/device_card.html"

    return render_template(template_name, request, device=device)


@router.post("/api/devices/{mac_address}/pair", response_model=None)
async def pair_device(
    mac_address: str,
    request: Request,
    bt: Annotated[BlueZManager, Depends(get_bluetooth_manager)],
    templates: Annotated[Jinja2Templates | None, Depends(get_templates_optional)],
) -> object:
    """Pair with a device."""
    mac = _validate_mac(mac_address)
    logger.info("Pairing with device %s", mac)
    await bt.pair_device(mac)

    try:
        live = await bt.get_device_state(mac)
    except (DeviceNotFoundError, BluetoothError):
        live = {}

    device = _build_runtime_state(mac, live or {})
    htmx_resp = _htmx_device_response(request, templates, device)
    if htmx_resp is not None:
        return htmx_resp

    return JSONResponse(DeviceActionResponse(mac_address=mac, status="paired").model_dump())


@router.post("/api/devices/{mac_address}/connect", response_model=None)
async def connect_device(
    mac_address: str,
    request: Request,
    bt: Annotated[BlueZManager, Depends(get_bluetooth_manager)],
    templates: Annotated[Jinja2Templates | None, Depends(get_templates_optional)],
) -> object:
    """Connect to a paired device."""
    mac = _validate_mac(mac_address)
    logger.info("Connecting to device %s", mac)
    await bt.connect_device(mac)

    try:
        live = await bt.get_device_state(mac)
    except (DeviceNotFoundError, BluetoothError):
        live = {}

    device = _build_runtime_state(mac, live or {})
    htmx_resp = _htmx_device_response(request, templates, device)
    if htmx_resp is not None:
        return htmx_resp

    return JSONResponse(DeviceActionResponse(mac_address=mac, status="connected").model_dump())


@router.post("/api/devices/{mac_address}/disconnect", response_model=None)
async def disconnect_device(
    mac_address: str,
    request: Request,
    bt: Annotated[BlueZManager, Depends(get_bluetooth_manager)],
    templates: Annotated[Jinja2Templates | None, Depends(get_templates_optional)],
) -> object:
    """Disconnect from a device."""
    mac = _validate_mac(mac_address)
    logger.info("Disconnecting device %s", mac)
    await bt.disconnect_device(mac)

    try:
        live = await bt.get_device_state(mac)
    except (DeviceNotFoundError, BluetoothError):
        live = {}

    device = _build_runtime_state(mac, live or {})
    htmx_resp = _htmx_device_response(request, templates, device)
    if htmx_resp is not None:
        return htmx_resp

    return JSONResponse(DeviceActionResponse(mac_address=mac, status="disconnected").model_dump())


@router.post("/api/devices/{mac_address}/trust", response_model=None)
async def trust_device(
    mac_address: str,
    request: Request,
    bt: Annotated[BlueZManager, Depends(get_bluetooth_manager)],
    templates: Annotated[Jinja2Templates | None, Depends(get_templates_optional)],
) -> object:
    """Trust a device."""
    mac = _validate_mac(mac_address)
    logger.info("Trusting device %s", mac)
    await bt.trust_device(mac)

    try:
        live = await bt.get_device_state(mac)
    except (DeviceNotFoundError, BluetoothError):
        live = {}

    device = _build_runtime_state(mac, live or {})
    htmx_resp = _htmx_device_response(request, templates, device)
    if htmx_resp is not None:
        return htmx_resp

    return JSONResponse(device.model_dump(mode="json"))


@router.post("/api/devices/{mac_address}/untrust", response_model=None)
async def untrust_device(
    mac_address: str,
    request: Request,
    bt: Annotated[BlueZManager, Depends(get_bluetooth_manager)],
    templates: Annotated[Jinja2Templates | None, Depends(get_templates_optional)],
) -> object:
    """Untrust a device."""
    mac = _validate_mac(mac_address)
    logger.info("Untrusting device %s", mac)
    await bt.untrust_device(mac)

    try:
        live = await bt.get_device_state(mac)
    except (DeviceNotFoundError, BluetoothError):
        live = {}

    device = _build_runtime_state(mac, live or {})
    htmx_resp = _htmx_device_response(request, templates, device)
    if htmx_resp is not None:
        return htmx_resp

    return JSONResponse(device.model_dump(mode="json"))


@router.post("/api/devices/{mac_address}/remove", response_model=None)
async def remove_device(
    mac_address: str,
    request: Request,
    bt: Annotated[BlueZManager, Depends(get_bluetooth_manager)],
    templates: Annotated[Jinja2Templates | None, Depends(get_templates_optional)],
) -> object:
    """Remove a device from BlueZ."""
    mac = _validate_mac(mac_address)
    logger.info("Removing device %s from BlueZ", mac)
    await bt.remove_device(mac)

    if "hx-request" in request.headers:
        # Device is gone from BlueZ — return empty to remove the card
        return Response(content="", status_code=200, media_type="text/html")

    return {"status": "removed", "mac_address": mac}


# --- HTML page endpoints ---


@router.get("/devices")
async def devices_page() -> Response:
    """Redirect /devices to / (combined page)."""
    from fastapi.responses import RedirectResponse

    return RedirectResponse(url="/", status_code=302)


@router.get("/devices/{mac_address}")
async def device_detail_page(
    mac_address: str,
    request: Request,
    templates: Annotated[Jinja2Templates, Depends(get_templates)],
    bt: Annotated[BlueZManager, Depends(get_bluetooth_manager)],
) -> object:
    """Serve the device detail page."""
    mac = _validate_mac(mac_address)

    try:
        live = await bt.get_device_state(mac)
    except (DeviceNotFoundError, BluetoothError):
        live = None

    if live is None:
        raise DeviceNotFoundError(mac)

    device = _build_runtime_state(mac, live)
    return render_template("device.html", request, device=device)


# --- Factory functions for library usage ---


def create_api_router(container: ServiceContainer) -> APIRouter:
    """Create an APIRouter with device API endpoints using the ServiceContainer."""
    from bt_hub.api import AdapterUnavailableError

    api = APIRouter()

    def _get_bt() -> BlueZManager:
        assert container.services is not None
        bt = container.services.bluez_mgr
        if bt is None:
            raise AdapterUnavailableError("BlueZManager not initialized")
        return bt

    @api.get("/api/devices", response_model=DeviceListResponse)
    async def list_devices_factory() -> DeviceListResponse:
        bt = _get_bt()
        try:
            live_states = await bt.get_all_device_states()
        except BluetoothError:
            live_states = {}
        devices: list[DeviceRuntimeState] = []
        for mac, live in live_states.items():
            devices.append(_build_runtime_state(mac, live))
        devices.sort(
            key=lambda d: (not d.connected, not d.paired, (d.name or d.mac_address).lower())
        )
        return DeviceListResponse(devices=devices, count=len(devices))

    @api.get("/api/devices/{mac_address}", response_model=DeviceRuntimeState)
    async def get_device_factory(mac_address: str) -> DeviceRuntimeState:
        bt = _get_bt()
        mac = _validate_mac(mac_address)
        try:
            live = await bt.get_device_state(mac)
        except DeviceNotFoundError:
            raise
        except BluetoothError:
            raise DeviceNotFoundError(mac) from None
        if live is None:
            raise DeviceNotFoundError(mac)
        return _build_runtime_state(mac, live)

    @api.post("/api/devices/{mac_address}/pair", response_model=None)
    async def pair_device_factory(mac_address: str, request: Request) -> object:
        bt = _get_bt()
        mac = _validate_mac(mac_address)
        await bt.pair_device(mac)
        try:
            live = await bt.get_device_state(mac)
        except (DeviceNotFoundError, BluetoothError):
            live = {}
        device = _build_runtime_state(mac, live or {})
        htmx_resp = _htmx_device_response(request, get_templates_optional(), device)
        if htmx_resp is not None:
            return htmx_resp
        return JSONResponse(DeviceActionResponse(mac_address=mac, status="paired").model_dump())

    @api.post("/api/devices/{mac_address}/connect", response_model=None)
    async def connect_device_factory(mac_address: str, request: Request) -> object:
        bt = _get_bt()
        mac = _validate_mac(mac_address)
        await bt.connect_device(mac)
        try:
            live = await bt.get_device_state(mac)
        except (DeviceNotFoundError, BluetoothError):
            live = {}
        device = _build_runtime_state(mac, live or {})
        htmx_resp = _htmx_device_response(request, get_templates_optional(), device)
        if htmx_resp is not None:
            return htmx_resp
        return JSONResponse(DeviceActionResponse(mac_address=mac, status="connected").model_dump())

    @api.post("/api/devices/{mac_address}/disconnect", response_model=None)
    async def disconnect_device_factory(mac_address: str, request: Request) -> object:
        bt = _get_bt()
        mac = _validate_mac(mac_address)
        await bt.disconnect_device(mac)
        try:
            live = await bt.get_device_state(mac)
        except (DeviceNotFoundError, BluetoothError):
            live = {}
        device = _build_runtime_state(mac, live or {})
        htmx_resp = _htmx_device_response(request, get_templates_optional(), device)
        if htmx_resp is not None:
            return htmx_resp
        return JSONResponse(
            DeviceActionResponse(mac_address=mac, status="disconnected").model_dump()
        )

    @api.post("/api/devices/{mac_address}/trust", response_model=None)
    async def trust_device_factory(mac_address: str, request: Request) -> object:
        bt = _get_bt()
        mac = _validate_mac(mac_address)
        await bt.trust_device(mac)
        try:
            live = await bt.get_device_state(mac)
        except (DeviceNotFoundError, BluetoothError):
            live = {}
        device = _build_runtime_state(mac, live or {})
        htmx_resp = _htmx_device_response(request, get_templates_optional(), device)
        if htmx_resp is not None:
            return htmx_resp
        return JSONResponse(device.model_dump(mode="json"))

    @api.post("/api/devices/{mac_address}/untrust", response_model=None)
    async def untrust_device_factory(mac_address: str, request: Request) -> object:
        bt = _get_bt()
        mac = _validate_mac(mac_address)
        await bt.untrust_device(mac)
        try:
            live = await bt.get_device_state(mac)
        except (DeviceNotFoundError, BluetoothError):
            live = {}
        device = _build_runtime_state(mac, live or {})
        htmx_resp = _htmx_device_response(request, get_templates_optional(), device)
        if htmx_resp is not None:
            return htmx_resp
        return JSONResponse(device.model_dump(mode="json"))

    @api.post("/api/devices/{mac_address}/remove", response_model=None)
    async def remove_device_factory(mac_address: str, request: Request) -> object:
        bt = _get_bt()
        mac = _validate_mac(mac_address)
        await bt.remove_device(mac)
        if "hx-request" in request.headers:
            return Response(content="", status_code=200, media_type="text/html")
        return {"status": "removed", "mac_address": mac}

    return api


def create_page_router(
    container: ServiceContainer,
    templates: Jinja2Templates,
    active_page_prefix: str = "bluetooth",
) -> APIRouter:
    """Create an APIRouter with device page endpoints using the ServiceContainer."""
    pages = APIRouter()

    def _get_bt() -> BlueZManager | None:
        assert container.services is not None
        return container.services.bluez_mgr

    @pages.get("/devices")
    async def devices_page_factory() -> Response:
        from fastapi.responses import RedirectResponse

        return RedirectResponse(url="/", status_code=302)

    @pages.get("/devices/{mac_address}")
    async def device_detail_page_factory(mac_address: str, request: Request) -> object:
        bt = _get_bt()
        mac = _validate_mac(mac_address)
        try:
            live = await bt.get_device_state(mac) if bt else None
        except (DeviceNotFoundError, BluetoothError):
            live = None
        if live is None:
            raise DeviceNotFoundError(mac)
        device = _build_runtime_state(mac, live)
        return render_template(
            "device.html", request, device=device, active_page=active_page_prefix
        )

    return pages
