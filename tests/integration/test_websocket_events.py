"""Integration tests for WebSocket events (T023)."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest

from bt_hub.services.event_bus import Event, EventBus

if TYPE_CHECKING:
    from unittest.mock import MagicMock
    from starlette.applications import Starlette
    from starlette.testclient import TestClient as SyncTestClient


@pytest.fixture
def ws_client(
    device_store,
    event_bus: EventBus,
    mock_bluetooth_manager: MagicMock,
):
    """Yield a Starlette TestClient for WebSocket testing.

    The lifecycle patch must stay active through TestClient.__enter__/exit,
    so we yield from inside the patch context.
    """
    from pathlib import Path
    from starlette.templating import Jinja2Templates
    from starlette.testclient import TestClient

    from bt_hub.config import Settings
    from bt_hub.lifecycle import BtHubServices
    from bt_hub.main import create_app
    from bt_hub.services.log_handler import SSELogHandler

    template_dir = Path(__file__).parent.parent.parent / "backend" / "src" / "bt_hub" / "templates"
    templates = Jinja2Templates(directory=str(template_dir))

    mock_services = BtHubServices(
        settings=Settings(),
        device_store=device_store,
        event_bus=event_bus,
        bluez_mgr=mock_bluetooth_manager,
        log_handler=SSELogHandler(),
    )

    with patch("bt_hub.main.startup_services", AsyncMock(return_value=mock_services)), \
         patch("bt_hub.main.create_templates", return_value=templates), \
         patch("bt_hub.main.shutdown_services", AsyncMock()):
        app = create_app()
        with TestClient(app) as client:
            yield client


class TestWebSocketConnection:
    """Tests for WebSocket endpoint /ws."""

    def test_client_connects_successfully(self, ws_client, event_bus: EventBus) -> None:
        """Client connects to /ws successfully."""
        with ws_client.websocket_connect("/ws"):
            assert event_bus.subscriber_count >= 1

    def test_client_receives_events(self, ws_client, event_bus: EventBus) -> None:
        """Client receives events published to event_bus."""
        import asyncio

        with ws_client.websocket_connect("/ws") as ws:
            asyncio.get_event_loop().run_until_complete(
                event_bus.publish(
                    Event("device_discovered", {"mac_address": "AA:BB:CC:DD:EE:FF"})
                )
            )
            data = ws.receive_json()
            assert data["event"] == "device_discovered"
            assert data["data"]["mac_address"] == "AA:BB:CC:DD:EE:FF"
            assert "timestamp" in data

    def test_client_disconnects_cleanly(self, ws_client, event_bus: EventBus) -> None:
        """Client disconnects cleanly and is unsubscribed."""
        with ws_client.websocket_connect("/ws"):
            initial_count = event_bus.subscriber_count
            assert initial_count >= 1

        assert event_bus.subscriber_count < initial_count
