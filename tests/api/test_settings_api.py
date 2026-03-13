"""API tests for settings endpoints (T053)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from httpx import AsyncClient

    from bt_hub.services.device_store import DeviceStore


class TestGetSettings:
    """Tests for GET /api/settings."""

    async def test_get_settings_returns_defaults(
        self, test_client: AsyncClient, device_store: DeviceStore
    ) -> None:
        """GET /api/settings returns default settings."""
        response = await test_client.get("/api/settings")

        assert response.status_code == 200
        data = response.json()
        assert data["theme"] == "light"
        assert data["auto_connect_favorites"] is False
        assert data["scan_duration_seconds"] == 10
        assert data["adapter_name"] is None


class TestUpdateSettings:
    """Tests for PATCH /api/settings."""

    async def test_update_theme(self, test_client: AsyncClient, device_store: DeviceStore) -> None:
        """PATCH /api/settings updates theme."""
        response = await test_client.patch("/api/settings", json={"theme": "dark"})

        assert response.status_code == 200
        data = response.json()
        assert data["theme"] == "dark"

    async def test_update_scan_duration_valid(
        self, test_client: AsyncClient, device_store: DeviceStore
    ) -> None:
        """PATCH /api/settings updates scan_duration within valid range."""
        response = await test_client.patch("/api/settings", json={"scan_duration_seconds": 30})

        assert response.status_code == 200
        data = response.json()
        assert data["scan_duration_seconds"] == 30

    async def test_update_scan_duration_below_min_returns_422(
        self, test_client: AsyncClient, device_store: DeviceStore
    ) -> None:
        """PATCH /api/settings returns 422 for scan_duration < 5."""
        response = await test_client.patch("/api/settings", json={"scan_duration_seconds": 2})

        assert response.status_code == 422

    async def test_update_scan_duration_above_max_returns_422(
        self, test_client: AsyncClient, device_store: DeviceStore
    ) -> None:
        """PATCH /api/settings returns 422 for scan_duration > 60."""
        response = await test_client.patch("/api/settings", json={"scan_duration_seconds": 120})

        assert response.status_code == 422

    async def test_update_invalid_theme_returns_422(
        self, test_client: AsyncClient, device_store: DeviceStore
    ) -> None:
        """PATCH /api/settings returns 422 for invalid theme value."""
        response = await test_client.patch("/api/settings", json={"theme": "neon"})

        assert response.status_code == 422
