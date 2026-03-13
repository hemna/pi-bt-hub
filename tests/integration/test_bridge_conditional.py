"""Test that bridge routes and nav items are conditional on bridge_enabled."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


@pytest_asyncio.fixture
async def client_bridge_disabled() -> AsyncIterator[AsyncClient]:
    """Client with bridge_enabled=false (default)."""
    os.environ.pop("BT_HUB_BRIDGE_ENABLED", None)

    from bt_hub.main import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture
async def client_bridge_enabled() -> AsyncIterator[AsyncClient]:
    """Client with bridge_enabled=true."""
    os.environ["BT_HUB_BRIDGE_ENABLED"] = "true"
    try:
        from bt_hub import deps
        from bt_hub.main import create_app

        app = create_app()

        # Mock the bridge proxy dependency
        mock_proxy = MagicMock()
        mock_proxy.get_status = AsyncMock(return_value={"ble": {"state": "idle"}})
        mock_proxy.get_stats = AsyncMock(return_value={"packets_tx": 0})
        app.dependency_overrides[deps.get_bridge_proxy] = lambda: mock_proxy

        # Mock the templates dependency so we don't need lifespan
        mock_templates = MagicMock()
        mock_templates.TemplateResponse = MagicMock(
            return_value=MagicMock(status_code=200, body=b"ok"),
        )
        app.dependency_overrides[deps.get_templates] = lambda: mock_templates

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    finally:
        del os.environ["BT_HUB_BRIDGE_ENABLED"]


class TestBridgeDisabled:
    async def test_bridge_api_returns_404(
        self, client_bridge_disabled: AsyncClient
    ) -> None:
        resp = await client_bridge_disabled.get("/api/bridge/status")
        assert resp.status_code == 404

    async def test_bridge_page_returns_404(
        self, client_bridge_disabled: AsyncClient
    ) -> None:
        resp = await client_bridge_disabled.get("/bridge")
        assert resp.status_code == 404


class TestBridgeEnabled:
    async def test_bridge_api_available(
        self, client_bridge_enabled: AsyncClient
    ) -> None:
        resp = await client_bridge_enabled.get("/api/bridge/status")
        assert resp.status_code == 200

    async def test_bridge_page_available(
        self, client_bridge_enabled: AsyncClient
    ) -> None:
        resp = await client_bridge_enabled.get("/bridge")
        assert resp.status_code == 200
