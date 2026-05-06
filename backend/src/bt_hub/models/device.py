"""Pydantic models for Bluetooth devices and adapter state."""

from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


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


class DeviceRuntimeState(BaseModel):
    """Live Bluetooth device state from BlueZ. No persistence."""

    mac_address: str
    name: str | None = None
    device_type: DeviceType | None = None
    paired: bool = False
    connected: bool = False
    trusted: bool = False
    rssi: int | None = None
    connection_state: ConnectionState = ConnectionState.DISCONNECTED

    @field_validator("mac_address")
    @classmethod
    def normalize_mac(cls, v: str) -> str:
        """Normalize MAC address to uppercase."""
        return validate_mac_address(v)


class AdapterState(BaseModel):
    """Runtime-only model for the local Bluetooth adapter state."""

    address: str
    name: str
    powered: bool
    discovering: bool
    discoverable: bool


class PowerRequest(BaseModel):
    """Request body for toggling adapter power."""

    powered: bool


class ScanResponse(BaseModel):
    """Response for scan start/stop operations."""

    status: str
    duration_seconds: int | None = None


class DeviceActionResponse(BaseModel):
    """Response for device action operations (pair, connect, etc.)."""

    mac_address: str
    status: str


class DeviceListResponse(BaseModel):
    """Response for device list endpoint."""

    devices: list[DeviceRuntimeState]
    count: int


class ErrorResponse(BaseModel):
    """Consistent error response format per API contract."""

    error: str
    message: str
