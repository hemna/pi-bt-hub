"""Tests for the SSE log handler."""

from __future__ import annotations

import asyncio
import logging

import pytest

from bt_hub.services.log_handler import SSELogHandler


class TestSSELogHandlerBuffer:
    """Test ring buffer behavior."""

    def test_emit_adds_to_buffer(self) -> None:
        handler = SSELogHandler(maxlen=10)
        record = logging.LogRecord("test", logging.INFO, "", 0, "hello", (), None)
        handler.emit(record)
        assert handler.buffer_size == 1

    def test_buffer_respects_maxlen(self) -> None:
        handler = SSELogHandler(maxlen=3)
        for i in range(5):
            record = logging.LogRecord("test", logging.INFO, "", 0, f"msg {i}", (), None)
            handler.emit(record)
        assert handler.buffer_size == 3

    def test_get_recent_returns_all(self) -> None:
        handler = SSELogHandler(maxlen=10)
        for i in range(3):
            record = logging.LogRecord("test", logging.INFO, "", 0, f"msg {i}", (), None)
            handler.emit(record)
        entries = handler.get_recent()
        assert len(entries) == 3
        assert entries[0]["message"] == "msg 0"
        assert entries[2]["message"] == "msg 2"

    def test_get_recent_with_count(self) -> None:
        handler = SSELogHandler(maxlen=10)
        for i in range(5):
            record = logging.LogRecord("test", logging.INFO, "", 0, f"msg {i}", (), None)
            handler.emit(record)
        entries = handler.get_recent(2)
        assert len(entries) == 2
        assert entries[0]["message"] == "msg 3"
        assert entries[1]["message"] == "msg 4"


class TestSSELogHandlerFormat:
    """Test log entry formatting."""

    def test_entry_has_required_fields(self) -> None:
        handler = SSELogHandler()
        record = logging.LogRecord("mylogger", logging.WARNING, "", 0, "test msg", (), None)
        handler.emit(record)
        entry = handler.get_recent()[0]
        assert "timestamp" in entry
        assert entry["level"] == "WARNING"
        assert entry["logger"] == "mylogger"
        assert entry["message"] == "test msg"

    def test_entry_level_names(self) -> None:
        handler = SSELogHandler()
        for level, name in [(logging.DEBUG, "DEBUG"), (logging.ERROR, "ERROR")]:
            record = logging.LogRecord("test", level, "", 0, "x", (), None)
            handler.emit(record)
        entries = handler.get_recent()
        assert entries[0]["level"] == "DEBUG"
        assert entries[1]["level"] == "ERROR"


class TestSSELogHandlerSubscribe:
    """Test pub/sub subscriber behavior."""

    def test_subscribe_creates_queue(self) -> None:
        handler = SSELogHandler()
        queue = handler.subscribe()
        assert isinstance(queue, asyncio.Queue)
        assert handler.subscriber_count == 1

    def test_unsubscribe_removes_queue(self) -> None:
        handler = SSELogHandler()
        queue = handler.subscribe()
        handler.unsubscribe(queue)
        assert handler.subscriber_count == 0

    def test_unsubscribe_nonexistent_is_safe(self) -> None:
        handler = SSELogHandler()
        queue: asyncio.Queue = asyncio.Queue()
        handler.unsubscribe(queue)  # should not raise
        assert handler.subscriber_count == 0

    def test_emit_pushes_to_subscribers(self) -> None:
        handler = SSELogHandler()
        queue = handler.subscribe()
        record = logging.LogRecord("test", logging.INFO, "", 0, "hello", (), None)
        handler.emit(record)
        assert not queue.empty()
        entry = queue.get_nowait()
        assert entry["message"] == "hello"

    def test_emit_pushes_to_multiple_subscribers(self) -> None:
        handler = SSELogHandler()
        q1 = handler.subscribe()
        q2 = handler.subscribe()
        record = logging.LogRecord("test", logging.INFO, "", 0, "broadcast", (), None)
        handler.emit(record)
        assert q1.get_nowait()["message"] == "broadcast"
        assert q2.get_nowait()["message"] == "broadcast"

    def test_full_queue_drops_oldest(self) -> None:
        handler = SSELogHandler()
        queue = handler.subscribe()
        # Fill the queue (maxsize=200)
        for i in range(200):
            record = logging.LogRecord("test", logging.INFO, "", 0, f"msg {i}", (), None)
            handler.emit(record)
        # One more should not raise, it drops oldest
        record = logging.LogRecord("test", logging.INFO, "", 0, "overflow", (), None)
        handler.emit(record)
        # Queue should still be full (200)
        assert queue.qsize() == 200


class TestSSELogHandlerLevelFilter:
    """Test that the handler respects its level setting."""

    def test_handler_filters_below_level(self) -> None:
        handler = SSELogHandler(level=logging.WARNING)
        # Use a logger so the level check in callHandlers() is exercised
        test_logger = logging.getLogger("test_level_filter")
        test_logger.addHandler(handler)
        test_logger.setLevel(logging.DEBUG)  # Logger passes everything
        try:
            test_logger.warning("warn")
            test_logger.debug("debug")
            # Only the WARNING record should be in the buffer
            entries = handler.get_recent()
            assert len(entries) == 1
            assert entries[0]["level"] == "WARNING"
        finally:
            test_logger.removeHandler(handler)


class TestSetupSSELogging:
    """Test the setup_sse_logging function."""

    def test_setup_returns_handler(self) -> None:
        from bt_hub.services.log_handler import setup_sse_logging

        handler = setup_sse_logging()
        assert isinstance(handler, SSELogHandler)

    def test_setup_sets_global(self) -> None:
        from bt_hub.services.log_handler import get_sse_log_handler, setup_sse_logging

        setup_sse_logging()
        assert get_sse_log_handler() is not None

    def test_handler_captures_bt_hub_logs(self) -> None:
        from bt_hub.services.log_handler import setup_sse_logging

        handler = setup_sse_logging()
        test_logger = logging.getLogger("bt_hub.test_capture")
        test_logger.setLevel(logging.DEBUG)
        test_logger.info("capture test")
        entries = handler.get_recent()
        messages = [e["message"] for e in entries]
        assert "capture test" in messages
