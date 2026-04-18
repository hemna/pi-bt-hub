"""Log viewing API endpoints and page."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from fastapi.templating import Jinja2Templates  # noqa: TC002

from bt_hub.deps import get_templates, render_template
from bt_hub.services.log_handler import get_sse_log_handler

if TYPE_CHECKING:
    from bt_hub.lifecycle import ServiceContainer

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/logs")
async def logs_page(
    request: Request,
    templates: Annotated[Jinja2Templates, Depends(get_templates)],
) -> object:
    """Serve the log viewer page."""
    return render_template("logs.html", request)


@router.get("/api/logs/stream")
async def logs_stream() -> StreamingResponse:
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


@router.get("/api/logs/recent")
async def logs_recent(count: int = 100) -> dict:
    """Return recent log entries as JSON."""
    handler = get_sse_log_handler()
    if handler is None:
        return {"entries": [], "error": "Log streaming not configured"}

    clamped = min(max(count, 1), 500)
    entries = handler.get_recent(clamped)
    return {"entries": entries, "count": len(entries)}


# --- Factory functions for library usage ---


def create_api_router(container: ServiceContainer) -> APIRouter:
    """Create an APIRouter with log API endpoints using the ServiceContainer."""
    api = APIRouter()

    @api.get("/api/logs/stream")
    async def logs_stream_factory() -> StreamingResponse:
        assert container.services is not None
        handler = container.services.log_handler
        if handler is None:
            handler = get_sse_log_handler()
        if handler is None:
            return StreamingResponse(
                iter(['data: {"error": "Log streaming not configured"}\n\n']),
                media_type="text/event-stream",
            )

        async def event_generator() -> object:
            recent = handler.get_recent(100)
            if recent:
                data = json.dumps({"entries": recent})
                yield f"event: log_history\ndata: {data}\n\n"
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
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )

    @api.get("/api/logs/recent")
    async def logs_recent_factory(count: int = 100) -> dict:
        assert container.services is not None
        handler = container.services.log_handler
        if handler is None:
            handler = get_sse_log_handler()
        if handler is None:
            return {"entries": [], "error": "Log streaming not configured"}
        clamped = min(max(count, 1), 500)
        entries = handler.get_recent(clamped)
        return {"entries": entries, "count": len(entries)}

    return api


def create_page_router(
    container: ServiceContainer,
    templates: Jinja2Templates,
    active_page_prefix: str = "bluetooth",
) -> APIRouter:
    """Create an APIRouter with log page endpoint using the ServiceContainer."""
    pages = APIRouter()

    @pages.get("/logs")
    async def logs_page_factory(request: Request) -> object:
        return render_template("logs.html", request, active_page=active_page_prefix)

    return pages
