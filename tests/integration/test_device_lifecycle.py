"""Integration tests for full device lifecycle (T040)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from httpx import AsyncClient

    from bt_hub.services.device_store import DeviceStore


class TestDeviceLifecycle:
    """Test full device lifecycle: create -> get -> update -> delete."""

    async def test_full_device_lifecycle(
        self,
        test_client: AsyncClient,
        device_store: DeviceStore,
        mock_bluetooth_manager: MagicMock,
    ) -> None:
        """Create device in store, get via API, update, then delete."""
        mac = "AA:BB:CC:DD:EE:FF"

        # Step 1: Create device in store directly
        await device_store.upsert_device(mac, name="Lifecycle Device", device_type="audio")

        # Step 2: Verify device is retrievable via API
        response = await test_client.get(f"/api/devices/{mac}")
        assert response.status_code == 200
        data = response.json()
        assert data["mac_address"] == mac
        assert data["name"] == "Lifecycle Device"

        # Step 3: Update device via API
        response = await test_client.patch(
            f"/api/devices/{mac}",
            json={"alias": "My Speaker", "is_favorite": True, "notes": "Integration test"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["alias"] == "My Speaker"
        assert data["is_favorite"] is True
        assert data["notes"] == "Integration test"

        # Step 4: Verify update persisted
        response = await test_client.get(f"/api/devices/{mac}")
        assert response.status_code == 200
        data = response.json()
        assert data["alias"] == "My Speaker"
        assert data["is_favorite"] is True

        # Step 5: Device shows up in favorites filter
        response = await test_client.get("/api/devices?filter=favorites")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["devices"][0]["mac_address"] == mac

        # Step 6: Delete the device
        response = await test_client.delete(f"/api/devices/{mac}")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "deleted"

        # Step 7: Verify device is gone
        response = await test_client.get(f"/api/devices/{mac}")
        assert response.status_code == 404

    async def test_multiple_devices_lifecycle(
        self,
        test_client: AsyncClient,
        device_store: DeviceStore,
        mock_bluetooth_manager: MagicMock,
    ) -> None:
        """Test managing multiple devices concurrently."""
        devices = [
            ("11:22:33:44:55:66", "Device A"),
            ("AA:BB:CC:DD:EE:FF", "Device B"),
            ("77:88:99:AA:BB:CC", "Device C"),
        ]

        # Create all devices
        for mac, name in devices:
            await device_store.upsert_device(mac, name=name)

        # List all should return 3
        response = await test_client.get("/api/devices")
        assert response.status_code == 200
        assert response.json()["count"] == 3

        # Delete one
        response = await test_client.delete("/api/devices/11:22:33:44:55:66")
        assert response.status_code == 200

        # List should now return 2
        response = await test_client.get("/api/devices")
        assert response.status_code == 200
        assert response.json()["count"] == 2

        # The deleted device should be 404
        response = await test_client.get("/api/devices/11:22:33:44:55:66")
        assert response.status_code == 404
