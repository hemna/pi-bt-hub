"""API tests for device endpoints (live BlueZ only, no persistence)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

from bt_hub.api import (
    AlreadyPairedError,
    DeviceNotFoundError,
    NotPairedError,
)

if TYPE_CHECKING:
    from httpx import AsyncClient


class TestListDevices:
    """Tests for GET /api/devices."""

    async def test_list_devices_empty(
        self,
        test_client: AsyncClient,
        mock_bluetooth_manager: MagicMock,
    ) -> None:
        """GET /api/devices returns empty list when no devices discovered."""
        mock_bluetooth_manager.get_all_device_states = AsyncMock(return_value={})

        response = await test_client.get("/api/devices")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0
        assert data["devices"] == []

    async def test_list_devices_returns_discovered(
        self,
        test_client: AsyncClient,
        mock_bluetooth_manager: MagicMock,
    ) -> None:
        """GET /api/devices returns devices from BlueZ."""
        mock_bluetooth_manager.get_all_device_states = AsyncMock(
            return_value={
                "AA:BB:CC:DD:EE:FF": {
                    "name": "Test Speaker",
                    "paired": True,
                    "connected": False,
                    "trusted": False,
                    "rssi": -55,
                    "device_type": "audio",
                },
                "11:22:33:44:55:66": {
                    "name": "Test Keyboard",
                    "paired": False,
                    "connected": False,
                    "trusted": False,
                    "rssi": -70,
                    "device_type": "input",
                },
            }
        )

        response = await test_client.get("/api/devices")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        macs = {d["mac_address"] for d in data["devices"]}
        assert "AA:BB:CC:DD:EE:FF" in macs
        assert "11:22:33:44:55:66" in macs


class TestGetDevice:
    """Tests for GET /api/devices/{mac}."""

    async def test_get_device_returns_device(
        self,
        test_client: AsyncClient,
        mock_bluetooth_manager: MagicMock,
    ) -> None:
        """GET /api/devices/{mac} returns device from BlueZ."""
        mock_bluetooth_manager.get_device_state = AsyncMock(
            return_value={
                "name": "Test Speaker",
                "paired": True,
                "connected": False,
                "trusted": True,
                "rssi": -45,
                "device_type": "audio",
            }
        )

        response = await test_client.get("/api/devices/AA:BB:CC:DD:EE:FF")

        assert response.status_code == 200
        data = response.json()
        assert data["mac_address"] == "AA:BB:CC:DD:EE:FF"
        assert data["name"] == "Test Speaker"
        assert data["paired"] is True

    async def test_get_device_returns_404_for_unknown(
        self,
        test_client: AsyncClient,
        mock_bluetooth_manager: MagicMock,
    ) -> None:
        """GET /api/devices/{mac} returns 404 when device not in BlueZ."""
        mock_bluetooth_manager.get_device_state = AsyncMock(
            side_effect=DeviceNotFoundError("FF:FF:FF:FF:FF:FF")
        )

        response = await test_client.get("/api/devices/FF:FF:FF:FF:FF:FF")

        assert response.status_code == 404
        data = response.json()
        assert data["error"] == "device_not_found"


class TestPairDevice:
    """Tests for POST /api/devices/{mac}/pair."""

    async def test_pair_device_returns_200(
        self,
        test_client: AsyncClient,
        mock_bluetooth_manager: MagicMock,
    ) -> None:
        """POST /api/devices/{mac}/pair returns 200."""
        response = await test_client.post("/api/devices/AA:BB:CC:DD:EE:FF/pair")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "paired"
        assert data["mac_address"] == "AA:BB:CC:DD:EE:FF"
        mock_bluetooth_manager.pair_device.assert_awaited_once_with("AA:BB:CC:DD:EE:FF")

    async def test_pair_device_returns_409_when_already_paired(
        self,
        test_client: AsyncClient,
        mock_bluetooth_manager: MagicMock,
    ) -> None:
        """POST /api/devices/{mac}/pair returns 409 when already paired."""
        mock_bluetooth_manager.pair_device = AsyncMock(side_effect=AlreadyPairedError())

        response = await test_client.post("/api/devices/AA:BB:CC:DD:EE:FF/pair")

        assert response.status_code == 409
        data = response.json()
        assert data["error"] == "already_paired"


class TestConnectDevice:
    """Tests for POST /api/devices/{mac}/connect."""

    async def test_connect_device_returns_200(
        self,
        test_client: AsyncClient,
        mock_bluetooth_manager: MagicMock,
    ) -> None:
        """POST /api/devices/{mac}/connect returns 200."""
        response = await test_client.post("/api/devices/AA:BB:CC:DD:EE:FF/connect")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "connected"
        mock_bluetooth_manager.connect_device.assert_awaited_once_with("AA:BB:CC:DD:EE:FF")

    async def test_connect_device_returns_412_when_not_paired(
        self,
        test_client: AsyncClient,
        mock_bluetooth_manager: MagicMock,
    ) -> None:
        """POST /api/devices/{mac}/connect returns 412 when not paired."""
        mock_bluetooth_manager.connect_device = AsyncMock(side_effect=NotPairedError())

        response = await test_client.post("/api/devices/AA:BB:CC:DD:EE:FF/connect")

        assert response.status_code == 412
        data = response.json()
        assert data["error"] == "not_paired"


class TestDisconnectDevice:
    """Tests for POST /api/devices/{mac}/disconnect."""

    async def test_disconnect_device_returns_200(
        self,
        test_client: AsyncClient,
        mock_bluetooth_manager: MagicMock,
    ) -> None:
        """POST /api/devices/{mac}/disconnect returns 200."""
        response = await test_client.post("/api/devices/AA:BB:CC:DD:EE:FF/disconnect")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "disconnected"
        mock_bluetooth_manager.disconnect_device.assert_awaited_once_with("AA:BB:CC:DD:EE:FF")


class TestTrustUntrust:
    """Tests for POST /api/devices/{mac}/trust and /untrust."""

    async def test_trust_device(
        self,
        test_client: AsyncClient,
        mock_bluetooth_manager: MagicMock,
    ) -> None:
        """POST /api/devices/{mac}/trust returns 200."""
        response = await test_client.post("/api/devices/AA:BB:CC:DD:EE:FF/trust")

        assert response.status_code == 200
        data = response.json()
        assert data["mac_address"] == "AA:BB:CC:DD:EE:FF"
        mock_bluetooth_manager.trust_device.assert_awaited_once_with("AA:BB:CC:DD:EE:FF")

    async def test_untrust_device(
        self,
        test_client: AsyncClient,
        mock_bluetooth_manager: MagicMock,
    ) -> None:
        """POST /api/devices/{mac}/untrust returns 200."""
        response = await test_client.post("/api/devices/AA:BB:CC:DD:EE:FF/untrust")

        assert response.status_code == 200
        data = response.json()
        assert data["mac_address"] == "AA:BB:CC:DD:EE:FF"
        mock_bluetooth_manager.untrust_device.assert_awaited_once_with("AA:BB:CC:DD:EE:FF")


class TestRemoveDevice:
    """Tests for POST /api/devices/{mac}/remove."""

    async def test_remove_device(
        self,
        test_client: AsyncClient,
        mock_bluetooth_manager: MagicMock,
    ) -> None:
        """POST /api/devices/{mac}/remove returns 200."""
        response = await test_client.post("/api/devices/AA:BB:CC:DD:EE:FF/remove")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "removed"
        assert data["mac_address"] == "AA:BB:CC:DD:EE:FF"
        mock_bluetooth_manager.remove_device.assert_awaited_once_with("AA:BB:CC:DD:EE:FF")
