"""SSE log handler for real-time log streaming to the browser.

Provides a Python logging.Handler that buffers log records in a ring buffer
and publishes them to SSE subscriber queues for real-time streaming.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
from collections import deque
from datetime import UTC, datetime

# Module-level singleton
_sse_log_handler: SSELogHandler | None = None

DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def get_sse_log_handler() -> SSELogHandler | None:
    """Get the global SSE log handler instance (if configured)."""
    return _sse_log_handler


def setup_sse_logging(level: int = logging.DEBUG) -> SSELogHandler:
    """Create and attach an SSELogHandler to the bt_hub root logger.

    This should be called once during application startup (lifespan).
    The handler captures all log records from bt_hub.* loggers.

    Returns:
        The configured SSELogHandler instance.
    """
    global _sse_log_handler

    handler = SSELogHandler(maxlen=500, level=level)
    _sse_log_handler = handler

    # Attach to the root bt_hub logger so all child loggers are captured
    root_logger = logging.getLogger("bt_hub")
    root_logger.addHandler(handler)

    # Also capture uvicorn access logs
    uvicorn_logger = logging.getLogger("uvicorn.access")
    uvicorn_logger.addHandler(handler)

    return handler


class SSELogHandler(logging.Handler):
    """Logging handler that buffers entries and pushes to SSE consumers.

    Keeps the last ``maxlen`` formatted log entries in a ring buffer so new
    SSE clients receive recent history, and publishes each new entry to all
    registered async queues for real-time streaming.
    """

    def __init__(self, maxlen: int = 500, level: int = logging.DEBUG) -> None:
        super().__init__(level)
        self._buffer: deque[dict[str, str]] = deque(maxlen=maxlen)
        self._subscribers: list[asyncio.Queue[dict[str, str]]] = []
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        """Process a log record: buffer it and push to all subscribers."""
        try:
            entry = self._format_entry(record)
            with self._lock:
                self._buffer.append(entry)
                for queue in self._subscribers:
                    try:
                        queue.put_nowait(entry)
                    except asyncio.QueueFull:
                        # Drop oldest to make room
                        with contextlib.suppress(asyncio.QueueEmpty):
                            queue.get_nowait()
                        with contextlib.suppress(asyncio.QueueFull):
                            queue.put_nowait(entry)
        except Exception:
            self.handleError(record)

    def _format_entry(self, record: logging.LogRecord) -> dict[str, str]:
        """Format a log record into a dict for JSON serialization."""
        return {
            "timestamp": datetime.now(UTC).strftime(DATE_FORMAT),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

    def get_recent(self, count: int | None = None) -> list[dict[str, str]]:
        """Return recent log entries from the ring buffer.

        Args:
            count: Max entries to return. None returns all buffered entries.

        Returns:
            List of log entry dicts, oldest first.
        """
        with self._lock:
            if count is None:
                return list(self._buffer)
            return list(self._buffer)[-count:]

    def subscribe(self) -> asyncio.Queue[dict[str, str]]:
        """Create a new subscriber queue for real-time streaming.

        Returns:
            An asyncio.Queue that will receive new log entries.
        """
        queue: asyncio.Queue[dict[str, str]] = asyncio.Queue(maxsize=200)
        with self._lock:
            self._subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, str]]) -> None:
        """Remove a subscriber queue."""
        with self._lock:
            if queue in self._subscribers:
                self._subscribers.remove(queue)

    @property
    def subscriber_count(self) -> int:
        """Number of active subscribers."""
        with self._lock:
            return len(self._subscribers)

    @property
    def buffer_size(self) -> int:
        """Number of entries in the ring buffer."""
        with self._lock:
            return len(self._buffer)
