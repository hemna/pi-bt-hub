"""Bridge proxy API routes.

All routes forward requests to the headless bridge daemon via BridgeProxy.
Registered conditionally when bridge_enabled=true.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from bt_hub.deps import get_bridge_proxy, get_templates
from bt_hub.services.bridge_proxy import BridgeProxy

logger = logging.getLogger(__name__)

router = APIRouter()


def _proxy_response(data: dict[str, Any] | None) -> JSONResponse:
    """Wrap proxy result: return data or offline indicator."""
    if data is None:
        return JSONResponse({"offline": True, "message": "Bridge is not reachable"})
    return JSONResponse(data)


# --- Status ---


@router.get("/api/bridge/status")
async def bridge_status(
    proxy: Annotated[BridgeProxy, Depends(get_bridge_proxy)],
) -> JSONResponse:
    return _proxy_response(await proxy.get_status())


@router.get("/api/bridge/status/stream")
async def bridge_status_stream(
    proxy: Annotated[BridgeProxy, Depends(get_bridge_proxy)],
) -> StreamingResponse:
    return StreamingResponse(
        proxy.stream_status(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.get("/api/bridge/stats")
async def bridge_stats(
    proxy: Annotated[BridgeProxy, Depends(get_bridge_proxy)],
) -> JSONResponse:
    return _proxy_response(await proxy.get_stats())


# --- Logs ---


@router.get("/api/bridge/logs/recent")
async def bridge_logs_recent(
    proxy: Annotated[BridgeProxy, Depends(get_bridge_proxy)],
) -> JSONResponse:
    return _proxy_response(await proxy.get_recent_logs())


@router.get("/api/bridge/logs/stream")
async def bridge_logs_stream(
    proxy: Annotated[BridgeProxy, Depends(get_bridge_proxy)],
) -> StreamingResponse:
    return StreamingResponse(
        proxy.stream_logs(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


# --- Settings ---


@router.get("/api/bridge/settings")
async def bridge_settings_get(
    proxy: Annotated[BridgeProxy, Depends(get_bridge_proxy)],
) -> JSONResponse:
    return _proxy_response(await proxy.get_settings())


@router.post("/api/bridge/settings")
async def bridge_settings_update(
    request: Request,
    proxy: Annotated[BridgeProxy, Depends(get_bridge_proxy)],
) -> JSONResponse:
    data = await request.json()
    return _proxy_response(await proxy.update_settings(data))


# --- Daemon control ---


@router.post("/api/bridge/restart")
async def bridge_restart(
    proxy: Annotated[BridgeProxy, Depends(get_bridge_proxy)],
) -> JSONResponse:
    return _proxy_response(await proxy.restart())


# --- TNC History ---


@router.get("/api/bridge/tnc")
async def bridge_tnc_list(
    proxy: Annotated[BridgeProxy, Depends(get_bridge_proxy)],
) -> JSONResponse:
    return _proxy_response(await proxy.get_tnc_history())


@router.post("/api/bridge/tnc")
async def bridge_tnc_add(
    request: Request,
    proxy: Annotated[BridgeProxy, Depends(get_bridge_proxy)],
) -> JSONResponse:
    data = await request.json()
    return _proxy_response(await proxy.add_tnc(data))


@router.get("/api/bridge/tnc/{address}")
async def bridge_tnc_get(
    address: str,
    proxy: Annotated[BridgeProxy, Depends(get_bridge_proxy)],
) -> JSONResponse:
    return _proxy_response(await proxy.get_tnc(address))


@router.put("/api/bridge/tnc/{address}")
async def bridge_tnc_update(
    address: str,
    request: Request,
    proxy: Annotated[BridgeProxy, Depends(get_bridge_proxy)],
) -> JSONResponse:
    data = await request.json()
    return _proxy_response(await proxy.update_tnc(address, data))


@router.delete("/api/bridge/tnc/{address}")
async def bridge_tnc_delete(
    address: str,
    proxy: Annotated[BridgeProxy, Depends(get_bridge_proxy)],
) -> JSONResponse:
    return _proxy_response(await proxy.delete_tnc(address))


@router.post("/api/bridge/tnc/{address}/select")
async def bridge_tnc_select(
    address: str,
    proxy: Annotated[BridgeProxy, Depends(get_bridge_proxy)],
) -> JSONResponse:
    return _proxy_response(await proxy.select_tnc(address))


@router.post("/api/bridge/tnc/{address}/connect")
async def bridge_tnc_connect(
    address: str,
    proxy: Annotated[BridgeProxy, Depends(get_bridge_proxy)],
) -> JSONResponse:
    return _proxy_response(await proxy.connect_tnc(address))


# --- HTML pages (server-rendered) ---


@router.get("/bridge")
async def bridge_page(
    request: Request,
    proxy: Annotated[BridgeProxy, Depends(get_bridge_proxy)],
    templates: Annotated[Jinja2Templates, Depends(get_templates)],
) -> object:
    status = await proxy.get_status()
    return templates.TemplateResponse("bridge/status.html", {
        "request": request,
        "status": status,
        "offline": status is None,
    })


@router.get("/bridge/stats")
async def bridge_stats_page(
    request: Request,
    proxy: Annotated[BridgeProxy, Depends(get_bridge_proxy)],
    templates: Annotated[Jinja2Templates, Depends(get_templates)],
) -> object:
    stats = await proxy.get_stats()
    status = await proxy.get_status()
    return templates.TemplateResponse("bridge/stats.html", {
        "request": request,
        "stats": stats,
        "status": status,
        "offline": status is None,
    })


@router.get("/bridge/tnc")
async def bridge_tnc_page(
    request: Request,
    proxy: Annotated[BridgeProxy, Depends(get_bridge_proxy)],
    templates: Annotated[Jinja2Templates, Depends(get_templates)],
) -> object:
    return templates.TemplateResponse("bridge/tnc.html", {
        "request": request,
    })
