"""Pydantic models for Bluetooth devices and adapter state."""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from typing import Annotated

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

MacAddress = Annotated[
    str,
    Field(
        description="Bluetooth MAC address in XX:XX:XX:XX:XX:XX format",
        examples=["AA:BB:CC:DD:EE:FF"],
    ),
]


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


class Device(BaseModel):
    """Persisted Bluetooth device record stored in SQLite."""

    mac_address: MacAddress
    name: str | None = None
    alias: str | None = Field(default=None, min_length=1, max_length=64)
    device_type: DeviceType | None = None
    first_seen: datetime
    last_seen: datetime
    last_connected: datetime | None = None
    is_favorite: bool = False
    notes: str | None = Field(default=None, max_length=500)

    @field_validator("mac_address")
    @classmethod
    def normalize_mac(cls, v: str) -> str:
        """Normalize MAC address to uppercase."""
        return validate_mac_address(v)


class DeviceRuntimeState(Device):
    """Device with live BlueZ state merged in. Not persisted."""

    paired: bool = False
    connected: bool = False
    trusted: bool = False
    rssi: int | None = None
    connection_state: ConnectionState = ConnectionState.DISCONNECTED


class DeviceUpdate(BaseModel):
    """Partial update for user-editable device fields."""

    alias: str | None = Field(default=None, min_length=1, max_length=64)
    is_favorite: bool | None = None
    notes: str | None = Field(default=None, max_length=500)


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
