"""Adapter and scan API endpoints."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates  # noqa: TC002

from bt_hub.api import AdapterUnavailableError
from bt_hub.deps import get_bt_bridge_client, get_device_store, get_templates
from bt_hub.models.device import (
    AdapterState,
    PowerRequest,
    ScanResponse,
)
from bt_hub.services.bluetooth import BlueZManager  # noqa: TC001
from bt_hub.services.bt_bridge_client import BtBridgeClient  # noqa: TC001
from bt_hub.services.device_store import DeviceStore  # noqa: TC001

logger = logging.getLogger(__name__)

router = APIRouter()

# Module-level singleton set by main.py lifespan
_bluetooth_manager: BlueZManager | None = None


def get_bluetooth_manager() -> BlueZManager:
    """Dependency: return the global BlueZManager instance."""
    if _bluetooth_manager is None:
        raise AdapterUnavailableError("BlueZManager not initialized")
    return _bluetooth_manager


def set_bluetooth_manager(manager: BlueZManager) -> None:
    """Called from main.py lifespan to set the global BlueZManager instance."""
    global _bluetooth_manager
    _bluetooth_manager = manager


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
    body: PowerRequest,
    bt: Annotated[BlueZManager, Depends(get_bluetooth_manager)],
) -> AdapterState:
    """Toggle adapter power on or off."""
    logger.info("Setting adapter power to %s", body.powered)
    return await bt.set_powered(body.powered)


@router.post("/api/scan/start", response_model=ScanResponse)
async def start_scan(
    bt: Annotated[BlueZManager, Depends(get_bluetooth_manager)],
    store: Annotated[DeviceStore, Depends(get_device_store)],
    duration: int = 10,
) -> ScanResponse:
    """Start Bluetooth discovery scan."""
    logger.info("Starting scan for %d seconds", duration)
    await bt.start_discovery(duration_seconds=duration)
    return ScanResponse(status="scanning", duration_seconds=duration)


@router.post("/api/scan/stop", response_model=ScanResponse)
async def stop_scan(
    bt: Annotated[BlueZManager, Depends(get_bluetooth_manager)],
) -> ScanResponse:
    """Stop Bluetooth discovery scan."""
    logger.info("Stopping scan")
    await bt.stop_discovery()
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

    # Probe BT Bridge if configured (graceful fallback)
    bridge_status = None
    bridge_port = None
    if bridge_client.is_configured:
        bridge_status = await bridge_client.get_status()
        from bt_hub.config import get_settings

        bridge_port = get_settings().bt_bridge_port

    devices = await store.get_all_devices()
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "adapter": adapter,
            "device_count": len(devices),
            "is_scanning": bt.is_scanning,
            "bridge_status": bridge_status,
            "bridge_configured": bridge_client.is_configured,
            "bridge_port": bridge_port,
        },
    )
