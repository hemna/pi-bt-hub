"""Unit tests for Device, DeviceRuntimeState, and AdapterState models."""

from __future__ import annotations

import pytest

from bt_hub.models.device import (
    AdapterState,
    ConnectionState,
    Device,
    DeviceRuntimeState,
    DeviceType,
    DeviceUpdate,
    validate_mac_address,
)


class TestMacAddressValidation:
    """Tests for MAC address validation and normalization."""

    def test_valid_uppercase_mac(self) -> None:
        result = validate_mac_address("AA:BB:CC:DD:EE:FF")
        assert result == "AA:BB:CC:DD:EE:FF"

    def test_lowercase_mac_is_normalized(self) -> None:
        result = validate_mac_address("aa:bb:cc:dd:ee:ff")
        assert result == "AA:BB:CC:DD:EE:FF"

    def test_mixed_case_mac_is_normalized(self) -> None:
        result = validate_mac_address("Aa:Bb:Cc:Dd:Ee:Ff")
        assert result == "AA:BB:CC:DD:EE:FF"

    def test_mac_with_whitespace_is_trimmed(self) -> None:
        result = validate_mac_address("  AA:BB:CC:DD:EE:FF  ")
        assert result == "AA:BB:CC:DD:EE:FF"

    def test_invalid_mac_too_short(self) -> None:
        with pytest.raises(ValueError, match="Invalid MAC address"):
            validate_mac_address("AA:BB:CC")

    def test_invalid_mac_wrong_separator(self) -> None:
        with pytest.raises(ValueError, match="Invalid MAC address"):
            validate_mac_address("AA-BB-CC-DD-EE-FF")

    def test_invalid_mac_no_separator(self) -> None:
        with pytest.raises(ValueError, match="Invalid MAC address"):
            validate_mac_address("AABBCCDDEEFF")

    def test_invalid_mac_non_hex(self) -> None:
        with pytest.raises(ValueError, match="Invalid MAC address"):
            validate_mac_address("GG:HH:II:JJ:KK:LL")

    def test_empty_mac(self) -> None:
        with pytest.raises(ValueError, match="Invalid MAC address"):
            validate_mac_address("")


class TestDeviceType:
    """Tests for DeviceType enum."""

    def test_all_device_types(self) -> None:
        expected = {"audio", "input", "phone", "computer", "network", "other"}
        actual = {dt.value for dt in DeviceType}
        assert actual == expected

    def test_device_type_from_string(self) -> None:
        assert DeviceType("audio") == DeviceType.AUDIO


class TestConnectionState:
    """Tests for ConnectionState enum."""

    def test_all_connection_states(self) -> None:
        expected = {"disconnected", "connecting", "connected", "pairing", "error"}
        actual = {cs.value for cs in ConnectionState}
        assert actual == expected


