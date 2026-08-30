"""Test that bridge routes and nav items are conditional on bridge_enabled."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend" / "src"))

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


@pytest_asyncio.fixture
async def client_bridge_disabled() -> AsyncIterator[AsyncClient]:
    """Client with bridge_enabled=false (default)."""
    os.environ.pop("BT_HUB_BRIDGE_ENABLED", None)

    from bt_hub.config import get_settings
    get_settings.cache_clear()

    from starlette.templating import Jinja2Templates

    from bt_hub.deps import set_templates

    template_dir = (
        Path(__file__).parent.parent.parent / "backend" / "src" / "bt_hub" / "templates"
    )
    set_templates(Jinja2Templates(directory=str(template_dir)))

    from bt_hub.main import create_app
    app = create_app()

    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    get_settings.cache_clear()


@pytest_asyncio.fixture
async def client_bridge_enabled() -> AsyncIterator[AsyncClient]:
    """Client with bridge_enabled=true."""
    os.environ["BT_HUB_BRIDGE_ENABLED"] = "true"

    from bt_hub.config import get_settings
    get_settings.cache_clear()

    from starlette.templating import Jinja2Templates

    from bt_hub.deps import set_bridge_proxy, set_templates

    template_dir = (
        Path(__file__).parent.parent.parent / "backend" / "src" / "bt_hub" / "templates"
    )
    set_templates(Jinja2Templates(directory=str(template_dir)))

    mock_proxy = MagicMock()
    mock_proxy.get_status = AsyncMock(
        return_value={"ble": {"state": "idle"}, "classic": {"state": "idle"}, "uptime_seconds": 100}
    )
    mock_proxy.get_stats = AsyncMock(return_value={"packets_tx": 0})
    set_bridge_proxy(mock_proxy)

    try:
        from bt_hub.main import create_app
        app = create_app()

        transport = ASGITransport(app=app)  # type: ignore[arg-type]
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    finally:
        del os.environ["BT_HUB_BRIDGE_ENABLED"]
        get_settings.cache_clear()


class TestBridgeDisabled:
    async def test_bridge_api_returns_404(self, client_bridge_disabled: AsyncClient) -> None:
        resp = await client_bridge_disabled.get("/api/bridge/status")
        assert resp.status_code == 404

    async def test_bridge_page_returns_404(self, client_bridge_disabled: AsyncClient) -> None:
        resp = await client_bridge_disabled.get("/bridge")
        assert resp.status_code == 404


class TestBridgeEnabled:
    async def test_bridge_api_available(self, client_bridge_enabled: AsyncClient) -> None:
        resp = await client_bridge_enabled.get("/api/bridge/status")
        assert resp.status_code == 200

    async def test_bridge_page_available(self, client_bridge_enabled: AsyncClient) -> None:
        resp = await client_bridge_enabled.get("/bridge")
        assert resp.status_code == 200
