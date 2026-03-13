"""Tests for the BtBridgeClient service."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from bt_hub.services.bt_bridge_client import BtBridgeClient


class TestBtBridgeClientInit:
    """Test BtBridgeClient initialization."""

    def test_not_configured_when_url_is_none(self) -> None:
        client = BtBridgeClient(None)
        assert client.is_configured is False

    def test_configured_when_url_provided(self) -> None:
        client = BtBridgeClient("http://localhost:8081")
        assert client.is_configured is True

    def test_strips_trailing_slash(self) -> None:
        client = BtBridgeClient("http://localhost:8081/")
        assert client._base_url == "http://localhost:8081"


class TestBtBridgeClientGetStatus:
    """Test the get_status method."""

    @pytest.mark.asyncio
    async def test_returns_none_when_not_configured(self) -> None:
        client = BtBridgeClient(None)
        result = await client.get_status()
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_dict_on_success(self) -> None:
        status_data = {
            "ble": {"state": "scanning"},
            "classic": {"state": "connected", "target_address": "AA:BB:CC:DD:EE:FF"},
            "tcp_kiss": {"enabled": True, "client_count": 1, "max_clients": 5, "listening": True},
            "uptime_seconds": 3600.5,
            "version": "1.0.0",
        }

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json = lambda: status_data  # sync method, not async

        with patch("bt_hub.services.bt_bridge_client.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            client = BtBridgeClient("http://localhost:8081")
            result = await client.get_status()

        assert result == status_data
        mock_client.get.assert_called_once_with("http://localhost:8081/api/status")

    @pytest.mark.asyncio
    async def test_returns_none_on_non_200(self) -> None:
        mock_response = AsyncMock()
        mock_response.status_code = 500

        with patch("bt_hub.services.bt_bridge_client.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            client = BtBridgeClient("http://localhost:8081")
            result = await client.get_status()

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_timeout(self) -> None:
        with patch("bt_hub.services.bt_bridge_client.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.side_effect = httpx.TimeoutException("timed out")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            client = BtBridgeClient("http://localhost:8081")
            result = await client.get_status()

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_connect_error(self) -> None:
        with patch("bt_hub.services.bt_bridge_client.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.side_effect = httpx.ConnectError("connection refused")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            client = BtBridgeClient("http://localhost:8081")
            result = await client.get_status()

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_unexpected_error(self) -> None:
        with patch("bt_hub.services.bt_bridge_client.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.side_effect = RuntimeError("unexpected")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            client = BtBridgeClient("http://localhost:8081")
            result = await client.get_status()

        assert result is None


class TestBtBridgeClientTimeout:
    """Test custom timeout configuration."""

    def test_default_timeout(self) -> None:
        client = BtBridgeClient("http://localhost:8081")
        assert client._timeout == 2.0

    def test_custom_timeout(self) -> None:
        client = BtBridgeClient("http://localhost:8081", timeout=5.0)
        assert client._timeout == 5.0