class TestDevice:
    """Tests for Device model creation and validation."""

    def test_create_device_with_all_fields(self) -> None:
        device = Device(
            mac_address="AA:BB:CC:DD:EE:FF",
            name="Test Speaker",
            alias="Living Room",
            device_type=DeviceType.AUDIO,
            first_seen="2026-03-01T10:00:00+00:00",
            last_seen="2026-03-10T14:30:00+00:00",
            last_connected="2026-03-10T14:25:00+00:00",
            is_favorite=True,
            notes="Great sound quality",
        )
        assert device.mac_address == "AA:BB:CC:DD:EE:FF"
        assert device.name == "Test Speaker"
        assert device.alias == "Living Room"
        assert device.device_type == DeviceType.AUDIO
        assert device.is_favorite is True

    def test_create_device_minimal_fields(self) -> None:
        device = Device(
            mac_address="AA:BB:CC:DD:EE:FF",
            first_seen="2026-03-01T10:00:00+00:00",
            last_seen="2026-03-10T14:30:00+00:00",
        )
        assert device.name is None
        assert device.alias is None
        assert device.device_type is None
        assert device.is_favorite is False
        assert device.notes is None

    def test_device_normalizes_mac_to_uppercase(self) -> None:
        device = Device(
            mac_address="aa:bb:cc:dd:ee:ff",
            first_seen="2026-03-01T10:00:00+00:00",
            last_seen="2026-03-10T14:30:00+00:00",
        )
        assert device.mac_address == "AA:BB:CC:DD:EE:FF"

    def test_device_rejects_invalid_mac(self) -> None:
        with pytest.raises(ValueError):
            Device(
                mac_address="invalid",
                first_seen="2026-03-01T10:00:00+00:00",
                last_seen="2026-03-10T14:30:00+00:00",
            )

    def test_device_alias_max_length(self) -> None:
        device = Device(
            mac_address="AA:BB:CC:DD:EE:FF",
            alias="x" * 64,
            first_seen="2026-03-01T10:00:00+00:00",
            last_seen="2026-03-10T14:30:00+00:00",
        )
        assert len(device.alias) == 64  # type: ignore[arg-type]

    def test_device_alias_too_long(self) -> None:
        with pytest.raises(ValueError):
            Device(
                mac_address="AA:BB:CC:DD:EE:FF",
                alias="x" * 65,
                first_seen="2026-03-01T10:00:00+00:00",
                last_seen="2026-03-10T14:30:00+00:00",
            )

    def test_device_notes_max_length(self) -> None:
        device = Device(
            mac_address="AA:BB:CC:DD:EE:FF",
            notes="x" * 500,
            first_seen="2026-03-01T10:00:00+00:00",
            last_seen="2026-03-10T14:30:00+00:00",
        )
        assert len(device.notes) == 500  # type: ignore[arg-type]

    def test_device_notes_too_long(self) -> None:
        with pytest.raises(ValueError):
            Device(
                mac_address="AA:BB:CC:DD:EE:FF",
                notes="x" * 501,
                first_seen="2026-03-01T10:00:00+00:00",
                last_seen="2026-03-10T14:30:00+00:00",
            )


class TestDeviceRuntimeState:
    """Tests for DeviceRuntimeState model merging persisted and live state."""

    def test_runtime_state_defaults(self) -> None:
        state = DeviceRuntimeState(
            mac_address="AA:BB:CC:DD:EE:FF",
            first_seen="2026-03-01T10:00:00+00:00",
            last_seen="2026-03-10T14:30:00+00:00",
        )
        assert state.paired is False
        assert state.connected is False
        assert state.trusted is False
        assert state.rssi is None
        assert state.connection_state == ConnectionState.DISCONNECTED

    def test_runtime_state_with_live_data(self) -> None:
        state = DeviceRuntimeState(
            mac_address="AA:BB:CC:DD:EE:FF",
            name="Speaker",
            first_seen="2026-03-01T10:00:00+00:00",
            last_seen="2026-03-10T14:30:00+00:00",
            paired=True,
            connected=True,
            trusted=True,
            rssi=-45,
            connection_state=ConnectionState.CONNECTED,
        )
        assert state.paired is True
        assert state.connected is True
        assert state.rssi == -45
        assert state.connection_state == ConnectionState.CONNECTED


class TestAdapterState:
    """Tests for AdapterState model."""

    def test_create_adapter_state(self) -> None:
        adapter = AdapterState(
            address="AA:BB:CC:DD:EE:FF",
            name="hci0",
            powered=True,
            discovering=False,
            discoverable=False,
        )
        assert adapter.address == "AA:BB:CC:DD:EE:FF"
        assert adapter.name == "hci0"
        assert adapter.powered is True
        assert adapter.discovering is False


class TestDeviceUpdate:
    """Tests for DeviceUpdate partial update model."""

    def test_all_fields_none_by_default(self) -> None:
        update = DeviceUpdate()
        assert update.alias is None
        assert update.is_favorite is None
        assert update.notes is None

    def test_partial_update(self) -> None:
        update = DeviceUpdate(alias="New Name", is_favorite=True)
        assert update.alias == "New Name"
        assert update.is_favorite is True
        assert update.notes is None
