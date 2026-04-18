"""Service lifecycle management for Pi BT Hub.

Provides BtHubServices dataclass, ServiceContainer, and startup/shutdown functions
that can be used by both the standalone app and external host apps (e.g., digipi-web).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi.templating import Jinja2Templates

if TYPE_CHECKING:
    from bt_hub.config import Settings
    from bt_hub.services.bluetooth import BlueZManager
    from bt_hub.services.bridge_proxy import BridgeProxy
    from bt_hub.services.bt_bridge_client import BtBridgeClient
    from bt_hub.services.device_store import DeviceStore
    from bt_hub.services.event_bus import EventBus
    from bt_hub.services.log_handler import SSELogHandler
    from bt_hub.services.systemd_service import SystemdService

logger = logging.getLogger(__name__)

DEFAULT_TEMPLATE_DIR = Path(__file__).parent / "templates"


def create_templates(
    template_dirs: list[Path] | None = None,
    bridge_enabled: bool = False,
) -> Jinja2Templates:
    """Create a Jinja2Templates instance with optional directory overrides.

    When ``template_dirs`` is provided, uses Jinja2's ChoiceLoader to search
    override directories first, then the default bt-hub template directory.
    This allows the host app to override ``base.html`` while keeping all other
    templates from bt-hub.
    """
    default_dir = DEFAULT_TEMPLATE_DIR
    if template_dirs:
        from jinja2 import ChoiceLoader, FileSystemLoader

        loaders = [FileSystemLoader(str(d)) for d in template_dirs]
        loaders.append(FileSystemLoader(str(default_dir)))
        loader = ChoiceLoader(loaders)
        templates = Jinja2Templates(directory=str(default_dir))
        templates.env.loader = loader
    else:
        templates = Jinja2Templates(directory=str(default_dir))

    templates.env.globals["bridge_enabled"] = bridge_enabled
    return templates


@dataclass
class BtHubServices:
    """Holds all runtime services initialized during application startup."""

    settings: Settings
    device_store: DeviceStore
    event_bus: EventBus
    bt_bridge_client: BtBridgeClient | None = None
    bridge_proxy: BridgeProxy | None = None
    systemd_service: SystemdService | None = None
    log_handler: SSELogHandler | None = None
    bluez_mgr: BlueZManager | None = None


@dataclass
class ServiceContainer:
    """Mutable holder passed to router factories at creation time, populated during lifespan."""

    services: BtHubServices | None = None


async def startup_services(settings: Settings) -> BtHubServices:
    """Initialize all application services.

    Mirrors the logic from main.py lifespan, extracted for reuse by host apps.
    """
    from bt_hub.services.bt_bridge_client import BtBridgeClient
    from bt_hub.services.device_store import DeviceStore
    from bt_hub.services.event_bus import EventBus
    from bt_hub.services.log_handler import setup_sse_logging

    # Logging
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    log_handler = setup_sse_logging(
        level=getattr(logging, settings.log_level.upper(), logging.INFO)
    )

    # Device store
    store = DeviceStore(settings.db_path)
    await store.init_db()

    # Event bus
    bus = EventBus()

    # Bridge client
    bridge_client = BtBridgeClient(settings.bridge_url if settings.bridge_enabled else None)

    # Bridge proxy + systemd service (only when bridge is enabled)
    bridge_proxy: BridgeProxy | None = None
    systemd_service: SystemdService | None = None
    if settings.bridge_enabled:
        from bt_hub.services.bridge_proxy import BridgeProxy
        from bt_hub.services.systemd_service import SystemdService

        bridge_proxy = BridgeProxy(settings.bridge_url)
        await bridge_proxy.startup()
        systemd_service = SystemdService("bt-bridge.service")
        logger.info("Bridge proxy enabled: %s", settings.bridge_url)

    # BlueZ manager
    bluez_mgr: BlueZManager | None = None
    try:
        from bt_hub.services.bluetooth import BlueZManager

        adapter_name = settings.adapter or "hci0"
        bluez_mgr = BlueZManager(bus, adapter_name=adapter_name)
        await bluez_mgr.startup()
    except ImportError:
        logger.warning("dbus-fast not installed; Bluetooth features unavailable")
    except Exception:
        logger.warning(
            "BlueZManager failed to start - Bluetooth features will be unavailable",
            exc_info=True,
        )

    logger.info("Pi BT Hub services started")

    return BtHubServices(
        settings=settings,
        device_store=store,
        event_bus=bus,
        bt_bridge_client=bridge_client,
        bridge_proxy=bridge_proxy,
        systemd_service=systemd_service,
        log_handler=log_handler,
        bluez_mgr=bluez_mgr,
    )


async def shutdown_services(services: BtHubServices) -> None:
    """Shut down all application services in reverse order."""
    if services.bluez_mgr:
        try:
            await services.bluez_mgr.shutdown()
        except Exception:
            logger.warning("Error shutting down BlueZManager", exc_info=True)

    if services.bridge_proxy:
        try:
            await services.bridge_proxy.shutdown()
        except Exception:
            logger.warning("Error shutting down BridgeProxy", exc_info=True)

    await services.device_store.close()

    logger.info("Pi BT Hub services shut down")
