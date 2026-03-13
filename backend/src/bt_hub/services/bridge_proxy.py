"""Bridge proxy client — communicates with the headless bridge daemon."""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class BridgeProxy:
    """Async HTTP client for proxying requests to the bridge daemon.

    All methods return None or empty results on connection failure
    (graceful degradation when bridge is offline).
    """

    def __init__(self, bridge_url: str, timeout: float = 5.0) -> None:
        self._bridge_url = bridge_url.rstrip("/")
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def startup(self) -> None:
        """Create the persistent HTTP client."""
        self._client = httpx.AsyncClient(
            base_url=self._bridge_url,
            timeout=self._timeout,
        )
        logger.info("BridgeProxy started (target: %s)", self._bridge_url)

    async def shutdown(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
        logger.info("BridgeProxy stopped")

    def _ensure_client(self) -> httpx.AsyncClient:
        assert self._client is not None, "BridgeProxy not started"
        return self._client

    async def _get(self, path: str) -> dict[str, Any] | None:
        """GET a JSON endpoint, returning None on any failure."""
        try:
            resp = await self._ensure_client().get(path)
            if resp.status_code == 200:
                return resp.json()
            logger.warning("Bridge returned HTTP %d from %s", resp.status_code, path)
            return None
        except (httpx.ConnectError, httpx.TimeoutException):
            logger.debug("Bridge unreachable: %s%s", self._bridge_url, path)
            return None
        except Exception:
            logger.warning("Unexpected error calling bridge %s", path, exc_info=True)
            return None

    async def _post(self, path: str, data: dict[str, Any] | None = None) -> dict[str, Any] | None:
        """POST JSON to an endpoint, returning None on any failure."""
        try:
            resp = await self._ensure_client().post(path, json=data)
            if resp.status_code in (200, 201, 202):
                return resp.json()
            logger.warning("Bridge returned HTTP %d from POST %s", resp.status_code, path)
            return None
        except (httpx.ConnectError, httpx.TimeoutException):
            logger.debug("Bridge unreachable: POST %s%s", self._bridge_url, path)
            return None
        except Exception:
            logger.warning("Unexpected error calling bridge POST %s", path, exc_info=True)
            return None

    async def _put(self, path: str, data: dict[str, Any]) -> dict[str, Any] | None:
        """PUT JSON to an endpoint."""
        try:
            resp = await self._ensure_client().put(path, json=data)
            if resp.status_code == 200:
                return resp.json()
            return None
        except (httpx.ConnectError, httpx.TimeoutException):
            return None
        except Exception:
            logger.warning("Unexpected error calling bridge PUT %s", path, exc_info=True)
            return None

    async def _delete(self, path: str) -> dict[str, Any] | None:
        """DELETE an endpoint."""
        try:
            resp = await self._ensure_client().delete(path)
            if resp.status_code == 200:
                return resp.json()
            return None
        except (httpx.ConnectError, httpx.TimeoutException):
            return None
        except Exception:
            logger.warning("Unexpected error calling bridge DELETE %s", path, exc_info=True)
            return None

    # --- Status ---

    async def get_status(self) -> dict[str, Any] | None:
        return await self._get("/api/status")

    # --- Statistics ---

    async def get_stats(self) -> dict[str, Any] | None:
        return await self._get("/api/stats")

    # --- Logs ---

    async def get_recent_logs(self) -> dict[str, Any] | None:
        return await self._get("/api/logs/recent")

    # --- Settings ---

    async def get_settings(self) -> dict[str, Any] | None:
        return await self._get("/api/settings")

    async def update_settings(self, data: dict[str, Any]) -> dict[str, Any] | None:
        return await self._post("/api/settings", data)

    # --- Daemon control ---

    async def restart(self) -> dict[str, Any] | None:
        return await self._post("/api/restart")

    # --- TNC History ---

    async def get_tnc_history(self) -> dict[str, Any] | None:
        return await self._get("/api/tnc-history")

    async def add_tnc(self, data: dict[str, Any]) -> dict[str, Any] | None:
        return await self._post("/api/tnc-history", data)

    async def get_tnc(self, address: str) -> dict[str, Any] | None:
        return await self._get(f"/api/tnc-history/{address}")

    async def update_tnc(self, address: str, data: dict[str, Any]) -> dict[str, Any] | None:
        return await self._put(f"/api/tnc-history/{address}", data)

    async def delete_tnc(self, address: str) -> dict[str, Any] | None:
        return await self._delete(f"/api/tnc-history/{address}")

    async def select_tnc(self, address: str) -> dict[str, Any] | None:
        return await self._post(f"/api/tnc-history/{address}/select")

    async def connect_tnc(self, address: str) -> dict[str, Any] | None:
        return await self._post(f"/api/tnc-history/{address}/connect")
