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

        Implements org.bluez.Agent1 with DisplayYesNo capability.
        Handles all pairing methods: JustWorks, numeric comparison,
        passkey display, passkey entry, and PIN code.
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

        @dbus_method(name="RequestConfirmation")
        def request_confirmation(self, device: "o", passkey: "u") -> None:  # noqa: F821
            """Auto-confirm numeric comparison (SSP). BlueZ shows a 6-digit
            passkey and asks the agent to confirm it matches the remote device."""
            logger.info("Auto-confirming pairing passkey %06d for %s", passkey, device)

        @dbus_method(name="RequestPasskey")
        def request_passkey(self, device: "o") -> "u":  # noqa: F821
            """Return a passkey for pairing. Returns 0 (auto-accept)."""
            logger.info("Returning passkey 0 for %s", device)
            return 0

        @dbus_method(name="DisplayPasskey")
        def display_passkey(self, device: "o", passkey: "u", entered: "q") -> None:  # noqa: F821
            """Display a passkey for the user (logged only)."""
            logger.info("Passkey for %s: %06d (entered: %d)", device, passkey, entered)

        @dbus_method(name="DisplayPinCode")
        def display_pin_code(self, device: "o", pincode: "s") -> None:  # noqa: F821
            """Display a PIN code for the user (logged only)."""
            logger.info("PIN code for %s: %s", device, pincode)

        @dbus_method(name="RequestPinCode")
        def request_pin_code(self, device: "o") -> "s":  # noqa: F821
            """Return a PIN code for legacy pairing."""
            logger.info("Returning PIN '0000' for %s", device)
            return "0000"

        @dbus_method(name="Cancel")
        def cancel(self) -> None:
            logger.debug("Agent pairing cancelled")

else:
    AutoAcceptAgent = None  # type: ignore[assignment,misc]
