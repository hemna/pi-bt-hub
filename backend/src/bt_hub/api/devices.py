"""Device API endpoints."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import JSONResponse, Response
from fastapi.templating import Jinja2Templates  # noqa: TC002

from bt_hub.api import (
    BluetoothError,
    DeviceNotFoundError,
    InvalidMacAddressError,
)
from bt_hub.api.adapter import get_bluetooth_manager
from bt_hub.deps import get_device_store, get_templates, get_templates_optional
from bt_hub.models.device import (
    ConnectionState,
    DeviceActionResponse,
    DeviceListResponse,
    DeviceRuntimeState,
    DeviceType,
    DeviceUpdate,
    validate_mac_address,
)
from bt_hub.services.bluetooth import BlueZManager  # noqa: TC001
from bt_hub.services.device_store import DeviceStore  # noqa: TC001

logger = logging.getLogger(__name__)

router = APIRouter()


def _validate_mac(mac_address: str) -> str:
    """Validate MAC address, raising InvalidMacAddressError on failure."""
    try:
        return validate_mac_address(mac_address)
    except ValueError:
        raise InvalidMacAddressError(mac_address) from None


def _build_runtime_state(
    stored: dict[str, Any],
    live: dict[str, Any] | None = None,
) -> DeviceRuntimeState:
    """Merge a stored device record with live BlueZ state into DeviceRuntimeState."""
    paired = False
    connected = False
    trusted = False
    rssi: int | None = None
    connection_state = ConnectionState.DISCONNECTED

    if live:
        paired = live.get("paired", False)
        connected = live.get("connected", False)
        trusted = live.get("trusted", False)
        rssi = live.get("rssi")
        if connected:
            connection_state = ConnectionState.CONNECTED

        # Update device type from live data if we have it and stored is None
        if live.get("device_type") and not stored.get("device_type"):
            stored["device_type"] = live["device_type"]

        # Update name from live data if stored is None
        if live.get("name") and not stored.get("name"):
            stored["name"] = live["name"]

    # Parse device_type
    device_type = None
    if stored.get("device_type"):
        try:
            device_type = DeviceType(stored["device_type"])
        except ValueError:
            device_type = DeviceType.OTHER

    # Parse datetimes
    first_seen = stored.get("first_seen")
    if isinstance(first_seen, str):
        first_seen = datetime.fromisoformat(first_seen)
    last_seen = stored.get("last_seen")
    if isinstance(last_seen, str):
        last_seen = datetime.fromisoformat(last_seen)
    last_connected = stored.get("last_connected")
    if isinstance(last_connected, str):
        last_connected = datetime.fromisoformat(last_connected)

    return DeviceRuntimeState(
        mac_address=stored["mac_address"],
        name=stored.get("name"),
        alias=stored.get("alias"),
        device_type=device_type,
        first_seen=first_seen or datetime.now(UTC),
        last_seen=last_seen or datetime.now(UTC),
        last_connected=last_connected,
        is_favorite=bool(stored.get("is_favorite", False)),
        notes=stored.get("notes"),
        paired=paired,
        connected=connected,
        trusted=trusted,
        rssi=rssi,
        connection_state=connection_state,
    )


# --- JSON API endpoints ---


@router.get("/api/devices", response_model=DeviceListResponse)
async def list_devices(
    store: Annotated[DeviceStore, Depends(get_device_store)],
    bt: Annotated[BlueZManager, Depends(get_bluetooth_manager)],
    filter: str = Query(default="all", pattern="^(all|paired|connected|favorites)$"),
    sort: str = Query(default="last_seen", pattern="^(last_seen|name|last_connected)$"),
) -> DeviceListResponse:
    """List all devices, merging stored data with live BlueZ state."""
    # Get live states from BlueZ
    try:
        live_states = await bt.get_all_device_states()
    except BluetoothError:
        live_states = {}

    # Get stored devices
    store_filter = "favorites" if filter == "favorites" else "all"
    stored_devices = await store.get_all_devices(filter_type=store_filter, sort_by=sort)

    # Upsert any BlueZ-known devices not yet in the store
    stored_macs = {d["mac_address"] for d in stored_devices}
    for mac, live_data in live_states.items():
        if mac not in stored_macs:
            new_record = await store.upsert_device(
                mac,
                name=live_data.get("name"),
                device_type=live_data.get("device_type"),
            )
            stored_devices.append(new_record)

    # Build merged runtime states
    devices: list[DeviceRuntimeState] = []
    for stored in stored_devices:
        mac = str(stored["mac_address"])
        live = live_states.get(mac)
        runtime = _build_runtime_state(stored, live)

        # Apply filter for paired/connected
        if filter == "paired" and not runtime.paired:
            continue
        if filter == "connected" and not runtime.connected:
            continue

        devices.append(runtime)

    return DeviceListResponse(devices=devices, count=len(devices))


@router.get("/api/devices/{mac_address}", response_model=DeviceRuntimeState)
async def get_device(
    mac_address: str,
    store: Annotated[DeviceStore, Depends(get_device_store)],
    bt: Annotated[BlueZManager, Depends(get_bluetooth_manager)],
) -> DeviceRuntimeState:
    """Get a single device by MAC address."""
    mac = _validate_mac(mac_address)
    stored = await store.get_device(mac)
    if not stored:
        raise DeviceNotFoundError(mac)

    try:
        live = await bt.get_device_state(mac)
    except DeviceNotFoundError:
        live = None
    except BluetoothError:
        live = None

    return _build_runtime_state(stored, live)


@router.patch("/api/devices/{mac_address}", response_model=DeviceRuntimeState)
async def update_device(
    mac_address: str,
    body: DeviceUpdate,
    store: Annotated[DeviceStore, Depends(get_device_store)],
    bt: Annotated[BlueZManager, Depends(get_bluetooth_manager)],
) -> DeviceRuntimeState:
    """Update user-editable fields on a device (alias, is_favorite, notes)."""
    mac = _validate_mac(mac_address)
    logger.info("Updating device %s: %s", mac, body.model_dump(exclude_none=True))

    update_fields: dict[str, Any] = {}
    if body.alias is not None:
        update_fields["alias"] = body.alias
    if body.is_favorite is not None:
        update_fields["is_favorite"] = body.is_favorite
    if body.notes is not None:
        update_fields["notes"] = body.notes

    updated = await store.update_device(mac, **update_fields)
    if updated is None:
        raise DeviceNotFoundError(mac)

    try:
        live = await bt.get_device_state(mac)
    except (DeviceNotFoundError, BluetoothError):
        live = None

    return _build_runtime_state(updated, live)


@router.post("/api/devices/{mac_address}/favorite")
async def toggle_favorite(
    mac_address: str,
    request: Request,
    store: Annotated[DeviceStore, Depends(get_device_store)],
    bt: Annotated[BlueZManager, Depends(get_bluetooth_manager)],
    templates: Annotated[Jinja2Templates, Depends(get_templates)],
    is_favorite: bool = Form(...),
) -> Response:
    """Toggle favorite status on a device (HTMX endpoint, returns HTML partial)."""
    mac = _validate_mac(mac_address)
    logger.info("Setting favorite=%s for device %s", is_favorite, mac)

    updated = await store.update_device(mac, is_favorite=is_favorite)
    if updated is None:
        raise DeviceNotFoundError(mac)

    try:
        live = await bt.get_device_state(mac)
    except (DeviceNotFoundError, BluetoothError):
        live = None

    device = _build_runtime_state(updated, live)

    # Determine which partial to return based on the HTMX target
    target = request.headers.get("hx-target", "")
    if target.startswith("device-row-"):
        template_name = "partials/device_row.html"
    elif target.startswith("detail-favorite-"):
        template_name = "partials/favorite_button_detail.html"
    else:
        template_name = "partials/device_card.html"

    return templates.TemplateResponse(
        template_name,
        {"request": request, "device": device},
    )


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
        # Detail page actions target body — tell HTMX to do a full page reload
        mac = device.mac_address
        return Response(
            status_code=200,
            headers={"HX-Redirect": f"/devices/{mac}"},
        )
    else:
        template_name = "partials/device_card.html"

    return templates.TemplateResponse(
        template_name,
        {"request": request, "device": device},
    )


@router.delete("/api/devices/{mac_address}")
async def delete_device(
    mac_address: str,
    store: Annotated[DeviceStore, Depends(get_device_store)],
) -> dict[str, str]:
    """Delete a device from the store."""
    mac = _validate_mac(mac_address)
    logger.info("Deleting device %s from store", mac)
    deleted = await store.delete_device(mac)
    if not deleted:
        raise DeviceNotFoundError(mac)
    return {"status": "deleted", "mac_address": mac}


@router.post("/api/devices/{mac_address}/pair", response_model=None)
async def pair_device(
    mac_address: str,
    request: Request,
    bt: Annotated[BlueZManager, Depends(get_bluetooth_manager)],
    store: Annotated[DeviceStore, Depends(get_device_store)],
    templates: Annotated[Jinja2Templates | None, Depends(get_templates_optional)],
) -> object:
    """Pair with a device."""
    mac = _validate_mac(mac_address)
    logger.info("Pairing with device %s", mac)
    await bt.pair_device(mac)
    await store.upsert_device(mac)

    stored = await store.get_device(mac)
    if stored is None:
        stored = await store.upsert_device(mac)

    try:
        live = await bt.get_device_state(mac)
    except (DeviceNotFoundError, BluetoothError):
        live = None

    device = _build_runtime_state(stored, live)
    htmx_resp = _htmx_device_response(request, templates, device)
    if htmx_resp is not None:
        return htmx_resp

    return JSONResponse(DeviceActionResponse(mac_address=mac, status="paired").model_dump())


@router.post("/api/devices/{mac_address}/connect", response_model=None)
async def connect_device(
    mac_address: str,
    request: Request,
    bt: Annotated[BlueZManager, Depends(get_bluetooth_manager)],
    store: Annotated[DeviceStore, Depends(get_device_store)],
    templates: Annotated[Jinja2Templates | None, Depends(get_templates_optional)],
) -> object:
    """Connect to a paired device."""
    mac = _validate_mac(mac_address)
    logger.info("Connecting to device %s", mac)
    await bt.connect_device(mac)
    now = datetime.now(UTC).isoformat()
    await store.update_device(mac, last_connected=now)

    stored = await store.get_device(mac)
    if stored is None:
        raise DeviceNotFoundError(mac)

    try:
        live = await bt.get_device_state(mac)
    except (DeviceNotFoundError, BluetoothError):
        live = None

    device = _build_runtime_state(stored, live)
    htmx_resp = _htmx_device_response(request, templates, device)
    if htmx_resp is not None:
        return htmx_resp

    return JSONResponse(DeviceActionResponse(mac_address=mac, status="connected").model_dump())


@router.post("/api/devices/{mac_address}/disconnect", response_model=None)
async def disconnect_device(
    mac_address: str,
    request: Request,
    bt: Annotated[BlueZManager, Depends(get_bluetooth_manager)],
    store: Annotated[DeviceStore, Depends(get_device_store)],
    templates: Annotated[Jinja2Templates | None, Depends(get_templates_optional)],
) -> object:
    """Disconnect from a device."""
    mac = _validate_mac(mac_address)
    logger.info("Disconnecting device %s", mac)
    await bt.disconnect_device(mac)

    stored = await store.get_device(mac)
    if stored is None:
        raise DeviceNotFoundError(mac)

    try:
        live = await bt.get_device_state(mac)
    except (DeviceNotFoundError, BluetoothError):
        live = None

    device = _build_runtime_state(stored, live)
    htmx_resp = _htmx_device_response(request, templates, device)
    if htmx_resp is not None:
        return htmx_resp

    return JSONResponse(DeviceActionResponse(mac_address=mac, status="disconnected").model_dump())


@router.post("/api/devices/{mac_address}/trust", response_model=None)
async def trust_device(
    mac_address: str,
    request: Request,
    bt: Annotated[BlueZManager, Depends(get_bluetooth_manager)],
    store: Annotated[DeviceStore, Depends(get_device_store)],
    templates: Annotated[Jinja2Templates | None, Depends(get_templates_optional)],
) -> object:
    """Trust a device."""
    mac = _validate_mac(mac_address)
    logger.info("Trusting device %s", mac)
    await bt.trust_device(mac)

    stored = await store.get_device(mac)
    if not stored:
        stored = await store.upsert_device(mac)

    try:
        live = await bt.get_device_state(mac)
    except (DeviceNotFoundError, BluetoothError):
        live = None

    device = _build_runtime_state(stored, live)
    htmx_resp = _htmx_device_response(request, templates, device)
    if htmx_resp is not None:
        return htmx_resp

    return JSONResponse(device.model_dump(mode="json"))


@router.post("/api/devices/{mac_address}/untrust", response_model=None)
async def untrust_device(
    mac_address: str,
    request: Request,
    bt: Annotated[BlueZManager, Depends(get_bluetooth_manager)],
    store: Annotated[DeviceStore, Depends(get_device_store)],
    templates: Annotated[Jinja2Templates | None, Depends(get_templates_optional)],
) -> object:
    """Untrust a device."""
    mac = _validate_mac(mac_address)
    logger.info("Untrusting device %s", mac)
    await bt.untrust_device(mac)

    stored = await store.get_device(mac)
    if not stored:
        stored = await store.upsert_device(mac)

    try:
        live = await bt.get_device_state(mac)
    except (DeviceNotFoundError, BluetoothError):
        live = None

    device = _build_runtime_state(stored, live)
    htmx_resp = _htmx_device_response(request, templates, device)
    if htmx_resp is not None:
        return htmx_resp

    return JSONResponse(device.model_dump(mode="json"))


@router.post("/api/devices/{mac_address}/remove", response_model=None)
async def remove_device(
    mac_address: str,
    request: Request,
    bt: Annotated[BlueZManager, Depends(get_bluetooth_manager)],
    store: Annotated[DeviceStore, Depends(get_device_store)],
    templates: Annotated[Jinja2Templates | None, Depends(get_templates_optional)],
) -> object:
    """Remove a device from BlueZ (keep in store for history)."""
    mac = _validate_mac(mac_address)
    logger.info("Removing device %s from BlueZ", mac)
    await bt.remove_device(mac)

    if "hx-request" in request.headers:
        stored = await store.get_device(mac)
        if stored:
            device = _build_runtime_state(stored, None)
            htmx_resp = _htmx_device_response(request, templates, device)
            if htmx_resp is not None:
                return htmx_resp

    return {"status": "removed", "mac_address": mac}


# --- HTML page endpoints ---


@router.get("/devices")
async def devices_page(
    request: Request,
    templates: Annotated[Jinja2Templates, Depends(get_templates)],
    store: Annotated[DeviceStore, Depends(get_device_store)],
    bt: Annotated[BlueZManager, Depends(get_bluetooth_manager)],
    filter: str = Query(default="all", pattern="^(all|paired|connected|favorites)$"),
    sort: str = Query(default="last_seen", pattern="^(last_seen|name|last_connected)$"),
) -> object:
    """Serve the devices list page."""
    # Get live states from BlueZ
    try:
        live_states = await bt.get_all_device_states()
    except BluetoothError:
        live_states = {}

    # Get stored devices
    store_filter = "favorites" if filter == "favorites" else "all"
    stored_devices = await store.get_all_devices(filter_type=store_filter, sort_by=sort)

    # Upsert any BlueZ-known devices not yet in the store
    stored_macs = {d["mac_address"] for d in stored_devices}
    for mac, live_data in live_states.items():
        if mac not in stored_macs:
            new_record = await store.upsert_device(
                mac,
                name=live_data.get("name"),
                device_type=live_data.get("device_type"),
            )
            stored_devices.append(new_record)

    # Build merged runtime states and count stats
    devices: list[DeviceRuntimeState] = []
    paired_count = 0
    connected_count = 0
    favorite_count = 0

    for stored in stored_devices:
        mac = str(stored["mac_address"])
        live = live_states.get(mac)
        runtime = _build_runtime_state(stored, live)

        # Count stats (from all devices, before filtering)
        if runtime.paired:
            paired_count += 1
        if runtime.connected:
            connected_count += 1
        if runtime.is_favorite:
            favorite_count += 1

        # Apply filter for paired/connected
        if filter == "paired" and not runtime.paired:
            continue
        if filter == "connected" and not runtime.connected:
            continue

        devices.append(runtime)

    return templates.TemplateResponse(
        "devices.html",
        {
            "request": request,
            "devices": devices,
            "device_count": len(stored_devices),
            "paired_count": paired_count,
            "connected_count": connected_count,
            "favorite_count": favorite_count,
            "current_filter": filter,
            "current_sort": sort,
            "is_scanning": bt.is_scanning,
        },
    )


@router.get("/devices/{mac_address}")
async def device_detail_page(
    mac_address: str,
    request: Request,
    templates: Annotated[Jinja2Templates, Depends(get_templates)],
    store: Annotated[DeviceStore, Depends(get_device_store)],
    bt: Annotated[BlueZManager, Depends(get_bluetooth_manager)],
) -> object:
    """Serve the device detail page."""
    mac = _validate_mac(mac_address)
    stored = await store.get_device(mac)
    if not stored:
        raise DeviceNotFoundError(mac)

    try:
        live = await bt.get_device_state(mac)
    except (DeviceNotFoundError, BluetoothError):
        live = None

    device = _build_runtime_state(stored, live)

    return templates.TemplateResponse(
        "device.html",
        {
            "request": request,
            "device": device,
        },
    )
