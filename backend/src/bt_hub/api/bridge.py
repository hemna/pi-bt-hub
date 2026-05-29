"""Bridge proxy API routes.

All routes forward requests to the headless bridge daemon via BridgeProxy.
Registered conditionally when bridge_enabled=true.
"""

from __future__ import annotations

import dataclasses
import logging
from typing import Any

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, PlainTextResponse, StreamingResponse
from starlette.routing import Route, Router

from bt_hub.deps import get_bridge_proxy, get_bridge_service, render_template

logger = logging.getLogger(__name__)


def _proxy_response(data: dict[str, Any] | None) -> JSONResponse:
    """Wrap proxy result: return data or offline indicator."""
    if data is None:
        return JSONResponse({"offline": True, "message": "Bridge is not reachable"})
    return JSONResponse(data)


# --- Status ---


async def bridge_status(request: Request) -> JSONResponse:
    proxy = get_bridge_proxy()
    return _proxy_response(await proxy.get_status())


async def bridge_status_stream(request: Request) -> StreamingResponse:
    proxy = get_bridge_proxy()
    return StreamingResponse(
        proxy.stream_status(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


async def bridge_stats(request: Request) -> JSONResponse:
    proxy = get_bridge_proxy()
    return _proxy_response(await proxy.get_stats())


# --- Logs ---


async def bridge_logs_recent(request: Request) -> JSONResponse:
    proxy = get_bridge_proxy()
    return _proxy_response(await proxy.get_recent_logs())


async def bridge_logs_stream(request: Request) -> StreamingResponse:
    proxy = get_bridge_proxy()
    return StreamingResponse(
        proxy.stream_logs(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


# --- Settings ---


async def bridge_settings_get(request: Request) -> JSONResponse:
    proxy = get_bridge_proxy()
    return _proxy_response(await proxy.get_settings())


async def bridge_settings_update(request: Request) -> JSONResponse:
    proxy = get_bridge_proxy()
    data = await request.json()
    return _proxy_response(await proxy.update_settings(data))


# --- Daemon control ---


async def bridge_restart(request: Request) -> JSONResponse:
    proxy = get_bridge_proxy()
    return _proxy_response(await proxy.restart())


# --- Systemd Service Control ---


async def bridge_service_status(request: Request) -> JSONResponse:
    """Get the systemd service status for bt-bridge."""
    service = get_bridge_service()
    status = await service.status()
    return JSONResponse(dataclasses.asdict(status))


async def bridge_service_start(request: Request) -> object:
    """Start the bt-bridge systemd service."""
    service = get_bridge_service()
    result = await service.start()
    if "hx-request" in request.headers:
        status = await service.status()
        return render_template(
            "partials/bridge_service_status.html",
            request,
            service_status=status,
            result=result,
        )
    return JSONResponse(dataclasses.asdict(result))


async def bridge_service_stop(request: Request) -> object:
    """Stop the bt-bridge systemd service."""
    service = get_bridge_service()
    result = await service.stop()
    if "hx-request" in request.headers:
        status = await service.status()
        return render_template(
            "partials/bridge_service_status.html",
            request,
            service_status=status,
            result=result,
        )
    return JSONResponse(dataclasses.asdict(result))


async def bridge_service_restart(request: Request) -> object:
    """Restart the bt-bridge systemd service."""
    service = get_bridge_service()
    result = await service.restart()
    if "hx-request" in request.headers:
        status = await service.status()
        return render_template(
            "partials/bridge_service_status.html",
            request,
            service_status=status,
            result=result,
        )
    return JSONResponse(dataclasses.asdict(result))


async def bridge_service_logs(request: Request) -> JSONResponse | PlainTextResponse:
    """Get recent journalctl logs for bt-bridge service."""
    service = get_bridge_service()
    try:
        lines = int(request.query_params.get("lines", 100))
    except (ValueError, TypeError):
        lines = 100
    logs = await service.logs(lines=lines)
    if "hx-request" in request.headers:
        return PlainTextResponse(logs)
    return JSONResponse({"logs": logs})


async def bridge_service_install(request: Request) -> JSONResponse | HTMLResponse:
    """Install bt-bridge from GitHub."""
    service = get_bridge_service()
    result = await service.install_bt_bridge()
    if "hx-request" in request.headers:
        status_class = "alert--success" if result.success else "alert--error"
        reload_hint = "<br><small>Page will reload in 2 seconds...</small>" if result.success else ""
        html = (
            f'<div id="install-result-banner" class="alert {status_class}"'
            f' style="margin-bottom: 1rem;">'
            f"{result.message}{reload_hint}</div>"
            f'<pre style="white-space: pre-wrap; word-wrap: break-word;">'
            f"{result.output}</pre>"
        )
        return HTMLResponse(html)
    return JSONResponse(dataclasses.asdict(result))


# --- TNC History ---


async def bridge_tnc_list(request: Request) -> JSONResponse:
    return _proxy_response(await get_bridge_proxy().get_tnc_history())


async def bridge_tnc_add(request: Request) -> JSONResponse:
    data = await request.json()
    return _proxy_response(await get_bridge_proxy().add_tnc(data))


async def bridge_tnc_get(request: Request) -> JSONResponse:
    return _proxy_response(await get_bridge_proxy().get_tnc(request.path_params["address"]))


async def bridge_tnc_update(request: Request) -> JSONResponse:
    data = await request.json()
    return _proxy_response(await get_bridge_proxy().update_tnc(request.path_params["address"], data))


async def bridge_tnc_delete(request: Request) -> JSONResponse:
    return _proxy_response(await get_bridge_proxy().delete_tnc(request.path_params["address"]))


async def bridge_tnc_select(request: Request) -> JSONResponse:
    return _proxy_response(await get_bridge_proxy().select_tnc(request.path_params["address"]))


async def bridge_tnc_connect(request: Request) -> JSONResponse:
    return _proxy_response(await get_bridge_proxy().connect_tnc(request.path_params["address"]))


# --- HTML pages ---


async def bridge_page(request: Request) -> object:
    proxy = get_bridge_proxy()
    status = await proxy.get_status()
    return render_template("bridge/status.html", request, status=status, offline=status is None)


async def bridge_stats_page(request: Request) -> object:
    proxy = get_bridge_proxy()
    stats = await proxy.get_stats()
    status = await proxy.get_status()
    return render_template(
        "bridge/stats.html", request, stats=stats, status=status, offline=status is None
    )


async def bridge_tnc_page(request: Request) -> object:
    return render_template("bridge/tnc.html", request)


router = Router(
    routes=[
        Route("/api/bridge/status", bridge_status, methods=["GET"]),
        Route("/api/bridge/status/stream", bridge_status_stream, methods=["GET"]),
        Route("/api/bridge/stats", bridge_stats, methods=["GET"]),
        Route("/api/bridge/logs/recent", bridge_logs_recent, methods=["GET"]),
        Route("/api/bridge/logs/stream", bridge_logs_stream, methods=["GET"]),
        Route("/api/bridge/settings", bridge_settings_get, methods=["GET"]),
        Route("/api/bridge/settings", bridge_settings_update, methods=["POST"]),
        Route("/api/bridge/restart", bridge_restart, methods=["POST"]),
        Route("/api/bridge/service/status", bridge_service_status, methods=["GET"]),
        Route("/api/bridge/service/start", bridge_service_start, methods=["POST"]),
        Route("/api/bridge/service/stop", bridge_service_stop, methods=["POST"]),
        Route("/api/bridge/service/restart", bridge_service_restart, methods=["POST"]),
        Route("/api/bridge/service/logs", bridge_service_logs, methods=["GET"]),
        Route("/api/bridge/service/install", bridge_service_install, methods=["POST"]),
        Route("/api/bridge/tnc", bridge_tnc_list, methods=["GET"]),
        Route("/api/bridge/tnc", bridge_tnc_add, methods=["POST"]),
        Route("/api/bridge/tnc/{address}", bridge_tnc_get, methods=["GET"]),
        Route("/api/bridge/tnc/{address}", bridge_tnc_update, methods=["PUT"]),
        Route("/api/bridge/tnc/{address}", bridge_tnc_delete, methods=["DELETE"]),
        Route("/api/bridge/tnc/{address}/select", bridge_tnc_select, methods=["POST"]),
        Route("/api/bridge/tnc/{address}/connect", bridge_tnc_connect, methods=["POST"]),
        Route("/bridge", bridge_page, methods=["GET"]),
        Route("/bridge/stats", bridge_stats_page, methods=["GET"]),
        Route("/bridge/tnc", bridge_tnc_page, methods=["GET"]),
    ]
)
