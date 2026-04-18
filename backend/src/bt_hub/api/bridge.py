"""Bridge proxy API routes.

All routes forward requests to the headless bridge daemon via BridgeProxy.
Registered conditionally when bridge_enabled=true.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from bt_hub.deps import get_bridge_proxy, get_bridge_service, get_templates, render_template
from bt_hub.services.bridge_proxy import BridgeProxy
from bt_hub.services.systemd_service import SystemdService

if TYPE_CHECKING:
    from bt_hub.lifecycle import ServiceContainer

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


# --- Systemd Service Control ---


@router.get("/api/bridge/service/status")
async def bridge_service_status(
    service: Annotated[SystemdService, Depends(get_bridge_service)],
) -> JSONResponse:
    """Get the systemd service status for bt-bridge."""
    status = await service.status()
    return JSONResponse(status.model_dump())


@router.post("/api/bridge/service/start")
async def bridge_service_start(
    request: Request,
    service: Annotated[SystemdService, Depends(get_bridge_service)],
    templates: Annotated[Jinja2Templates, Depends(get_templates)],
) -> JSONResponse:
    """Start the bt-bridge systemd service."""
    result = await service.start()
    # For HTMX requests, return the updated bridge card partial
    if "hx-request" in request.headers:
        # Get fresh status after action
        status = await service.status()
        return render_template(
            "partials/bridge_service_status.html",
            request,
            service_status=status,
            result=result,
        )
    return JSONResponse(result.model_dump())


@router.post("/api/bridge/service/stop")
async def bridge_service_stop(
    request: Request,
    service: Annotated[SystemdService, Depends(get_bridge_service)],
    templates: Annotated[Jinja2Templates, Depends(get_templates)],
) -> JSONResponse:
    """Stop the bt-bridge systemd service."""
    result = await service.stop()
    if "hx-request" in request.headers:
        status = await service.status()
        return render_template(
            "partials/bridge_service_status.html",
            request,
            service_status=status,
            result=result,
        )
    return JSONResponse(result.model_dump())


@router.post("/api/bridge/service/restart")
async def bridge_service_restart(
    request: Request,
    service: Annotated[SystemdService, Depends(get_bridge_service)],
    templates: Annotated[Jinja2Templates, Depends(get_templates)],
) -> JSONResponse:
    """Restart the bt-bridge systemd service."""
    result = await service.restart()
    if "hx-request" in request.headers:
        status = await service.status()
        return render_template(
            "partials/bridge_service_status.html",
            request,
            service_status=status,
            result=result,
        )
    return JSONResponse(result.model_dump())


@router.get("/api/bridge/service/logs", response_model=None)
async def bridge_service_logs(
    request: Request,
    service: Annotated[SystemdService, Depends(get_bridge_service)],
    lines: int = 100,
) -> JSONResponse | PlainTextResponse:
    """Get recent journalctl logs for bt-bridge service."""
    logs = await service.logs(lines=lines)
    # For HTMX requests, return plain text that goes directly into the pre element
    if "hx-request" in request.headers:
        return PlainTextResponse(logs)
    return JSONResponse({"logs": logs})


@router.post("/api/bridge/service/install", response_model=None)
async def bridge_service_install(
    request: Request,
    service: Annotated[SystemdService, Depends(get_bridge_service)],
    templates: Annotated[Jinja2Templates, Depends(get_templates)],
) -> JSONResponse | HTMLResponse:
    """Install bt-bridge from GitHub."""
    result = await service.install_bt_bridge()
    if "hx-request" in request.headers:
        # Return HTML with result for the modal
        status_class = "alert--success" if result.success else "alert--error"
        html = f"""<div id="install-result-banner" class="alert {status_class}" style="margin-bottom: 1rem;">
            {result.message}
            {"<br><small>Page will reload in 2 seconds...</small>" if result.success else ""}
        </div>
        <pre style="white-space: pre-wrap; word-wrap: break-word;">{result.output}</pre>
        <script>
            document.getElementById('bridge-install-status').innerHTML = document.getElementById('install-result-banner').outerHTML;
            document.getElementById('install-result-banner').remove();
        </script>"""
        return HTMLResponse(html)
    return JSONResponse(result.model_dump())


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
    return render_template(
        "bridge/status.html",
        request,
        status=status,
        offline=status is None,
    )


@router.get("/bridge/stats")
async def bridge_stats_page(
    request: Request,
    proxy: Annotated[BridgeProxy, Depends(get_bridge_proxy)],
    templates: Annotated[Jinja2Templates, Depends(get_templates)],
) -> object:
    stats = await proxy.get_stats()
    status = await proxy.get_status()
    return render_template(
        "bridge/stats.html",
        request,
        stats=stats,
        status=status,
        offline=status is None,
    )


@router.get("/bridge/tnc")
async def bridge_tnc_page(
    request: Request,
    proxy: Annotated[BridgeProxy, Depends(get_bridge_proxy)],
    templates: Annotated[Jinja2Templates, Depends(get_templates)],
) -> object:
    return render_template("bridge/tnc.html", request)


# --- Factory functions for library usage ---


def create_api_router(container: ServiceContainer) -> APIRouter:
    """Create an APIRouter with bridge API endpoints using the ServiceContainer."""
    api = APIRouter()

    def _get_proxy() -> BridgeProxy:
        assert container.services is not None
        proxy = container.services.bridge_proxy
        if proxy is None:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="Bridge not enabled")
        return proxy

    def _get_service() -> SystemdService:
        assert container.services is not None
        service = container.services.systemd_service
        if service is None:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="Bridge service not available")
        return service

    @api.get("/api/bridge/status")
    async def bridge_status_factory() -> JSONResponse:
        return _proxy_response(await _get_proxy().get_status())

    @api.get("/api/bridge/status/stream")
    async def bridge_status_stream_factory() -> StreamingResponse:
        return StreamingResponse(
            _get_proxy().stream_status(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )

    @api.get("/api/bridge/stats")
    async def bridge_stats_factory() -> JSONResponse:
        return _proxy_response(await _get_proxy().get_stats())

    @api.get("/api/bridge/logs/recent")
    async def bridge_logs_recent_factory() -> JSONResponse:
        return _proxy_response(await _get_proxy().get_recent_logs())

    @api.get("/api/bridge/logs/stream")
    async def bridge_logs_stream_factory() -> StreamingResponse:
        return StreamingResponse(
            _get_proxy().stream_logs(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )

    @api.get("/api/bridge/settings")
    async def bridge_settings_get_factory() -> JSONResponse:
        return _proxy_response(await _get_proxy().get_settings())

    @api.post("/api/bridge/settings")
    async def bridge_settings_update_factory(request: Request) -> JSONResponse:
        data = await request.json()
        return _proxy_response(await _get_proxy().update_settings(data))

    @api.post("/api/bridge/restart")
    async def bridge_restart_factory() -> JSONResponse:
        return _proxy_response(await _get_proxy().restart())

    @api.get("/api/bridge/service/status")
    async def bridge_service_status_factory() -> JSONResponse:
        status = await _get_service().status()
        return JSONResponse(status.model_dump())

    @api.post("/api/bridge/service/start")
    async def bridge_service_start_factory(request: Request) -> JSONResponse:
        service = _get_service()
        result = await service.start()
        if "hx-request" in request.headers:
            status = await service.status()
            return render_template(
                "partials/bridge_service_status.html",
                request,
                service_status=status,
                result=result,
            )
        return JSONResponse(result.model_dump())

    @api.post("/api/bridge/service/stop")
    async def bridge_service_stop_factory(request: Request) -> JSONResponse:
        service = _get_service()
        result = await service.stop()
        if "hx-request" in request.headers:
            status = await service.status()
            return render_template(
                "partials/bridge_service_status.html",
                request,
                service_status=status,
                result=result,
            )
        return JSONResponse(result.model_dump())

    @api.post("/api/bridge/service/restart")
    async def bridge_service_restart_factory(request: Request) -> JSONResponse:
        service = _get_service()
        result = await service.restart()
        if "hx-request" in request.headers:
            status = await service.status()
            return render_template(
                "partials/bridge_service_status.html",
                request,
                service_status=status,
                result=result,
            )
        return JSONResponse(result.model_dump())

    @api.get("/api/bridge/service/logs", response_model=None)
    async def bridge_service_logs_factory(
        request: Request, lines: int = 100
    ) -> JSONResponse | PlainTextResponse:
        logs = await _get_service().logs(lines=lines)
        if "hx-request" in request.headers:
            return PlainTextResponse(logs)
        return JSONResponse({"logs": logs})

    @api.post("/api/bridge/service/install", response_model=None)
    async def bridge_service_install_factory(
        request: Request,
    ) -> JSONResponse | HTMLResponse:
        result = await _get_service().install_bt_bridge()
        if "hx-request" in request.headers:
            status_class = "alert--success" if result.success else "alert--error"
            html = f"""<div id="install-result-banner" class="alert {status_class}" style="margin-bottom: 1rem;">
                {result.message}
                {"<br><small>Page will reload in 2 seconds...</small>" if result.success else ""}
            </div>
            <pre style="white-space: pre-wrap; word-wrap: break-word;">{result.output}</pre>"""
            return HTMLResponse(html)
        return JSONResponse(result.model_dump())

    @api.get("/api/bridge/tnc")
    async def bridge_tnc_list_factory() -> JSONResponse:
        return _proxy_response(await _get_proxy().get_tnc_history())

    @api.post("/api/bridge/tnc")
    async def bridge_tnc_add_factory(request: Request) -> JSONResponse:
        data = await request.json()
        return _proxy_response(await _get_proxy().add_tnc(data))

    @api.get("/api/bridge/tnc/{address}")
    async def bridge_tnc_get_factory(address: str) -> JSONResponse:
        return _proxy_response(await _get_proxy().get_tnc(address))

    @api.put("/api/bridge/tnc/{address}")
    async def bridge_tnc_update_factory(address: str, request: Request) -> JSONResponse:
        data = await request.json()
        return _proxy_response(await _get_proxy().update_tnc(address, data))

    @api.delete("/api/bridge/tnc/{address}")
    async def bridge_tnc_delete_factory(address: str) -> JSONResponse:
        return _proxy_response(await _get_proxy().delete_tnc(address))

    @api.post("/api/bridge/tnc/{address}/select")
    async def bridge_tnc_select_factory(address: str) -> JSONResponse:
        return _proxy_response(await _get_proxy().select_tnc(address))

    @api.post("/api/bridge/tnc/{address}/connect")
    async def bridge_tnc_connect_factory(address: str) -> JSONResponse:
        return _proxy_response(await _get_proxy().connect_tnc(address))

    return api


def create_page_router(
    container: ServiceContainer,
    templates: Jinja2Templates,
    active_page_prefix: str = "bluetooth",
) -> APIRouter:
    """Create an APIRouter with bridge page endpoints using the ServiceContainer."""
    pages = APIRouter()

    def _get_proxy() -> BridgeProxy | None:
        assert container.services is not None
        return container.services.bridge_proxy

    @pages.get("/bridge")
    async def bridge_page_factory(request: Request) -> object:
        proxy = _get_proxy()
        if proxy is None:
            return render_template(
                "bridge/status.html",
                request,
                status=None,
                offline=True,
                active_page=active_page_prefix,
            )
        status = await proxy.get_status()
        return render_template(
            "bridge/status.html",
            request,
            status=status,
            offline=status is None,
            active_page=active_page_prefix,
        )

    @pages.get("/bridge/stats")
    async def bridge_stats_page_factory(request: Request) -> object:
        proxy = _get_proxy()
        if proxy is None:
            return render_template(
                "bridge/stats.html",
                request,
                stats=None,
                status=None,
                offline=True,
                active_page=active_page_prefix,
            )
        stats = await proxy.get_stats()
        status = await proxy.get_status()
        return render_template(
            "bridge/stats.html",
            request,
            stats=stats,
            status=status,
            offline=status is None,
            active_page=active_page_prefix,
        )

    @pages.get("/bridge/tnc")
    async def bridge_tnc_page_factory(request: Request) -> object:
        return render_template("bridge/tnc.html", request, active_page=active_page_prefix)

    return pages
