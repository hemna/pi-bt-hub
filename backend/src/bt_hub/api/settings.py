"""Settings API endpoints."""

from __future__ import annotations

import dataclasses
import logging
from typing import TYPE_CHECKING, Any

from starlette.responses import JSONResponse
from starlette.routing import Route, Router

if TYPE_CHECKING:
    from starlette.requests import Request

from bt_hub.deps import get_device_store, render_template
from bt_hub.models.settings import AppSettings, AppSettingsUpdate

logger = logging.getLogger(__name__)


async def get_settings(request: Request) -> JSONResponse:
    """Return the current application settings."""
    store = get_device_store()
    row = await store.get_settings()
    return JSONResponse(dataclasses.asdict(AppSettings(**row)))


async def update_settings(request: Request) -> JSONResponse:
    """Update application settings. Only provided fields are changed."""
    store = get_device_store()
    try:
        data = await request.json()
    except Exception:
        data = {}

    try:
        body = AppSettingsUpdate(**{k: v for k, v in data.items() if v is not None})
    except ValueError as e:
        return JSONResponse({"error": "validation_error", "message": str(e)}, status_code=422)
    update_fields: dict[str, Any] = {}
    logger.info("Updating settings: %s", data)

    if body.theme is not None:
        update_fields["theme"] = body.theme.value
    if body.auto_connect_favorites is not None:
        update_fields["auto_connect_favorites"] = body.auto_connect_favorites
    if body.scan_duration_seconds is not None:
        update_fields["scan_duration_seconds"] = body.scan_duration_seconds
    if body.adapter_name is not None:
        update_fields["adapter_name"] = body.adapter_name

    row = await store.update_settings(**update_fields)
    return JSONResponse(dataclasses.asdict(AppSettings(**row)))


async def settings_page(request: Request) -> object:
    """Serve the settings page."""
    store = get_device_store()
    row = await store.get_settings()
    settings = AppSettings(**row)
    return render_template("settings.html", request, settings=settings)


router = Router(
    routes=[
        Route("/api/settings", get_settings, methods=["GET"]),
        Route("/api/settings", update_settings, methods=["PATCH"]),
        Route("/settings", settings_page, methods=["GET"]),
    ]
)
