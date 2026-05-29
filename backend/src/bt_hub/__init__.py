"""Pi BT Hub — Bluetooth management and bridge web UI.

Public API:
    - BtHubServices: Dataclass holding all runtime services
    - startup_services / shutdown_services: Lifecycle management
    - create_templates: Jinja2Templates with optional directory override
"""

from bt_hub.lifecycle import (
    DEFAULT_TEMPLATE_DIR,
    BtHubServices,
    create_templates,
    shutdown_services,
    startup_services,
)

__all__ = [
    "DEFAULT_TEMPLATE_DIR",
    "BtHubServices",
    "create_templates",
    "shutdown_services",
    "startup_services",
]
