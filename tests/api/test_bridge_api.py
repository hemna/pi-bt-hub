"""Tests for bridge proxy API routes."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from bt_hub.services.bridge_proxy import BridgeProxy

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


def _make_mock_proxy() -> MagicMock:
    """Create a mock BridgeProxy."""
    proxy = MagicMock(spec=BridgeProxy)
    proxy.get_status = AsyncMock(return_value={
        "ble": {"state": "idle"},
        "classic": {"state": "idle"},
        "uptime_seconds": 100,
    })
    proxy.get_stats = AsyncMock(return_value={"packets_tx": 0, "errors": 0})
    proxy.get_settings = AsyncMock(return_value={"device_name": "PiBridge"})
    proxy.update_settings = AsyncMock(return_value={"status": "saved"})
    proxy.restart = AsyncMock(return_value={"status": "restarting"})
    proxy.get_tnc_history = AsyncMock(return_value={"devices": [], "count": 0})
    proxy.add_tnc = AsyncMock(return_value={"success": True})
    proxy.get_tnc = AsyncMock(return_value={"address": "AA:BB:CC:DD:EE:FF"})
    proxy.update_tnc = AsyncMock(return_value={"success": True})
    proxy.delete_tnc = AsyncMock(return_value={"success": True})
    proxy.select_tnc = AsyncMock(return_value={"success": True})
    proxy.connect_tnc = AsyncMock(return_value={"success": True})
    proxy.get_recent_logs = AsyncMock(return_value={"entries": []})
    return proxy


@pytest_asyncio.fixture
async def bridge_client() -> AsyncIterator[tuple[AsyncClient, MagicMock]]:
    """Create a test client with bridge_enabled=True and mocked proxy."""
    import os
    os.environ["BT_HUB_BRIDGE_ENABLED"] = "true"

    try:
        from bt_hub.main import create_app
        from bt_hub import deps

        app = create_app()
        mock_proxy = _make_mock_proxy()
        app.dependency_overrides[deps.get_bridge_proxy] = lambda: mock_proxy

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, mock_proxy
    finally:
        del os.environ["BT_HUB_BRIDGE_ENABLED"]


class TestBridgeStatusAPI:
    async def test_get_status(self, bridge_client: tuple) -> None:
        client, mock_proxy = bridge_client
        resp = await client.get("/api/bridge/status")
        assert resp.status_code == 200
        assert "ble" in resp.json()
        mock_proxy.get_status.assert_awaited_once()

    async def test_get_status_offline(self, bridge_client: tuple) -> None:
        client, mock_proxy = bridge_client
        mock_proxy.get_status = AsyncMock(return_value=None)
        resp = await client.get("/api/bridge/status")
        assert resp.status_code == 200
        assert resp.json()["offline"] is True


class TestBridgeStatsAPI:
    async def test_get_stats(self, bridge_client: tuple) -> None:
        client, mock_proxy = bridge_client
        resp = await client.get("/api/bridge/stats")
        assert resp.status_code == 200
        mock_proxy.get_stats.assert_awaited_once()


class TestBridgeSettingsAPI:
    async def test_get_settings(self, bridge_client: tuple) -> None:
        client, mock_proxy = bridge_client
        resp = await client.get("/api/bridge/settings")
        assert resp.status_code == 200

    async def test_update_settings(self, bridge_client: tuple) -> None:
        client, mock_proxy = bridge_client
        resp = await client.post("/api/bridge/settings", json={"device_name": "NewName"})
        assert resp.status_code == 200


class TestBridgeLogsAPI:
    async def test_get_recent_logs(self, bridge_client: tuple) -> None:
        client, mock_proxy = bridge_client
        resp = await client.get("/api/bridge/logs/recent")
        assert resp.status_code == 200
        mock_proxy.get_recent_logs.assert_awaited_once()


class TestBridgeRestartAPI:
    async def test_restart(self, bridge_client: tuple) -> None:
        client, mock_proxy = bridge_client
        resp = await client.post("/api/bridge/restart")
        assert resp.status_code == 200
        mock_proxy.restart.assert_awaited_once()


class TestBridgeTncAPI:
    async def test_get_tnc_history(self, bridge_client: tuple) -> None:
        client, mock_proxy = bridge_client
        resp = await client.get("/api/bridge/tnc")
        assert resp.status_code == 200
        mock_proxy.get_tnc_history.assert_awaited_once()

    async def test_add_tnc(self, bridge_client: tuple) -> None:
        client, mock_proxy = bridge_client
        resp = await client.post("/api/bridge/tnc", json={"address": "11:22:33:44:55:66"})
        assert resp.status_code == 200
        mock_proxy.add_tnc.assert_awaited_once()

    async def test_get_tnc(self, bridge_client: tuple) -> None:
        client, mock_proxy = bridge_client
        resp = await client.get("/api/bridge/tnc/AA:BB:CC:DD:EE:FF")
        assert resp.status_code == 200
        mock_proxy.get_tnc.assert_awaited_once_with("AA:BB:CC:DD:EE:FF")

    async def test_update_tnc(self, bridge_client: tuple) -> None:
        client, mock_proxy = bridge_client
        resp = await client.put(
            "/api/bridge/tnc/AA:BB:CC:DD:EE:FF",
            json={"name": "Updated"},
        )
        assert resp.status_code == 200
        mock_proxy.update_tnc.assert_awaited_once_with("AA:BB:CC:DD:EE:FF", {"name": "Updated"})

    async def test_delete_tnc(self, bridge_client: tuple) -> None:
        client, mock_proxy = bridge_client
        resp = await client.delete("/api/bridge/tnc/AA:BB:CC:DD:EE:FF")
        assert resp.status_code == 200
        mock_proxy.delete_tnc.assert_awaited_once_with("AA:BB:CC:DD:EE:FF")

    async def test_select_tnc(self, bridge_client: tuple) -> None:
        client, mock_proxy = bridge_client
        resp = await client.post("/api/bridge/tnc/AA:BB:CC:DD:EE:FF/select")
        assert resp.status_code == 200
        mock_proxy.select_tnc.assert_awaited_once_with("AA:BB:CC:DD:EE:FF")

    async def test_connect_tnc(self, bridge_client: tuple) -> None:
        client, mock_proxy = bridge_client
        resp = await client.post("/api/bridge/tnc/AA:BB:CC:DD:EE:FF/connect")
        assert resp.status_code == 200
        mock_proxy.connect_tnc.assert_awaited_once_with("AA:BB:CC:DD:EE:FF")
