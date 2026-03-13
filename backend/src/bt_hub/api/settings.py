"""Settings API endpoints."""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates  # noqa: TC002

from bt_hub.deps import get_device_store, get_templates
from bt_hub.models.settings import AppSettings, AppSettingsUpdate
from bt_hub.services.device_store import DeviceStore  # noqa: TC001

logger = logging.getLogger(__name__)

router = APIRouter()


# --- JSON API endpoints ---


@router.get("/api/settings", response_model=AppSettings)
async def get_settings(
    store: Annotated[DeviceStore, Depends(get_device_store)],
) -> AppSettings:
    """Return the current application settings."""
    row = await store.get_settings()
    return AppSettings.model_validate(row)


@router.patch("/api/settings", response_model=AppSettings)
async def update_settings(
    body: AppSettingsUpdate,
    store: Annotated[DeviceStore, Depends(get_device_store)],
) -> AppSettings:
    """Update application settings. Only provided fields are changed."""
    update_fields: dict[str, Any] = {}
    logger.info("Updating settings: %s", body.model_dump(exclude_none=True))

    if body.theme is not None:
        update_fields["theme"] = body.theme.value
    if body.auto_connect_favorites is not None:
        update_fields["auto_connect_favorites"] = body.auto_connect_favorites
    if body.scan_duration_seconds is not None:
        update_fields["scan_duration_seconds"] = body.scan_duration_seconds
    if body.adapter_name is not None:
        update_fields["adapter_name"] = body.adapter_name

    row = await store.update_settings(**update_fields)
    return AppSettings.model_validate(row)


# --- HTML page endpoint ---


@router.get("/settings")
async def settings_page(
    request: Request,
    templates: Annotated[Jinja2Templates, Depends(get_templates)],
    store: Annotated[DeviceStore, Depends(get_device_store)],
) -> object:
    """Serve the settings page."""
    row = await store.get_settings()
    settings = AppSettings.model_validate(row)
    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "settings": settings,
        },
    )
