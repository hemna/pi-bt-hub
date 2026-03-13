"""API tests for adapter and scan endpoints (T021, T022)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

from bt_hub.api import AdapterUnavailableError, AlreadyScanningError
from bt_hub.models.device import AdapterState

if TYPE_CHECKING:
    from httpx import AsyncClient


class TestGetAdapter:
    """Tests for GET /api/adapter."""

    async def test_get_adapter_returns_200(
        self, test_client: AsyncClient, mock_bluetooth_manager: MagicMock
    ) -> None:
        """GET /api/adapter returns 200 with adapter state."""
        response = await test_client.get("/api/adapter")

        assert response.status_code == 200
        data = response.json()
        assert data["address"] == "AA:BB:CC:DD:EE:FF"
        assert data["name"] == "hci0"
        assert data["powered"] is True
        assert data["discovering"] is False
        assert data["discoverable"] is False

    async def test_get_adapter_returns_503_when_no_adapter(
        self, test_client: AsyncClient, mock_bluetooth_manager: MagicMock
    ) -> None:
        """GET /api/adapter returns 503 when no adapter available."""
        mock_bluetooth_manager.get_adapter_state = AsyncMock(side_effect=AdapterUnavailableError())

        response = await test_client.get("/api/adapter")

        assert response.status_code == 503
        data = response.json()
        assert data["error"] == "no_adapter"


class TestSetAdapterPower:
    """Tests for POST /api/adapter/power."""

    async def test_toggle_power(
        self, test_client: AsyncClient, mock_bluetooth_manager: MagicMock
    ) -> None:
        """POST /api/adapter/power toggles adapter power."""
        mock_bluetooth_manager.set_powered = AsyncMock(
            return_value=AdapterState(
                address="AA:BB:CC:DD:EE:FF",
                name="hci0",
                powered=False,
                discovering=False,
                discoverable=False,
            )
        )

        response = await test_client.post("/api/adapter/power", json={"powered": False})

        assert response.status_code == 200
        data = response.json()
        assert data["powered"] is False
        mock_bluetooth_manager.set_powered.assert_awaited_once_with(False)


class TestScanStart:
    """Tests for POST /api/scan/start."""

    async def test_start_scan_returns_200(
        self, test_client: AsyncClient, mock_bluetooth_manager: MagicMock
    ) -> None:
        """POST /api/scan/start returns 200 with scanning status."""
        response = await test_client.post("/api/scan/start")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "scanning"
        assert data["duration_seconds"] == 10
        mock_bluetooth_manager.start_discovery.assert_awaited_once()

    async def test_start_scan_returns_409_when_already_scanning(
        self, test_client: AsyncClient, mock_bluetooth_manager: MagicMock
    ) -> None:
        """POST /api/scan/start returns 409 when already scanning."""
        mock_bluetooth_manager.start_discovery = AsyncMock(side_effect=AlreadyScanningError())

        response = await test_client.post("/api/scan/start")

        assert response.status_code == 409
        data = response.json()
        assert data["error"] == "already_scanning"


class TestScanStop:
    """Tests for POST /api/scan/stop."""

    async def test_stop_scan_returns_200(
        self, test_client: AsyncClient, mock_bluetooth_manager: MagicMock
    ) -> None:
        """POST /api/scan/stop returns 200."""
        response = await test_client.post("/api/scan/stop")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "stopped"
        mock_bluetooth_manager.stop_discovery.assert_awaited_once()
