"""Internal async event bus for broadcasting BlueZ events to WebSocket clients."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


class Event:
    """A typed event with timestamp and payload."""

    def __init__(self, event_type: str, data: dict[str, Any]) -> None:
        self.event = event_type
        self.timestamp = datetime.now(UTC).isoformat()
        self.data = data

    def to_dict(self) -> dict[str, Any]:
        """Serialize event to the WebSocket message envelope format."""
        return {
            "event": self.event,
            "timestamp": self.timestamp,
            "data": self.data,
        }


class EventBus:
    """Async pub/sub event bus using asyncio.Queue per subscriber."""

    def __init__(self) -> None:
        self._subscribers: dict[int, asyncio.Queue[Event]] = {}
        self._next_id = 0

    def subscribe(self) -> tuple[int, asyncio.Queue[Event]]:
        """Register a new subscriber. Returns (subscriber_id, queue)."""
        sub_id = self._next_id
        self._next_id += 1
        queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=100)
        self._subscribers[sub_id] = queue
        logger.debug("Subscriber %d registered (total: %d)", sub_id, len(self._subscribers))
        return sub_id, queue

    def unsubscribe(self, subscriber_id: int) -> None:
        """Remove a subscriber by ID."""
        self._subscribers.pop(subscriber_id, None)
        logger.debug(
            "Subscriber %d unregistered (total: %d)",
            subscriber_id,
            len(self._subscribers),
        )

    async def publish(self, event: Event) -> None:
        """Broadcast an event to all subscribers. Drops if queue is full."""
        for sub_id, queue in self._subscribers.items():
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning(
                    "Subscriber %d queue full, dropping event %s",
                    sub_id,
                    event.event,
                )

    @property
    def subscriber_count(self) -> int:
        """Return the current number of subscribers."""
        return len(self._subscribers)
