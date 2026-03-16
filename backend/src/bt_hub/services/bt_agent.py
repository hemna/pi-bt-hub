"""BlueZ auto-accept pairing agent.

NOTE: This module intentionally does NOT use ``from __future__ import annotations``
because dbus-fast inspects type annotations at class-definition time to derive
D-Bus method signatures.  PEP 563 (stringified annotations) breaks this.
"""

import logging

try:
    from dbus_fast.service import ServiceInterface, dbus_method

    HAS_DBUS_FAST = True
except ImportError:
    HAS_DBUS_FAST = False

logger = logging.getLogger(__name__)

AGENT_PATH = "/org/bt_hub/agent"

if HAS_DBUS_FAST:

    class AutoAcceptAgent(ServiceInterface):
        """BlueZ pairing agent that auto-accepts all pairing requests.

        Implements org.bluez.Agent1 with NoInputNoOutput capability.
        This allows pairing to proceed without user interaction for
        devices that support JustWorks or NoInputNoOutput pairing.
        """

        def __init__(self) -> None:
            super().__init__("org.bluez.Agent1")

        @dbus_method(name="Release")
        def release(self) -> None:
            logger.debug("Agent released")

        @dbus_method(name="RequestAuthorization")
        def request_authorization(self, device: "o") -> None:  # noqa: F821
            logger.info("Auto-authorizing device %s", device)

        @dbus_method(name="AuthorizeService")
        def authorize_service(self, device: "o", uuid: "s") -> None:  # noqa: F821
            logger.info("Auto-authorizing service %s on %s", uuid, device)

        @dbus_method(name="Cancel")
        def cancel(self) -> None:
            logger.debug("Agent pairing cancelled")

else:
    AutoAcceptAgent = None  # type: ignore[assignment,misc]
