"""Client for probing the pi-bt-bridge /api/status endpoint."""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class BtBridgeClient:
    """Async HTTP client to check if pi-bt-bridge is running and get its status.

    Designed for use in the dashboard: call get_status() on page load.
    Returns None if the bridge is not configured or unreachable.
    """

    def __init__(self, base_url: str | None, timeout: float = 2.0) -> None:
        self._base_url = base_url.rstrip("/") if base_url else None
        self._timeout = timeout

    @property
    def is_configured(self) -> bool:
        """Return True if a bridge URL has been configured."""
        return self._base_url is not None

    async def get_status(self) -> dict[str, Any] | None:
        """Probe the bridge /api/status endpoint.

        Returns the parsed JSON dict on success, or None if the bridge
        is not configured, unreachable, or returns a non-200 response.
        """
        if not self._base_url:
            return None

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(f"{self._base_url}/api/status")
                if resp.status_code == 200:
                    return resp.json()
                logger.warning(
                    "Bridge returned HTTP %d from %s/api/status",
                    resp.status_code,
                    self._base_url,
                )
                return None
        except httpx.TimeoutException:
            logger.debug("Bridge probe timed out: %s", self._base_url)
            return None
        except httpx.ConnectError:
            logger.debug("Bridge unreachable: %s", self._base_url)
            return None
        except Exception:
            logger.warning("Unexpected error probing bridge", exc_info=True)
            return None
