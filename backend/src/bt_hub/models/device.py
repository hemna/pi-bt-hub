"""Dataclasses for Bluetooth devices and adapter state."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum


class DeviceType(StrEnum):
    """Bluetooth device class categories derived from BlueZ Icon property."""

    AUDIO = "audio"
    INPUT = "input"
    PHONE = "phone"
    COMPUTER = "computer"
    NETWORK = "network"
    OTHER = "other"


class ConnectionState(StrEnum):
    """Device connection state machine states."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    PAIRING = "pairing"
    ERROR = "error"


MAC_ADDRESS_PATTERN = re.compile(r"^([0-9A-F]{2}:){5}[0-9A-F]{2}$")

MacAddress = str


def validate_mac_address(value: str) -> str:
    """Validate and normalize a MAC address to uppercase."""
    normalized = value.upper().strip()
    if not MAC_ADDRESS_PATTERN.match(normalized):
        msg = (
            f"Invalid MAC address format: '{value}'. "
            "Expected XX:XX:XX:XX:XX:XX (uppercase hex, colon-separated)."
        )
        raise ValueError(msg)
    return normalized


@dataclass
class DeviceRuntimeState:
    """Live Bluetooth device state from BlueZ. No persistence."""

    mac_address: str
    name: str | None = None
    device_type: DeviceType | None = None
    paired: bool = False
    connected: bool = False
    trusted: bool = False
    rssi: int | None = None
    connection_state: ConnectionState = field(default=ConnectionState.DISCONNECTED)

    def __post_init__(self) -> None:
        self.mac_address = validate_mac_address(self.mac_address)


@dataclass
class AdapterState:
    """Runtime-only model for the local Bluetooth adapter state."""

    address: str
    name: str
    powered: bool
    discovering: bool
    discoverable: bool


@dataclass
class ScanResponse:
    """Response for scan start/stop operations."""

    status: str
    duration_seconds: int | None = None


@dataclass
class DeviceActionResponse:
    """Response for device action operations (pair, connect, etc.)."""

    mac_address: str
    status: str


@dataclass
class DeviceListResponse:
    """Response for device list endpoint."""

    devices: list[DeviceRuntimeState]
    count: int


@dataclass
class ErrorResponse:
    """Consistent error response format per API contract."""

    error: str
    message: str
