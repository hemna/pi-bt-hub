"""API tests for device endpoints (T039, T048)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest_asyncio

from bt_hub.api import (
    AlreadyPairedError,
    NotPairedError,
)

if TYPE_CHECKING:
    from httpx import AsyncClient

    from bt_hub.services.device_store import DeviceStore


@pytest_asyncio.fixture
async def seeded_store(device_store: DeviceStore) -> DeviceStore:
    """Seed the device store with test data."""
    await device_store.upsert_device("AA:BB:CC:DD:EE:FF", name="Test Speaker", device_type="audio")
    await device_store.upsert_device("11:22:33:44:55:66", name="Test Keyboard", device_type="input")
    await device_store.upsert_device(
        "77:88:99:AA:BB:CC", name="Favorite Phone", device_type="phone"
    )
    await device_store.update_device("77:88:99:AA:BB:CC", is_favorite=True)
    return device_store


class TestListDevices:
    """Tests for GET /api/devices."""

    async def test_list_devices_returns_device_list(
        self,
        test_client: AsyncClient,
        mock_bluetooth_manager: MagicMock,
        seeded_store: DeviceStore,
    ) -> None:
        """GET /api/devices returns all devices."""
        response = await test_client.get("/api/devices")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 3
        assert len(data["devices"]) == 3

    async def test_list_devices_filter_favorites(
        self,
        test_client: AsyncClient,
        mock_bluetooth_manager: MagicMock,
        seeded_store: DeviceStore,
    ) -> None:
        """GET /api/devices?filter=favorites returns only favorites."""
        response = await test_client.get("/api/devices?filter=favorites")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["devices"][0]["mac_address"] == "77:88:99:AA:BB:CC"


class TestGetDevice:
    """Tests for GET /api/devices/{mac}."""

    async def test_get_device_returns_device(
        self,
        test_client: AsyncClient,
        mock_bluetooth_manager: MagicMock,
        seeded_store: DeviceStore,
    ) -> None:
        """GET /api/devices/{mac} returns the device."""
        response = await test_client.get("/api/devices/AA:BB:CC:DD:EE:FF")

        assert response.status_code == 200
        data = response.json()
        assert data["mac_address"] == "AA:BB:CC:DD:EE:FF"
        assert data["name"] == "Test Speaker"

    async def test_get_device_returns_404_for_unknown(
        self,
        test_client: AsyncClient,
        mock_bluetooth_manager: MagicMock,
        seeded_store: DeviceStore,
    ) -> None:
        """GET /api/devices/{mac} returns 404 for unknown device."""
        response = await test_client.get("/api/devices/FF:FF:FF:FF:FF:FF")

        assert response.status_code == 404
        data = response.json()
        assert data["error"] == "device_not_found"


class TestUpdateDevice:
    """Tests for PATCH /api/devices/{mac}."""

    async def test_update_alias(
        self,
        test_client: AsyncClient,
        mock_bluetooth_manager: MagicMock,
        seeded_store: DeviceStore,
    ) -> None:
        """PATCH /api/devices/{mac} updates alias."""
        response = await test_client.patch(
            "/api/devices/AA:BB:CC:DD:EE:FF",
            json={"alias": "Living Room Speaker"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["alias"] == "Living Room Speaker"

    async def test_update_alias_too_long_returns_422(
        self,
        test_client: AsyncClient,
        mock_bluetooth_manager: MagicMock,
        seeded_store: DeviceStore,
    ) -> None:
        """PATCH /api/devices/{mac} returns 422 for alias > 64 chars."""
        response = await test_client.patch(
            "/api/devices/AA:BB:CC:DD:EE:FF",
            json={"alias": "x" * 65},
        )

        assert response.status_code == 422


class TestDeleteDevice:
    """Tests for DELETE /api/devices/{mac}."""

    async def test_delete_device(
        self,
        test_client: AsyncClient,
        mock_bluetooth_manager: MagicMock,
        seeded_store: DeviceStore,
    ) -> None:
        """DELETE /api/devices/{mac} removes device."""
        response = await test_client.delete("/api/devices/AA:BB:CC:DD:EE:FF")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "deleted"
        assert data["mac_address"] == "AA:BB:CC:DD:EE:FF"

    async def test_delete_device_returns_404_for_unknown(
        self,
        test_client: AsyncClient,
        mock_bluetooth_manager: MagicMock,
        seeded_store: DeviceStore,
    ) -> None:
        """DELETE /api/devices/{mac} returns 404 for unknown device."""
        response = await test_client.delete("/api/devices/FF:FF:FF:FF:FF:FF")

        assert response.status_code == 404


class TestPairDevice:
    """Tests for POST /api/devices/{mac}/pair."""

    async def test_pair_device_returns_200(
        self,
        test_client: AsyncClient,
        mock_bluetooth_manager: MagicMock,
        seeded_store: DeviceStore,
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
        seeded_store: DeviceStore,
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
        seeded_store: DeviceStore,
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
        seeded_store: DeviceStore,
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
        seeded_store: DeviceStore,
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
        seeded_store: DeviceStore,
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
        seeded_store: DeviceStore,
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
        seeded_store: DeviceStore,
    ) -> None:
        """POST /api/devices/{mac}/remove returns 200."""
        response = await test_client.post("/api/devices/AA:BB:CC:DD:EE:FF/remove")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "removed"
        assert data["mac_address"] == "AA:BB:CC:DD:EE:FF"
        mock_bluetooth_manager.remove_device.assert_awaited_once_with("AA:BB:CC:DD:EE:FF")
