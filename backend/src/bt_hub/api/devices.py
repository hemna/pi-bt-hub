"""Device API endpoints."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import JSONResponse, Response
from fastapi.templating import Jinja2Templates  # noqa: TC002

from bt_hub.api import (
    BluetoothError,
    DeviceNotFoundError,
    InvalidMacAddressError,
)
from bt_hub.deps import (
    get_bluetooth_manager,
    get_device_store,
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
    DeviceUpdate,
    validate_mac_address,
)
from bt_hub.services.bluetooth import BlueZManager  # noqa: TC001
from bt_hub.services.device_store import DeviceStore  # noqa: TC001

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
        is_ignored=bool(stored.get("is_ignored", False)),
        notes=stored.get("notes"),
        paired=paired,
        connected=connected,
        trusted=trusted,
        rssi=rssi,
        connection_state=connection_state,
        # Device is "in range" only if we have RSSI (actively being seen)
        # or if it's currently connected
        in_range=rssi is not None or connected,
    )


# --- JSON API endpoints ---


@router.get("/api/devices", response_model=DeviceListResponse)
async def list_devices(
    store: Annotated[DeviceStore, Depends(get_device_store)],
    bt: Annotated[BlueZManager, Depends(get_bluetooth_manager)],
    filter: str = Query(default="all", pattern="^(all|paired|connected|favorites|ignored)$"),
    sort: str = Query(default="last_seen", pattern="^(last_seen|name|last_connected)$"),
) -> DeviceListResponse:
    """List all devices, merging stored data with live BlueZ state."""
    # Get live states from BlueZ
    try:
        live_states = await bt.get_all_device_states()
    except BluetoothError:
        live_states = {}

    # Get stored devices - exclude ignored unless specifically filtering for them
    store_filter = filter if filter in ("favorites", "ignored") else "all"
    include_ignored = filter == "ignored"  # Only show ignored devices on the Ignored filter
    stored_devices = await store.get_all_devices(
        filter_type=store_filter, sort_by=sort, include_ignored=include_ignored
    )

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
    """Update user-editable fields on a device (alias, is_favorite, is_ignored, notes)."""
    mac = _validate_mac(mac_address)
    logger.info("Updating device %s: %s", mac, body.model_dump(exclude_none=True))

    update_fields: dict[str, Any] = {}
    if body.alias is not None:
        update_fields["alias"] = body.alias
    if body.is_favorite is not None:
        update_fields["is_favorite"] = body.is_favorite
    if body.is_ignored is not None:
        update_fields["is_ignored"] = body.is_ignored
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

    # If on detail page, just return the button
    if target.startswith("detail-favorite-"):
        return render_template("partials/favorite_button_detail.html", request, device=device)

    # Check current filter to determine if device should be hidden
    current_url = request.headers.get("hx-current-url", "")
    current_filter = "all"
    if "filter=paired" in current_url:
        current_filter = "paired"
    elif "filter=connected" in current_url:
        current_filter = "connected"
    elif "filter=favorites" in current_url:
        current_filter = "favorites"
    elif "filter=ignored" in current_url:
        current_filter = "ignored"
    elif "filter=history" in current_url:
        current_filter = "history"

    # Determine if device should be hidden from current view
    should_hide = False
    if current_filter == "favorites" and not device.is_favorite:
        # Un-favoriting from favorites view -> hide
        should_hide = True
    elif current_filter == "all" and not device.in_range:
        # "all" only shows in-range devices
        should_hide = True
    elif current_filter == "history" and device.in_range:
        # "history" only shows out-of-range devices
        should_hide = True

    if should_hide:
        return Response(content="", status_code=200, media_type="text/html")

    # Return the updated card/row
    if target.startswith("device-row-"):
        template_name = "partials/device_row.html"
    else:
        template_name = "partials/device_card.html"

    return render_template(template_name, request, device=device)


@router.post("/api/devices/{mac_address}/ignore")
async def toggle_ignored(
    mac_address: str,
    request: Request,
    store: Annotated[DeviceStore, Depends(get_device_store)],
    bt: Annotated[BlueZManager, Depends(get_bluetooth_manager)],
    templates: Annotated[Jinja2Templates, Depends(get_templates)],
    is_ignored: bool = Form(...),
) -> Response:
    """Toggle ignored status on a device (HTMX endpoint, returns HTML partial).

    When ignoring a device from a non-ignored view, returns empty content to hide the card.
    When un-ignoring from the ignored view, returns empty content to hide the card.
    Also includes out-of-band update for filter button counts.
    """
    mac = _validate_mac(mac_address)
    logger.info("Setting ignored=%s for device %s", is_ignored, mac)

    updated = await store.update_device(mac, is_ignored=is_ignored)
    if updated is None:
        raise DeviceNotFoundError(mac)

    # Get live state for this device
    try:
        live = await bt.get_device_state(mac)
    except (DeviceNotFoundError, BluetoothError):
        live = None

    device = _build_runtime_state(updated, live)

    # Check current filter from URL
    current_url = request.headers.get("hx-current-url", "")
    on_devices_page = "/devices" in current_url

    # Parse current filter
    current_filter = "all"
    if "filter=paired" in current_url:
        current_filter = "paired"
    elif "filter=connected" in current_url:
        current_filter = "connected"
    elif "filter=favorites" in current_url:
        current_filter = "favorites"
    elif "filter=ignored" in current_url:
        current_filter = "ignored"
    elif "filter=history" in current_url:
        current_filter = "history"

    # Determine the HTMX target
    target = request.headers.get("hx-target", "")

    # If on detail page (targeting the button itself), just update the button
    if target.startswith("detail-ignored-"):
        return render_template("partials/ignored_button_detail.html", request, device=device)

    # Calculate updated counts for filter buttons (only if on devices page)
    filter_buttons_html = ""
    if on_devices_page:
        # Get all devices and live states for counting
        all_devices = await store.get_all_devices(include_ignored=True)
        try:
            live_states = await bt.get_all_device_states()
        except BluetoothError:
            live_states = {}

        # Count stats (matching the logic in devices_page)
        paired_count = 0
        connected_count = 0
        favorite_count = 0
        ignored_count = 0
        in_range_count = 0
        history_count = 0

        for d in all_devices:
            d_mac = str(d["mac_address"])
            d_live = live_states.get(d_mac)
            d_runtime = _build_runtime_state(d, d_live)

            if d_runtime.is_ignored:
                ignored_count += 1
                continue

            # Count in-range vs history (non-ignored only)
            if d_runtime.in_range:
                in_range_count += 1
                if d_runtime.paired:
                    paired_count += 1
                if d_runtime.connected:
                    connected_count += 1
                if d_runtime.is_favorite:
                    favorite_count += 1
            else:
                history_count += 1

        # Render the filter buttons partial
        filter_buttons_html = templates.get_template("partials/device_filter_buttons.html").render(
            request=request,
            device_count=in_range_count,
            paired_count=paired_count,
            connected_count=connected_count,
            favorite_count=favorite_count,
            ignored_count=ignored_count,
            history_count=history_count,
            current_filter=current_filter,
        )

    # Determine if the device should be hidden from current view
    # Rules:
    # - Ignoring from any non-ignored view -> hide
    # - Un-ignoring from ignored view -> hide (device leaves the ignored list)
    # - "all" filter only shows in-range devices -> hide if not in_range
    # - "history" filter only shows out-of-range devices -> hide if in_range
    # - "paired" filter -> hide if not paired
    # - "connected" filter -> hide if not connected
    # - "favorites" filter -> hide if not favorite
    should_hide = False

    if is_ignored and current_filter != "ignored":
        # Ignoring a device from a non-ignored view -> hide it
        should_hide = True
    elif not is_ignored and current_filter == "ignored":
        # Un-ignoring from the ignored view -> hide it (it's no longer ignored)
        should_hide = True
    elif current_filter == "all" and not device.in_range:
        # "all" only shows in-range devices
        should_hide = True
    elif current_filter == "history" and device.in_range:
        # "history" only shows out-of-range devices
        should_hide = True
    elif (
        (current_filter == "paired" and not device.paired)
        or (current_filter == "connected" and not device.connected)
        or (current_filter == "favorites" and not device.is_favorite)
    ):
        should_hide = True

    if should_hide:
        # Return empty content (to remove the card) + OOB filter buttons update
        return Response(content=filter_buttons_html, status_code=200, media_type="text/html")

    # Otherwise return the updated card/row + OOB filter buttons
    if target.startswith("device-row-"):
        template_name = "partials/device_row.html"
    else:
        template_name = "partials/device_card.html"

    # Render the device card/row
    card_html = templates.get_template(template_name).render(
        request=request,
        device=device,
    )

    # Combine card + OOB filter buttons
    return Response(
        content=card_html + filter_buttons_html, status_code=200, media_type="text/html"
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

    return render_template(template_name, request, device=device)


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
    filter: str = Query(
        default="all", pattern="^(all|paired|connected|favorites|ignored|history)$"
    ),
    sort: str = Query(default="last_seen", pattern="^(last_seen|name|last_connected)$"),
) -> object:
    """Serve the devices list page."""
    # Get live states from BlueZ
    try:
        live_states = await bt.get_all_device_states()
    except BluetoothError:
        live_states = {}

    # Single DB query: get ALL devices (including ignored) for counts and display
    all_devices_for_counts = await store.get_all_devices(
        filter_type="all", sort_by=sort, include_ignored=True
    )

    # Build the filtered view from the full list (avoids a second DB query)
    if filter == "favorites":
        stored_devices = [d for d in all_devices_for_counts if d.get("is_favorite")]
    elif filter == "ignored":
        stored_devices = [d for d in all_devices_for_counts if d.get("is_ignored")]
    else:
        # "all", "paired", "connected", "history" — exclude ignored
        stored_devices = [d for d in all_devices_for_counts if not d.get("is_ignored")]

    # Upsert any BlueZ-known devices not yet in the store
    stored_macs = {d["mac_address"] for d in stored_devices}
    all_macs_for_counts = {d["mac_address"] for d in all_devices_for_counts}
    # Also track which devices are ignored (for filtering)
    ignored_macs = {d["mac_address"] for d in all_devices_for_counts if d.get("is_ignored")}

    for mac, live_data in live_states.items():
        new_record = None
        if mac not in all_macs_for_counts:
            # New device discovered by BlueZ - upsert to store
            new_record = await store.upsert_device(
                mac,
                name=live_data.get("name"),
                device_type=live_data.get("device_type"),
            )
            all_devices_for_counts.append(new_record)

        # Add to stored_devices only if:
        # 1. Not already in stored_devices
        # 2. Not filtering for ignored devices
        # 3. Device is NOT ignored (don't show ignored devices on "all" filter)
        if mac not in stored_macs and filter != "ignored" and mac not in ignored_macs:
            if new_record is None:
                new_record = await store.upsert_device(
                    mac,
                    name=live_data.get("name"),
                    device_type=live_data.get("device_type"),
                )
            stored_devices.append(new_record)

    # Calculate counts from ALL devices (including ignored) for filter button accuracy
    paired_count = 0
    connected_count = 0
    favorite_count = 0
    ignored_count = 0
    in_range_count = 0
    history_count = 0

    for stored in all_devices_for_counts:
        mac = str(stored["mac_address"])
        live = live_states.get(mac)
        runtime = _build_runtime_state(stored, live)

        # Count ignored devices separately
        if runtime.is_ignored:
            ignored_count += 1
            continue

        # Count favorites/paired/connected across ALL devices (not just in-range)
        if runtime.is_favorite:
            favorite_count += 1
        if runtime.paired:
            paired_count += 1
        if runtime.connected:
            connected_count += 1

        # Count in-range vs history (non-ignored only)
        if runtime.in_range:
            in_range_count += 1
        else:
            history_count += 1

    # Build runtime states for display (from filtered stored_devices)
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

        # "all" filter: only show in-range devices (excludes history)
        if filter == "all" and not runtime.in_range:
            continue

        # "history" filter: only show out-of-range devices
        if filter == "history" and runtime.in_range:
            continue

        devices.append(runtime)

    return render_template(
        "devices.html",
        request,
        devices=devices,
        device_count=in_range_count,
        paired_count=paired_count,
        connected_count=connected_count,
        favorite_count=favorite_count,
        ignored_count=ignored_count,
        history_count=history_count,
        current_filter=filter,
        current_sort=sort,
        is_scanning=bt.is_scanning,
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

    return render_template("device.html", request, device=device)


# --- Factory functions for library usage ---


def create_api_router(container: ServiceContainer) -> APIRouter:
    """Create an APIRouter with device API endpoints using the ServiceContainer.

    Includes all /api/devices/* routes. Handlers access container.services at request time.
    """
    from bt_hub.api import AdapterUnavailableError

    api = APIRouter()

    def _get_bt() -> BlueZManager:
        assert container.services is not None
        bt = container.services.bluez_mgr
        if bt is None:
            raise AdapterUnavailableError("BlueZManager not initialized")
        return bt

    def _get_store() -> DeviceStore:
        assert container.services is not None
        return container.services.device_store

    @api.get("/api/devices", response_model=DeviceListResponse)
    async def list_devices_factory(
        filter: str = Query(default="all", pattern="^(all|paired|connected|favorites|ignored)$"),
        sort: str = Query(default="last_seen", pattern="^(last_seen|name|last_connected)$"),
    ) -> DeviceListResponse:
        bt = _get_bt()
        store = _get_store()
        try:
            live_states = await bt.get_all_device_states()
        except BluetoothError:
            live_states = {}
        store_filter = filter if filter in ("favorites", "ignored") else "all"
        include_ignored = filter == "ignored"
        stored_devices = await store.get_all_devices(
            filter_type=store_filter, sort_by=sort, include_ignored=include_ignored
        )
        stored_macs = {d["mac_address"] for d in stored_devices}
        for mac, live_data in live_states.items():
            if mac not in stored_macs:
                new_record = await store.upsert_device(
                    mac, name=live_data.get("name"), device_type=live_data.get("device_type")
                )
                stored_devices.append(new_record)
        devices: list[DeviceRuntimeState] = []
        for stored in stored_devices:
            mac = str(stored["mac_address"])
            live = live_states.get(mac)
            runtime = _build_runtime_state(stored, live)
            if filter == "paired" and not runtime.paired:
                continue
            if filter == "connected" and not runtime.connected:
                continue
            devices.append(runtime)
        return DeviceListResponse(devices=devices, count=len(devices))

    @api.get("/api/devices/{mac_address}", response_model=DeviceRuntimeState)
    async def get_device_factory(mac_address: str) -> DeviceRuntimeState:
        bt = _get_bt()
        store = _get_store()
        mac = _validate_mac(mac_address)
        stored = await store.get_device(mac)
        if not stored:
            raise DeviceNotFoundError(mac)
        try:
            live = await bt.get_device_state(mac)
        except (DeviceNotFoundError, BluetoothError):
            live = None
        return _build_runtime_state(stored, live)

    @api.patch("/api/devices/{mac_address}", response_model=DeviceRuntimeState)
    async def update_device_factory(mac_address: str, body: DeviceUpdate) -> DeviceRuntimeState:
        bt = _get_bt()
        store = _get_store()
        mac = _validate_mac(mac_address)
        update_fields: dict[str, Any] = {}
        if body.alias is not None:
            update_fields["alias"] = body.alias
        if body.is_favorite is not None:
            update_fields["is_favorite"] = body.is_favorite
        if body.is_ignored is not None:
            update_fields["is_ignored"] = body.is_ignored
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

    @api.delete("/api/devices/{mac_address}")
    async def delete_device_factory(mac_address: str) -> dict[str, str]:
        store = _get_store()
        mac = _validate_mac(mac_address)
        deleted = await store.delete_device(mac)
        if not deleted:
            raise DeviceNotFoundError(mac)
        return {"status": "deleted", "mac_address": mac}

    @api.post("/api/devices/{mac_address}/pair", response_model=None)
    async def pair_device_factory(mac_address: str, request: Request) -> object:
        bt = _get_bt()
        store = _get_store()
        mac = _validate_mac(mac_address)
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
        htmx_resp = _htmx_device_response(request, get_templates_optional(), device)
        if htmx_resp is not None:
            return htmx_resp
        return JSONResponse(DeviceActionResponse(mac_address=mac, status="paired").model_dump())

    @api.post("/api/devices/{mac_address}/connect", response_model=None)
    async def connect_device_factory(mac_address: str, request: Request) -> object:
        bt = _get_bt()
        store = _get_store()
        mac = _validate_mac(mac_address)
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
        htmx_resp = _htmx_device_response(request, get_templates_optional(), device)
        if htmx_resp is not None:
            return htmx_resp
        return JSONResponse(DeviceActionResponse(mac_address=mac, status="connected").model_dump())

    @api.post("/api/devices/{mac_address}/disconnect", response_model=None)
    async def disconnect_device_factory(mac_address: str, request: Request) -> object:
        bt = _get_bt()
        store = _get_store()
        mac = _validate_mac(mac_address)
        await bt.disconnect_device(mac)
        stored = await store.get_device(mac)
        if stored is None:
            raise DeviceNotFoundError(mac)
        try:
            live = await bt.get_device_state(mac)
        except (DeviceNotFoundError, BluetoothError):
            live = None
        device = _build_runtime_state(stored, live)
        htmx_resp = _htmx_device_response(request, get_templates_optional(), device)
        if htmx_resp is not None:
            return htmx_resp
        return JSONResponse(
            DeviceActionResponse(mac_address=mac, status="disconnected").model_dump()
        )

    @api.post("/api/devices/{mac_address}/trust", response_model=None)
    async def trust_device_factory(mac_address: str, request: Request) -> object:
        bt = _get_bt()
        store = _get_store()
        mac = _validate_mac(mac_address)
        await bt.trust_device(mac)
        stored = await store.get_device(mac)
        if not stored:
            stored = await store.upsert_device(mac)
        try:
            live = await bt.get_device_state(mac)
        except (DeviceNotFoundError, BluetoothError):
            live = None
        device = _build_runtime_state(stored, live)
        htmx_resp = _htmx_device_response(request, get_templates_optional(), device)
        if htmx_resp is not None:
            return htmx_resp
        return JSONResponse(device.model_dump(mode="json"))

    @api.post("/api/devices/{mac_address}/untrust", response_model=None)
    async def untrust_device_factory(mac_address: str, request: Request) -> object:
        bt = _get_bt()
        store = _get_store()
        mac = _validate_mac(mac_address)
        await bt.untrust_device(mac)
        stored = await store.get_device(mac)
        if not stored:
            stored = await store.upsert_device(mac)
        try:
            live = await bt.get_device_state(mac)
        except (DeviceNotFoundError, BluetoothError):
            live = None
        device = _build_runtime_state(stored, live)
        htmx_resp = _htmx_device_response(request, get_templates_optional(), device)
        if htmx_resp is not None:
            return htmx_resp
        return JSONResponse(device.model_dump(mode="json"))

    @api.post("/api/devices/{mac_address}/remove", response_model=None)
    async def remove_device_factory(mac_address: str, request: Request) -> object:
        bt = _get_bt()
        store = _get_store()
        mac = _validate_mac(mac_address)
        await bt.remove_device(mac)
        if "hx-request" in request.headers:
            stored = await store.get_device(mac)
            if stored:
                device = _build_runtime_state(stored, None)
                htmx_resp = _htmx_device_response(request, get_templates_optional(), device)
                if htmx_resp is not None:
                    return htmx_resp
        return {"status": "removed", "mac_address": mac}

    @api.post("/api/devices/{mac_address}/favorite")
    async def toggle_favorite_factory(
        mac_address: str,
        request: Request,
        is_favorite: bool = Form(...),
    ) -> Response:
        bt = _get_bt()
        store = _get_store()
        mac = _validate_mac(mac_address)
        updated = await store.update_device(mac, is_favorite=is_favorite)
        if updated is None:
            raise DeviceNotFoundError(mac)
        try:
            live = await bt.get_device_state(mac)
        except (DeviceNotFoundError, BluetoothError):
            live = None
        device = _build_runtime_state(updated, live)
        target = request.headers.get("hx-target", "")
        if target.startswith("detail-favorite-"):
            return render_template("partials/favorite_button_detail.html", request, device=device)
        current_url = request.headers.get("hx-current-url", "")
        current_filter = "all"
        for f in ("paired", "connected", "favorites", "ignored", "history"):
            if f"filter={f}" in current_url:
                current_filter = f
                break
        should_hide = False
        if (
            (current_filter == "favorites" and not device.is_favorite)
            or (current_filter == "all" and not device.in_range)
            or (current_filter == "history" and device.in_range)
        ):
            should_hide = True
        if should_hide:
            return Response(content="", status_code=200, media_type="text/html")
        if target.startswith("device-row-"):
            template_name = "partials/device_row.html"
        else:
            template_name = "partials/device_card.html"
        return render_template(template_name, request, device=device)

    @api.post("/api/devices/{mac_address}/ignore")
    async def toggle_ignored_factory(
        mac_address: str,
        request: Request,
        is_ignored: bool = Form(...),
    ) -> Response:
        bt = _get_bt()
        store = _get_store()
        mac = _validate_mac(mac_address)
        updated = await store.update_device(mac, is_ignored=is_ignored)
        if updated is None:
            raise DeviceNotFoundError(mac)
        try:
            live = await bt.get_device_state(mac)
        except (DeviceNotFoundError, BluetoothError):
            live = None
        device = _build_runtime_state(updated, live)
        target = request.headers.get("hx-target", "")
        if target.startswith("detail-ignored-"):
            return render_template("partials/ignored_button_detail.html", request, device=device)
        current_url = request.headers.get("hx-current-url", "")
        current_filter = "all"
        for f in ("paired", "connected", "favorites", "ignored", "history"):
            if f"filter={f}" in current_url:
                current_filter = f
                break
        should_hide = False
        if (
            (is_ignored and current_filter != "ignored")
            or (not is_ignored and current_filter == "ignored")
            or (current_filter == "all" and not device.in_range)
            or (current_filter == "history" and device.in_range)
            or (
                (current_filter == "paired" and not device.paired)
                or (current_filter == "connected" and not device.connected)
                or (current_filter == "favorites" and not device.is_favorite)
            )
        ):
            should_hide = True
        if should_hide:
            return Response(content="", status_code=200, media_type="text/html")
        if target.startswith("device-row-"):
            template_name = "partials/device_row.html"
        else:
            template_name = "partials/device_card.html"
        return render_template(template_name, request, device=device)

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

    def _get_store() -> DeviceStore:
        assert container.services is not None
        return container.services.device_store

    @pages.get("/devices")
    async def devices_page_factory(
        request: Request,
        filter: str = Query(
            default="all", pattern="^(all|paired|connected|favorites|ignored|history)$"
        ),
        sort: str = Query(default="last_seen", pattern="^(last_seen|name|last_connected)$"),
    ) -> object:
        bt = _get_bt()
        store = _get_store()
        try:
            live_states = await bt.get_all_device_states() if bt else {}
        except BluetoothError:
            live_states = {}
        store_filter = filter if filter in ("favorites", "ignored") else "all"
        include_ignored = filter == "ignored"
        stored_devices = await store.get_all_devices(
            filter_type=store_filter, sort_by=sort, include_ignored=include_ignored
        )
        all_devices_for_counts = await store.get_all_devices(
            filter_type="all", sort_by="last_seen", include_ignored=True
        )
        stored_macs = {d["mac_address"] for d in stored_devices}
        all_macs_for_counts = {d["mac_address"] for d in all_devices_for_counts}
        ignored_macs = {d["mac_address"] for d in all_devices_for_counts if d.get("is_ignored")}
        for mac, live_data in live_states.items():
            new_record = None
            if mac not in all_macs_for_counts:
                new_record = await store.upsert_device(
                    mac, name=live_data.get("name"), device_type=live_data.get("device_type")
                )
                all_devices_for_counts.append(new_record)
            if mac not in stored_macs and filter != "ignored" and mac not in ignored_macs:
                if new_record is None:
                    new_record = await store.upsert_device(
                        mac, name=live_data.get("name"), device_type=live_data.get("device_type")
                    )
                stored_devices.append(new_record)
        paired_count = 0
        connected_count = 0
        favorite_count = 0
        ignored_count = 0
        in_range_count = 0
        history_count = 0
        for stored in all_devices_for_counts:
            mac = str(stored["mac_address"])
            live = live_states.get(mac)
            runtime = _build_runtime_state(stored, live)
            if runtime.is_ignored:
                ignored_count += 1
                continue
            if runtime.is_favorite:
                favorite_count += 1
            if runtime.paired:
                paired_count += 1
            if runtime.connected:
                connected_count += 1
            if runtime.in_range:
                in_range_count += 1
            else:
                history_count += 1
        devices: list[DeviceRuntimeState] = []
        for stored in stored_devices:
            mac = str(stored["mac_address"])
            live = live_states.get(mac)
            runtime = _build_runtime_state(stored, live)
            if filter == "paired" and not runtime.paired:
                continue
            if filter == "connected" and not runtime.connected:
                continue
            if filter == "all" and not runtime.in_range:
                continue
            if filter == "history" and runtime.in_range:
                continue
            devices.append(runtime)
        return render_template(
            "devices.html",
            request,
            devices=devices,
            device_count=in_range_count,
            paired_count=paired_count,
            connected_count=connected_count,
            favorite_count=favorite_count,
            ignored_count=ignored_count,
            history_count=history_count,
            current_filter=filter,
            current_sort=sort,
            is_scanning=bt.is_scanning if bt else False,
            active_page=active_page_prefix,
        )

    @pages.get("/devices/{mac_address}")
    async def device_detail_page_factory(mac_address: str, request: Request) -> object:
        bt = _get_bt()
        store = _get_store()
        mac = _validate_mac(mac_address)
        stored = await store.get_device(mac)
        if not stored:
            raise DeviceNotFoundError(mac)
        try:
            live = await bt.get_device_state(mac) if bt else None
        except (DeviceNotFoundError, BluetoothError):
            live = None
        device = _build_runtime_state(stored, live)
        return render_template(
            "device.html", request, device=device, active_page=active_page_prefix
        )

    return pages
