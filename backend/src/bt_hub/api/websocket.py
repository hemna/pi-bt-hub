"""WebSocket endpoint for real-time Bluetooth events."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from bt_hub.deps import get_event_bus
from bt_hub.services.event_bus import Event, EventBus  # noqa: TC001

logger = logging.getLogger(__name__)

router = APIRouter()


def _event_to_html(event: Event) -> str:
    """Convert an event to an HTML partial for HTMX clients.

    Returns a simple HTML snippet that HTMX can use for swapping content.
    """
    data = event.data
    event_type = event.event

    if event_type == "device_discovered":
        mac = data.get("mac_address", "unknown")
        name = data.get("name") or data.get("alias") or mac
        return (
            f'<div id="device-event" hx-swap-oob="afterbegin:#device-list">'
            f'<div class="device-item" data-mac="{mac}">'
            f'<span class="device-name">{name}</span>'
            f'<span class="device-mac">{mac}</span>'
            f"</div></div>"
        )

    if event_type == "device_updated":
        mac = data.get("mac_address", "unknown")
        props = data.get("properties", {})
        return (
            f'<div id="device-event" hx-swap-oob="true">'
            f"<span data-mac=\"{mac}\" data-props='{json.dumps(props)}'></span>"
            f"</div>"
        )

    if event_type == "scan_started":
        duration = data.get("duration_seconds", "?")
        return (
            f'<div id="scan-status" hx-swap-oob="true">'
            f'<span class="scanning">Scanning ({duration}s)...</span>'
            f"</div>"
        )

    if event_type == "scan_stopped":
        return (
            '<div id="scan-status" hx-swap-oob="true"><span class="idle">Scan complete</span></div>'
        )

    if event_type == "adapter_changed":
        return (
            f'<div id="adapter-event" hx-swap-oob="true">'
            f"<span data-props='{json.dumps(data.get('properties', {}))}'></span>"
            f"</div>"
        )

    # Fallback: generic event
    return f'<div id="event-{event_type}" hx-swap-oob="true"><span>{event_type}</span></div>'


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    event_bus: Annotated[EventBus, Depends(get_event_bus)],
) -> None:
    """WebSocket endpoint for streaming real-time Bluetooth events.

    Supports two message formats:
    - JSON (default): sends event as JSON object
    - HTML: sends HTMX-compatible HTML partial

    Clients can send {"format": "html"} or {"format": "json"} to switch.
    """
    await websocket.accept()

    sub_id, queue = event_bus.subscribe()
    logger.info("WebSocket client connected (subscriber %d)", sub_id)

    output_format = "json"

    async def _read_client() -> None:
        """Read messages from client to handle format switching and keepalive."""
        nonlocal output_format
        try:
            while True:
                raw = await websocket.receive_text()
                try:
                    msg = json.loads(raw)
                    if isinstance(msg, dict) and "format" in msg:
                        requested = msg["format"]
                        if requested in ("json", "html"):
                            output_format = requested
                            logger.debug(
                                "Client %d switched to %s format",
                                sub_id,
                                output_format,
                            )
                except (json.JSONDecodeError, TypeError):
                    pass  # Ignore malformed messages (could be pings)
        except WebSocketDisconnect:
            pass
        except Exception:
            logger.debug("Client reader error", exc_info=True)

    async def _write_events() -> None:
        """Read events from the bus queue and forward to the client."""
        try:
            while True:
                event: Event = await queue.get()
                try:
                    if output_format == "html":
                        html = _event_to_html(event)
                        await websocket.send_text(html)
                    else:
                        await websocket.send_json(event.to_dict())
                except WebSocketDisconnect:
                    break
                except Exception:
                    logger.debug("Error sending event to client %d", sub_id, exc_info=True)
                    break
        except asyncio.CancelledError:
            pass

    reader_task = asyncio.create_task(_read_client())
    writer_task = asyncio.create_task(_write_events())

    try:
        # Wait until one of the tasks completes (e.g., client disconnects)
        _done, pending = await asyncio.wait(
            [reader_task, writer_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
    finally:
        event_bus.unsubscribe(sub_id)
        logger.info("WebSocket client disconnected (subscriber %d)", sub_id)
