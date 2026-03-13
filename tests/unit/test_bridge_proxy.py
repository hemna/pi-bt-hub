"""Tests for the BridgeProxy service."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from bt_hub.services.bridge_proxy import BridgeProxy


class TestBridgeProxyInit:
    def test_strips_trailing_slash(self) -> None:
        proxy = BridgeProxy("http://localhost:8081/")
        assert proxy._bridge_url == "http://localhost:8081"


class TestBridgeProxyGetStatus:
    @pytest.mark.asyncio
    async def test_returns_dict_on_success(self) -> None:
        proxy = BridgeProxy("http://localhost:8081")
        await proxy.startup()

        status_data = {
            "ble": {"state": "scanning"},
            "classic": {"state": "connected", "target_address": "AA:BB:CC:DD:EE:FF"},
            "tcp_kiss": {"enabled": True, "client_count": 1, "max_clients": 5, "listening": True},
            "uptime_seconds": 3600.5,
            "version": "1.0.0",
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = status_data

        with patch.object(proxy._client, "get", new_callable=AsyncMock, return_value=mock_response):
            result = await proxy.get_status()

        assert result == status_data
        await proxy.shutdown()

    @pytest.mark.asyncio
    async def test_returns_none_on_connect_error(self) -> None:
        proxy = BridgeProxy("http://localhost:8081")
        await proxy.startup()

        with patch.object(
            proxy._client, "get", new_callable=AsyncMock,
            side_effect=httpx.ConnectError("refused"),
        ):
            result = await proxy.get_status()

        assert result is None
        await proxy.shutdown()

    @pytest.mark.asyncio
    async def test_returns_none_on_timeout(self) -> None:
        proxy = BridgeProxy("http://localhost:8081")
        await proxy.startup()

        with patch.object(
            proxy._client, "get", new_callable=AsyncMock,
            side_effect=httpx.TimeoutException("timed out"),
        ):
            result = await proxy.get_status()

        assert result is None
        await proxy.shutdown()

    @pytest.mark.asyncio
    async def test_returns_none_on_non_200(self) -> None:
        proxy = BridgeProxy("http://localhost:8081")
        await proxy.startup()

        mock_response = MagicMock()
        mock_response.status_code = 500

        with patch.object(proxy._client, "get", new_callable=AsyncMock, return_value=mock_response):
            result = await proxy.get_status()

        assert result is None
        await proxy.shutdown()


class TestBridgeProxyGetStats:
    @pytest.mark.asyncio
    async def test_returns_stats_on_success(self) -> None:
        proxy = BridgeProxy("http://localhost:8081")
        await proxy.startup()

        stats = {"packets_tx": 100, "bytes_tx": 5000, "errors": 0}
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = stats

        with patch.object(proxy._client, "get", new_callable=AsyncMock, return_value=mock_response):
            result = await proxy.get_stats()

        assert result == stats
        await proxy.shutdown()


class TestBridgeProxySettings:
    @pytest.mark.asyncio
    async def test_get_settings(self) -> None:
        proxy = BridgeProxy("http://localhost:8081")
        await proxy.startup()

        settings = {"device_name": "PiBridge", "web_port": 8081}
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = settings

        with patch.object(proxy._client, "get", new_callable=AsyncMock, return_value=mock_response):
            result = await proxy.get_settings()

        assert result == settings
        await proxy.shutdown()

    @pytest.mark.asyncio
    async def test_update_settings(self) -> None:
        proxy = BridgeProxy("http://localhost:8081")
        await proxy.startup()

        response_data = {"status": "saved", "restart_required": False}
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = response_data

        with patch.object(proxy._client, "post", new_callable=AsyncMock, return_value=mock_response):
            result = await proxy.update_settings({"device_name": "NewName"})

        assert result == response_data
        await proxy.shutdown()


class TestBridgeProxyTncHistory:
    @pytest.mark.asyncio
    async def test_get_tnc_history(self) -> None:
        proxy = BridgeProxy("http://localhost:8081")
        await proxy.startup()

        history = {"devices": [{"address": "AA:BB:CC:DD:EE:FF"}], "count": 1}
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = history

        with patch.object(proxy._client, "get", new_callable=AsyncMock, return_value=mock_response):
            result = await proxy.get_tnc_history()

        assert result == history
        await proxy.shutdown()

    @pytest.mark.asyncio
    async def test_select_tnc(self) -> None:
        proxy = BridgeProxy("http://localhost:8081")
        await proxy.startup()

        response_data = {"success": True, "message": "TNC selected"}
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = response_data

        with patch.object(proxy._client, "post", new_callable=AsyncMock, return_value=mock_response):
            result = await proxy.select_tnc("AA:BB:CC:DD:EE:FF")

        assert result == response_data
        await proxy.shutdown()
