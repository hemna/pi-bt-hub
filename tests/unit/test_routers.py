"""Tests for bt_hub.routers aggregator module."""

from __future__ import annotations

from unittest.mock import MagicMock

from fastapi.templating import Jinja2Templates

from bt_hub.lifecycle import ServiceContainer
from bt_hub.routers import create_api_routers, create_page_routers, create_ws_router


class TestCreateApiRouters:
    """Tests for the API router aggregator."""

    def test_returns_api_router(self) -> None:
        container = ServiceContainer()
        router = create_api_routers(container)
        # Should have routes from all modules (adapter, devices, bridge, settings, logs)
        paths = [r.path for r in router.routes]
        assert "/api/adapter" in paths
        assert "/api/devices" in paths
        assert "/api/bridge/status" in paths
        assert "/api/settings" in paths
        assert "/api/logs/stream" in paths

    def test_has_many_routes(self) -> None:
        container = ServiceContainer()
        router = create_api_routers(container)
        # Should have a substantial number of routes (API has 30+ endpoints)
        assert len(router.routes) > 20


class TestCreatePageRouters:
    """Tests for the page router aggregator."""

    def test_returns_page_router(self, tmp_path) -> None:
        container = ServiceContainer()
        # Create a minimal templates object
        tpl_dir = tmp_path / "templates"
        tpl_dir.mkdir()
        templates = MagicMock(spec=Jinja2Templates)
        router = create_page_routers(container, templates)
        paths = [r.path for r in router.routes]
        assert "/" in paths
        assert "/devices" in paths
        assert "/settings" in paths
        assert "/logs" in paths
        assert "/bridge" in paths


class TestCreateWsRouter:
    """Tests for the WebSocket router factory."""

    def test_default_path(self) -> None:
        container = ServiceContainer()
        router = create_ws_router(container)
        paths = [r.path for r in router.routes]
        assert "/ws" in paths

    def test_custom_path(self) -> None:
        container = ServiceContainer()
        router = create_ws_router(container, path="/ws/bluetooth")
        paths = [r.path for r in router.routes]
        assert "/ws/bluetooth" in paths
