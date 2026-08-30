"""Tests for EventBus publish snapshot safety (#7)."""

from __future__ import annotations

import pytest

from bt_hub.services.event_bus import Event, EventBus


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


def _make_event(kind: str = "test") -> Event:
    return Event(kind, {"key": "val"})


class TestEventBusPublish:
    """Tests for EventBus.publish dict-snapshot safety."""

    async def test_publish_delivers_to_all_subscribers(self, bus: EventBus) -> None:
        """Events reach every registered subscriber queue."""
        _, q1 = bus.subscribe()
        _, q2 = bus.subscribe()
        event = _make_event()

        await bus.publish(event)

        assert q1.qsize() == 1
        assert q2.qsize() == 1
        assert q1.get_nowait() is event
        assert q2.get_nowait() is event

    async def test_unsubscribe_during_publish_does_not_raise(self, bus: EventBus) -> None:
        """Unsubscribing inside publish must not raise RuntimeError.

        publish() iterates list(self._subscribers.items()) — a snapshot —
        so mutations to the dict during iteration are safe.
        """
        sub_id, _q = bus.subscribe()
        event = _make_event()

        # Inject a side-effect: unsubscribe self on first put_nowait call.
        # We do this by monkeypatching the queue after subscribing.
        original_put = _q.put_nowait

        def unsubscribe_then_put(item: object) -> None:
            bus.unsubscribe(sub_id)
            original_put(item)

        _q.put_nowait = unsubscribe_then_put  # type: ignore[method-assign]

        # Must not raise RuntimeError("dictionary changed size during iteration")
        await bus.publish(event)
        assert bus.subscriber_count == 0

    async def test_publish_to_empty_bus_is_noop(self, bus: EventBus) -> None:
        """Publishing with no subscribers completes without error."""
        await bus.publish(_make_event())  # no exception
