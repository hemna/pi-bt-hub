"""Integration tests for WebSocket events (T023)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest_asyncio

from bt_hub.services.event_bus import Event, EventBus

if TYPE_CHECKING:
    from unittest.mock import MagicMock


@pytest_asyncio.fixture
async def ws_app(
    device_store,
    event_bus: EventBus,
    mock_bluetooth_manager: MagicMock,
):
    """Create a FastAPI app configured for WebSocket testing."""
    from bt_hub.api.adapter import get_bluetooth_manager
    from bt_hub.main import create_app, get_device_store, get_event_bus

    app = create_app()
    app.dependency_overrides[get_device_store] = lambda: device_store
    app.dependency_overrides[get_event_bus] = lambda: event_bus
    app.dependency_overrides[get_bluetooth_manager] = lambda: mock_bluetooth_manager
    return app


class TestWebSocketConnection:
    """Tests for WebSocket endpoint /ws."""

    async def test_client_connects_successfully(self, ws_app, event_bus: EventBus) -> None:
        """Client connects to /ws successfully."""
        from starlette.testclient import TestClient

        with TestClient(ws_app) as client, client.websocket_connect("/ws"):
            # Connection succeeded if we get here
            assert event_bus.subscriber_count >= 1

    async def test_client_receives_events(self, ws_app, event_bus: EventBus) -> None:
        """Client receives events published to event_bus."""
        from starlette.testclient import TestClient

        with TestClient(ws_app) as client, client.websocket_connect("/ws") as ws:
            # Publish an event
            await event_bus.publish(
                Event("device_discovered", {"mac_address": "AA:BB:CC:DD:EE:FF"})
            )

            # Receive the event
            data = ws.receive_json()
            assert data["event"] == "device_discovered"
            assert data["data"]["mac_address"] == "AA:BB:CC:DD:EE:FF"
            assert "timestamp" in data

    async def test_client_disconnects_cleanly(self, ws_app, event_bus: EventBus) -> None:
        """Client disconnects cleanly and is unsubscribed."""
        from starlette.testclient import TestClient

        with TestClient(ws_app) as client:
            with client.websocket_connect("/ws"):
                initial_count = event_bus.subscriber_count
                assert initial_count >= 1

            # After disconnect, subscriber count should decrease
            # Allow brief moment for cleanup
            assert event_bus.subscriber_count < initial_count
