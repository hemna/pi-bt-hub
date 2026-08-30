"""Log viewing API endpoints and page."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING

from starlette.responses import StreamingResponse
from starlette.routing import Route, Router

if TYPE_CHECKING:
    from starlette.requests import Request

from bt_hub.deps import render_template
from bt_hub.services.log_handler import get_sse_log_handler

logger = logging.getLogger(__name__)


async def logs_page(request: Request) -> object:
    """Serve the log viewer page."""
    return render_template("logs.html", request)


async def logs_stream(request: Request) -> StreamingResponse:
    """SSE endpoint for real-time log streaming.

    Sends an initial ``log_history`` event with recent entries,
    then streams individual ``log`` events as they occur.
    """
    handler = get_sse_log_handler()
    if handler is None:
        return StreamingResponse(
            iter(['data: {"error": "Log streaming not configured"}\n\n']),
            media_type="text/event-stream",
        )

    async def event_generator() -> object:
        # Send recent history as initial batch
        recent = handler.get_recent(100)
        if recent:
            data = json.dumps({"entries": recent})
            yield f"event: log_history\ndata: {data}\n\n"

        # Subscribe for real-time entries
        queue = handler.subscribe()
        try:
            while True:
                entry = await queue.get()
                yield f"event: log\ndata: {json.dumps(entry)}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            handler.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


async def logs_recent(request: Request) -> object:
    """Return recent log entries as JSON."""
    from starlette.responses import JSONResponse

    handler = get_sse_log_handler()
    if handler is None:
        return JSONResponse({"entries": [], "error": "Log streaming not configured"})

    try:
        count = int(request.query_params.get("count", 100))
    except (ValueError, TypeError):
        count = 100
    clamped = min(max(count, 1), 500)
    entries = handler.get_recent(clamped)
    return JSONResponse({"entries": entries, "count": len(entries)})


router = Router(
    routes=[
        Route("/logs", logs_page, methods=["GET"]),
        Route("/api/logs/stream", logs_stream, methods=["GET"]),
        Route("/api/logs/recent", logs_recent, methods=["GET"]),
    ]
)
