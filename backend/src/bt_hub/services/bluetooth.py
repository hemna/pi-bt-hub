"""BlueZ D-Bus service for managing Bluetooth adapter and devices."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING, Any

try:
    from dbus_fast import BusType, Message, Variant
    from dbus_fast.aio import MessageBus

    HAS_DBUS_FAST = True
except ImportError:
    HAS_DBUS_FAST = False
    BusType = None  # type: ignore[assignment,misc]
    Message = None  # type: ignore[assignment,misc]
    Variant = None  # type: ignore[assignment,misc]
    MessageBus = None  # type: ignore[assignment,misc]

from bt_hub.api import (
    AdapterUnavailableError,
    AlreadyConnectedError,
    AlreadyDisconnectedError,
    AlreadyPairedError,
    AlreadyScanningError,
    BluetoothError,
    ConnectionFailedError,
    DeviceNotFoundError,
    NotPairedError,
    PairingFailedError,
)
from bt_hub.models.device import AdapterState, DeviceType
from bt_hub.services.event_bus import Event

if TYPE_CHECKING:
    from bt_hub.services.event_bus import EventBus

logger = logging.getLogger(__name__)

BLUEZ_SERVICE = "org.bluez"
ADAPTER_INTERFACE = "org.bluez.Adapter1"
DEVICE_INTERFACE = "org.bluez.Device1"
PROPERTIES_INTERFACE = "org.freedesktop.DBus.Properties"
OBJECT_MANAGER_INTERFACE = "org.freedesktop.DBus.ObjectManager"
AGENT_MANAGER_INTERFACE = "org.bluez.AgentManager1"

from bt_hub.services.bt_agent import AGENT_PATH, AutoAcceptAgent  # noqa: E402


def _mac_to_device_path(mac: str, adapter: str = "hci0") -> str:
    """Convert a MAC address to a BlueZ D-Bus object path."""
    dev = mac.upper().replace(":", "_")
    return f"/org/bluez/{adapter}/dev_{dev}"


def _device_path_to_mac(path: str) -> str | None:
    """Extract a MAC address from a BlueZ device object path."""
    # Path format: /org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF
    parts = path.split("/")
    if len(parts) < 5 or not parts[-1].startswith("dev_"):
        return None
    raw = parts[-1][4:]  # strip "dev_"
    return raw.replace("_", ":")


def _classify_device_type(icon: str | None) -> DeviceType:
    """Map BlueZ Icon property to our DeviceType enum."""
    if not icon:
        return DeviceType.OTHER
    icon_lower = icon.lower()
    if "audio" in icon_lower or "headset" in icon_lower or "headphone" in icon_lower:
        return DeviceType.AUDIO
    if "input" in icon_lower or "keyboard" in icon_lower or "mouse" in icon_lower:
        return DeviceType.INPUT
    if "phone" in icon_lower:
        return DeviceType.PHONE
    if "computer" in icon_lower or "laptop" in icon_lower:
        return DeviceType.COMPUTER
    if "network" in icon_lower:
        return DeviceType.NETWORK
    return DeviceType.OTHER


def _unwrap_variant(value: Any) -> Any:
    """Unwrap dbus_fast Variant to a plain Python value."""
    if isinstance(value, Variant):
        return value.value
    return value


def _unwrap_props(props: dict[str, Any]) -> dict[str, Any]:
    """Unwrap all Variant values in a properties dict."""
    return {k: _unwrap_variant(v) for k, v in props.items()}


class BlueZManager:
    """Manages interaction with BlueZ over D-Bus."""

    def __init__(self, event_bus: EventBus, adapter_name: str = "hci0") -> None:
        self._event_bus = event_bus
        self._adapter_name = adapter_name
        self._adapter_path = f"/org/bluez/{adapter_name}"
        self._bus: MessageBus | None = None
        self._is_scanning = False
        self._scan_task: asyncio.Task[None] | None = None
        self._signal_handlers: list[Any] = []

    @property
    def is_scanning(self) -> bool:
        """Whether a scan is currently in progress."""
        return self._is_scanning

    # --- Lifecycle ---

    async def startup(self) -> None:
        """Connect to the system D-Bus and subscribe to BlueZ signals."""
        if not HAS_DBUS_FAST:
            logger.error("dbus-fast is not installed; Bluetooth features are unavailable")
            raise AdapterUnavailableError(
                "dbus-fast package is not installed. Install it with: pip install dbus-fast"
            )
        try:
            self._bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        except Exception as exc:
            logger.error("Failed to connect to system D-Bus: %s", exc)
            raise AdapterUnavailableError(f"Cannot connect to system D-Bus: {exc}") from exc

        # Subscribe to PropertiesChanged on the bluez service
        try:
            await self._subscribe_signals()
        except Exception:
            logger.warning("Failed to subscribe to BlueZ signals", exc_info=True)

        # Register auto-accept pairing agent
        try:
            await self._register_agent()
        except Exception:
            logger.warning("Failed to register pairing agent", exc_info=True)

        logger.info("BlueZManager connected to D-Bus (adapter: %s)", self._adapter_name)

    async def shutdown(self) -> None:
        """Stop any active scan and disconnect from D-Bus."""
        if self._scan_task and not self._scan_task.done():
            self._scan_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._scan_task
            self._scan_task = None

        if self._is_scanning:
            try:
                await self.stop_discovery()
            except Exception:
                logger.debug("Error stopping discovery during shutdown", exc_info=True)

        if self._bus:
            self._bus.disconnect()
            self._bus = None

        logger.info("BlueZManager shut down")

    # --- D-Bus helpers ---

    def _ensure_bus(self) -> MessageBus:
        """Return the active message bus or raise."""
        if self._bus is None:
            raise AdapterUnavailableError("D-Bus connection not established")
        return self._bus

    async def _call_method(
        self,
        path: str,
        interface: str,
        method: str,
        signature: str = "",
        body: list[Any] | None = None,
    ) -> Any:
        """Call a D-Bus method and return the reply body."""
        bus = self._ensure_bus()
        try:
            reply = await bus.call(
                Message(
                    destination=BLUEZ_SERVICE,
                    path=path,
                    interface=interface,
                    member=method,
                    signature=signature,
                    body=body or [],
                )
            )
        except Exception as exc:
            logger.error("D-Bus call %s.%s on %s failed: %s", interface, method, path, exc)
            raise BluetoothError(
                error="dbus_error",
                message=f"D-Bus call {method} failed: {exc}",
                status_code=503,
            ) from exc

        if reply.message_type.name == "ERROR":
            error_name = reply.error_name or "unknown"
            error_body = reply.body[0] if reply.body else "no details"
            logger.warning(
                "D-Bus error from %s.%s: %s - %s",
                interface,
                method,
                error_name,
                error_body,
            )
            raise BluetoothError(
                error="dbus_error",
                message=f"{error_name}: {error_body}",
                status_code=503,
            )

        return reply.body

    async def _get_properties(self, path: str, interface: str) -> dict[str, Any]:
        """Get all properties for an interface via org.freedesktop.DBus.Properties."""
        result = await self._call_method(
            path=path,
            interface=PROPERTIES_INTERFACE,
            method="GetAll",
            signature="s",
            body=[interface],
        )
        if result:
            return _unwrap_props(result[0])
        return {}

    async def _set_property(
        self,
        path: str,
        interface: str,
        prop: str,
        variant: Variant,
    ) -> None:
        """Set a single property via org.freedesktop.DBus.Properties.Set."""
        await self._call_method(
            path=path,
            interface=PROPERTIES_INTERFACE,
            method="Set",
            signature="ssv",
            body=[interface, prop, variant],
        )

    async def _subscribe_signals(self) -> None:
        """Subscribe to PropertiesChanged and InterfacesAdded/Removed signals."""
        bus = self._ensure_bus()

        # Use add_match to listen for PropertiesChanged on all BlueZ paths
        # This catches both adapter and device property changes
        await bus.call(
            Message(
                destination="org.freedesktop.DBus",
                path="/org/freedesktop/DBus",
                interface="org.freedesktop.DBus",
                member="AddMatch",
                signature="s",
                body=[
                    "type='signal',"
                    "sender='org.bluez',"
                    "interface='org.freedesktop.DBus.Properties',"
                    "member='PropertiesChanged'"
                ],
            )
        )

        # Also listen for InterfacesAdded (new devices)
        await bus.call(
            Message(
                destination="org.freedesktop.DBus",
                path="/org/freedesktop/DBus",
                interface="org.freedesktop.DBus",
                member="AddMatch",
                signature="s",
                body=[
                    "type='signal',"
                    "sender='org.bluez',"
                    "interface='org.freedesktop.DBus.ObjectManager',"
                    "member='InterfacesAdded'"
                ],
            )
        )

        # Listen for InterfacesRemoved (removed devices)
        await bus.call(
            Message(
                destination="org.freedesktop.DBus",
                path="/org/freedesktop/DBus",
                interface="org.freedesktop.DBus",
                member="AddMatch",
                signature="s",
                body=[
                    "type='signal',"
                    "sender='org.bluez',"
                    "interface='org.freedesktop.DBus.ObjectManager',"
                    "member='InterfacesRemoved'"
                ],
            )
        )

        # Register a message handler on the bus
        bus.add_message_handler(self._on_dbus_message)

    async def _register_agent(self) -> None:
        """Register an auto-accept pairing agent with BlueZ."""
        bus = self._ensure_bus()

        # Export the agent object on the bus
        agent = AutoAcceptAgent()
        bus.export(AGENT_PATH, agent)

        # Register the agent with BlueZ AgentManager
        await bus.call(
            Message(
                destination=BLUEZ_SERVICE,
                path="/org/bluez",
                interface=AGENT_MANAGER_INTERFACE,
                member="RegisterAgent",
                signature="os",
                body=[AGENT_PATH, "NoInputNoOutput"],
            )
        )

        # Make it the default agent
        await bus.call(
            Message(
                destination=BLUEZ_SERVICE,
                path="/org/bluez",
                interface=AGENT_MANAGER_INTERFACE,
                member="RequestDefaultAgent",
                signature="o",
                body=[AGENT_PATH],
            )
        )

        logger.info("Registered auto-accept pairing agent at %s", AGENT_PATH)

    def _on_dbus_message(self, msg: Any) -> bool:
        """Handle incoming D-Bus signals. Returns False to allow other handlers."""
        if msg.message_type.name != "SIGNAL":
            return False

        if msg.member == "PropertiesChanged" and msg.body:
            asyncio.get_running_loop().create_task(
                self._handle_properties_changed(msg.path, msg.body)
            )
        elif msg.member == "InterfacesAdded" and msg.body:
            asyncio.get_running_loop().create_task(self._handle_interfaces_added(msg.body))
        elif msg.member == "InterfacesRemoved" and msg.body:
            asyncio.get_running_loop().create_task(self._handle_interfaces_removed(msg.body))

        return False

    async def _handle_properties_changed(
        self,
        path: str,
        body: list[Any],
    ) -> None:
        """Process a PropertiesChanged signal."""
        if len(body) < 2:
            return
        interface = body[0]
        changed_props = _unwrap_props(body[1]) if body[1] else {}

        if not changed_props:
            return

        if interface == ADAPTER_INTERFACE and path == self._adapter_path:
            # Adapter property changed
            if "Discovering" in changed_props:
                self._is_scanning = bool(changed_props["Discovering"])
            await self._event_bus.publish(
                Event(
                    "adapter_changed",
                    {"path": path, "properties": changed_props},
                )
            )
        elif interface == DEVICE_INTERFACE:
            mac = _device_path_to_mac(path)
            if mac:
                await self._event_bus.publish(
                    Event(
                        "device_updated",
                        {"mac_address": mac, "properties": changed_props},
                    )
                )

    async def _handle_interfaces_added(self, body: list[Any]) -> None:
        """Process an InterfacesAdded signal (new device discovered)."""
        if len(body) < 2:
            return
        path = body[0]
        interfaces = body[1]

        if DEVICE_INTERFACE in interfaces:
            mac = _device_path_to_mac(path)
            if mac:
                props = _unwrap_props(interfaces[DEVICE_INTERFACE])
                await self._event_bus.publish(
                    Event(
                        "device_discovered",
                        {
                            "mac_address": mac,
                            "name": props.get("Name"),
                            "alias": props.get("Alias"),
                            "rssi": props.get("RSSI"),
                            "icon": props.get("Icon"),
                            "paired": props.get("Paired", False),
                            "connected": props.get("Connected", False),
                            "trusted": props.get("Trusted", False),
                        },
                    )
                )

    async def _handle_interfaces_removed(self, body: list[Any]) -> None:
        """Process an InterfacesRemoved signal (device removed)."""
        if len(body) < 2:
            return
        path = body[0]
        interfaces = body[1]

        if DEVICE_INTERFACE in interfaces:
            mac = _device_path_to_mac(path)
            if mac:
                await self._event_bus.publish(
                    Event(
                        "device_removed",
                        {"mac_address": mac},
                    )
                )

    # --- Adapter operations ---

    async def get_adapter_state(self) -> AdapterState:
        """Read current adapter properties and return an AdapterState model."""
        try:
            props = await self._get_properties(self._adapter_path, ADAPTER_INTERFACE)
        except BluetoothError as exc:
            raise AdapterUnavailableError() from exc

        return AdapterState(
            address=props.get("Address", "00:00:00:00:00:00"),
            name=props.get("Name", self._adapter_name),
            powered=props.get("Powered", False),
            discovering=props.get("Discovering", False),
            discoverable=props.get("Discoverable", False),
        )

    async def set_powered(self, powered: bool) -> AdapterState:
        """Set the adapter Powered property."""
        await self._set_property(
            self._adapter_path,
            ADAPTER_INTERFACE,
            "Powered",
            Variant("b", powered),
        )
        return await self.get_adapter_state()

    async def start_discovery(self, duration_seconds: int = 10) -> None:
        """Start Bluetooth discovery, auto-stop after duration_seconds."""
        if self._is_scanning:
            raise AlreadyScanningError()

        await self._call_method(
            path=self._adapter_path,
            interface=ADAPTER_INTERFACE,
            method="StartDiscovery",
        )
        self._is_scanning = True

        await self._event_bus.publish(
            Event(
                "scan_started",
                {"duration_seconds": duration_seconds},
            )
        )

        # Emit device_discovered for all devices BlueZ already knows about,
        # since InterfacesAdded only fires for truly new devices.
        try:
            known_devices = await self.get_all_device_states()
            for mac, props in known_devices.items():
                await self._event_bus.publish(
                    Event(
                        "device_discovered",
                        {
                            "mac_address": mac,
                            "name": props.get("name"),
                            "alias": props.get("alias"),
                            "rssi": props.get("rssi"),
                            "paired": props.get("paired", False),
                            "connected": props.get("connected", False),
                            "device_type": props.get("device_type"),
                        },
                    )
                )
        except Exception:
            logger.debug("Failed to emit cached devices at scan start", exc_info=True)

        # Schedule auto-stop
        self._scan_task = asyncio.create_task(self._auto_stop_discovery(duration_seconds))

    async def _auto_stop_discovery(self, duration: int) -> None:
        """Wait and then stop discovery."""
        try:
            await asyncio.sleep(duration)
            if self._is_scanning:
                # Snapshot all devices before stopping — BlueZ removes
                # transient (unpaired) devices after StopDiscovery.
                try:
                    devices = await self.get_all_device_states()
                    for mac, props in devices.items():
                        await self._event_bus.publish(
                            Event(
                                "device_discovered",
                                {
                                    "mac_address": mac,
                                    "name": props.get("name"),
                                    "alias": props.get("alias"),
                                    "rssi": props.get("rssi"),
                                    "paired": props.get("paired", False),
                                    "connected": props.get("connected", False),
                                    "device_type": props.get("device_type"),
                                },
                            )
                        )
                except Exception:
                    logger.debug("Failed to snapshot devices before stop", exc_info=True)
                await self.stop_discovery()
        except asyncio.CancelledError:
            pass

    async def stop_discovery(self) -> None:
        """Stop Bluetooth discovery."""
        if self._scan_task and not self._scan_task.done():
            self._scan_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._scan_task
            self._scan_task = None

        try:
            await self._call_method(
                path=self._adapter_path,
                interface=ADAPTER_INTERFACE,
                method="StopDiscovery",
            )
        except BluetoothError:
            logger.debug("StopDiscovery failed (may already be stopped)", exc_info=True)
        finally:
            self._is_scanning = False
            logger.info("Scan stopped, publishing scan_stopped event")
            await self._event_bus.publish(Event("scan_stopped", {}))

    # --- Device operations ---

    async def get_all_device_states(self) -> dict[str, dict[str, Any]]:
        """Enumerate all known BlueZ devices via ObjectManager.GetManagedObjects().

        Returns a dict mapping MAC address to device properties.
        """
        result = await self._call_method(
            path="/",
            interface=OBJECT_MANAGER_INTERFACE,
            method="GetManagedObjects",
        )

        devices: dict[str, dict[str, Any]] = {}
        if not result:
            return devices

        managed_objects = result[0]
        for path, interfaces in managed_objects.items():
            if DEVICE_INTERFACE not in interfaces:
                continue
            # Only include devices under our adapter
            if not path.startswith(self._adapter_path + "/"):
                continue
            mac = _device_path_to_mac(path)
            if mac:
                props = _unwrap_props(interfaces[DEVICE_INTERFACE])
                devices[mac] = {
                    "name": props.get("Name") or props.get("Alias"),
                    "alias": props.get("Alias"),
                    "paired": props.get("Paired", False),
                    "connected": props.get("Connected", False),
                    "trusted": props.get("Trusted", False),
                    "rssi": props.get("RSSI"),
                    "icon": props.get("Icon"),
                    "device_type": _classify_device_type(props.get("Icon")).value,
                }

        return devices

    async def get_device_state(self, mac: str) -> dict[str, Any]:
        """Get a single device's BlueZ state by MAC address."""
        path = _mac_to_device_path(mac, self._adapter_name)
        try:
            props = await self._get_properties(path, DEVICE_INTERFACE)
        except BluetoothError as exc:
            raise DeviceNotFoundError(mac) from exc

        return {
            "name": props.get("Name") or props.get("Alias"),
            "alias": props.get("Alias"),
            "paired": props.get("Paired", False),
            "connected": props.get("Connected", False),
            "trusted": props.get("Trusted", False),
            "rssi": props.get("RSSI"),
            "icon": props.get("Icon"),
            "device_type": _classify_device_type(props.get("Icon")).value,
        }

    async def pair_device(self, mac: str) -> None:
        """Pair with a device."""
        path = _mac_to_device_path(mac, self._adapter_name)

        # Check current state — device may have been removed from BlueZ
        # after a scan stopped.
        try:
            props = await self._get_properties(path, DEVICE_INTERFACE)
        except BluetoothError:
            # Device not in BlueZ — start a short scan to re-discover it
            logger.info("Device %s not in BlueZ, starting brief scan to re-discover", mac)
            scan_started = False
            try:
                await self._call_method(
                    path=self._adapter_path,
                    interface=ADAPTER_INTERFACE,
                    method="StartDiscovery",
                )
                scan_started = True
            except BluetoothError as start_err:
                # Discovery may already be running (e.g. from another caller)
                logger.debug("StartDiscovery failed (may already be running): %s", start_err)

            # Wait up to 10 seconds for the device to appear
            props = None
            for i in range(20):
                await asyncio.sleep(0.5)
                try:
                    props = await self._get_properties(path, DEVICE_INTERFACE)
                    logger.info("Device %s appeared in BlueZ after %.1fs", mac, (i + 1) * 0.5)
                    break
                except BluetoothError:
                    continue

            # Stop our scan if we started one
            if scan_started:
                with contextlib.suppress(Exception):
                    await self._call_method(
                        path=self._adapter_path,
                        interface=ADAPTER_INTERFACE,
                        method="StopDiscovery",
                    )

            if props is None:
                raise DeviceNotFoundError(mac)

        if props.get("Paired", False):
            raise AlreadyPairedError()

        try:
            await self._call_method(
                path=path,
                interface=DEVICE_INTERFACE,
                method="Pair",
            )
        except BluetoothError as exc:
            raise PairingFailedError(mac, str(exc.error_message)) from exc

    async def connect_device(self, mac: str) -> None:
        """Connect to a paired device."""
        path = _mac_to_device_path(mac, self._adapter_name)

        try:
            props = await self._get_properties(path, DEVICE_INTERFACE)
        except BluetoothError as exc:
            raise DeviceNotFoundError(mac) from exc

        if not props.get("Paired", False):
            raise NotPairedError()
        if props.get("Connected", False):
            raise AlreadyConnectedError()

        try:
            await self._call_method(
                path=path,
                interface=DEVICE_INTERFACE,
                method="Connect",
            )
        except BluetoothError as exc:
            raise ConnectionFailedError(mac, str(exc.error_message)) from exc

    async def disconnect_device(self, mac: str) -> None:
        """Disconnect from a device."""
        path = _mac_to_device_path(mac, self._adapter_name)

        try:
            props = await self._get_properties(path, DEVICE_INTERFACE)
        except BluetoothError as exc:
            raise DeviceNotFoundError(mac) from exc

        if not props.get("Connected", False):
            raise AlreadyDisconnectedError()

        await self._call_method(
            path=path,
            interface=DEVICE_INTERFACE,
            method="Disconnect",
        )

    async def trust_device(self, mac: str) -> None:
        """Set a device as trusted."""
        path = _mac_to_device_path(mac, self._adapter_name)
        await self._set_property(
            path,
            DEVICE_INTERFACE,
            "Trusted",
            Variant("b", True),
        )

    async def untrust_device(self, mac: str) -> None:
        """Set a device as untrusted."""
        path = _mac_to_device_path(mac, self._adapter_name)
        await self._set_property(
            path,
            DEVICE_INTERFACE,
            "Trusted",
            Variant("b", False),
        )

    async def remove_device(self, mac: str) -> None:
        """Remove a device from the BlueZ adapter."""
        path = _mac_to_device_path(mac, self._adapter_name)
        await self._call_method(
            path=self._adapter_path,
            interface=ADAPTER_INTERFACE,
            method="RemoveDevice",
            signature="o",
            body=[path],
        )
