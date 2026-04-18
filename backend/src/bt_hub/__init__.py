"""Pi BT Hub — Bluetooth management and bridge web UI.

Public API for library usage:
    - BtHubServices: Dataclass holding all runtime services
    - ServiceContainer: Mutable holder for router factory pattern
    - startup_services / shutdown_services: Lifecycle management
    - create_templates: Jinja2Templates with optional directory override
    - create_api_routers / create_page_routers / create_ws_router: Router aggregators
"""

from bt_hub.lifecycle import (
    DEFAULT_TEMPLATE_DIR,
    BtHubServices,
    ServiceContainer,
    create_templates,
    shutdown_services,
    startup_services,
)
from bt_hub.routers import create_api_routers, create_page_routers, create_ws_router

__all__ = [
    "BtHubServices",
    "DEFAULT_TEMPLATE_DIR",
    "ServiceContainer",
    "create_api_routers",
    "create_page_routers",
    "create_templates",
    "create_ws_router",
    "shutdown_services",
    "startup_services",
]
