"""API endpoints for Bluetooth Web UI.

Defines shared exceptions and error handlers used across all routers.
"""

from __future__ import annotations

from fastapi import HTTPException


class BluetoothError(HTTPException):
    """Base exception for Bluetooth operation failures."""

    def __init__(self, error: str, message: str, status_code: int = 500) -> None:
        self.error_code = error
        self.error_message = message
        super().__init__(
            status_code=status_code,
            detail={"error": error, "message": message},
        )


class DeviceNotFoundError(BluetoothError):
    """Raised when a device MAC address is not found."""

    def __init__(self, mac_address: str) -> None:
        super().__init__(
            error="device_not_found",
            message=f"No device found with address {mac_address}.",
            status_code=404,
        )


class AdapterUnavailableError(BluetoothError):
    """Raised when the Bluetooth adapter is not available."""

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            error="no_adapter",
            message=message
            or (
                "No Bluetooth adapter found. "
                "Check that a Bluetooth adapter is connected and BlueZ is running."
            ),
            status_code=503,
        )


class AlreadyScanningError(BluetoothError):
    """Raised when a scan is requested but one is already in progress."""

    def __init__(self) -> None:
        super().__init__(
            error="already_scanning",
            message="A scan is already in progress.",
            status_code=409,
        )


class AlreadyPairedError(BluetoothError):
    """Raised when pairing is requested but device is already paired."""

    def __init__(self) -> None:
        super().__init__(
            error="already_paired",
            message="Device is already paired.",
            status_code=409,
        )


class NotPairedError(BluetoothError):
    """Raised when connection is requested but device is not paired."""

    def __init__(self) -> None:
        super().__init__(
            error="not_paired",
            message="Device must be paired before connecting.",
            status_code=412,
        )


class AlreadyConnectedError(BluetoothError):
    """Raised when connect is requested but device is already connected."""

    def __init__(self) -> None:
        super().__init__(
            error="already_connected",
            message="Device is already connected.",
            status_code=409,
        )


class AlreadyDisconnectedError(BluetoothError):
    """Raised when disconnect is requested but device is already disconnected."""

    def __init__(self) -> None:
        super().__init__(
            error="already_disconnected",
            message="Device is already disconnected.",
            status_code=409,
        )


class PairingFailedError(BluetoothError):
    """Raised when a pairing attempt fails."""

    def __init__(self, mac_address: str, reason: str = "unknown error") -> None:
        super().__init__(
            error="pairing_failed",
            message=f"Pairing with {mac_address} failed: {reason}.",
            status_code=504,
        )


class ConnectionFailedError(BluetoothError):
    """Raised when a connection attempt fails."""

    def __init__(self, mac_address: str, reason: str = "unknown error") -> None:
        super().__init__(
            error="connection_failed",
            message=f"Connection to {mac_address} failed: {reason}.",
            status_code=504,
        )


class InvalidMacAddressError(BluetoothError):
    """Raised when a MAC address is malformed."""

    def __init__(self, mac_address: str) -> None:
        super().__init__(
            error="validation_error",
            message=f"Invalid MAC address format: '{mac_address}'. "
            "Expected XX:XX:XX:XX:XX:XX (uppercase hex, colon-separated).",
            status_code=422,
        )
