"""Tests for unified hub configuration."""

from __future__ import annotations

import os

import pytest

from bt_hub.config import Settings


class TestSettings:
    """Test core settings."""

    def test_defaults(self) -> None:
        settings = Settings()
        assert settings.host == "0.0.0.0"
        assert settings.port == 8080
        assert settings.log_level == "INFO"
        assert settings.adapter is None

    def test_env_prefix(self, monkeypatch: object) -> None:
        os.environ["BT_HUB_PORT"] = "9090"
        try:
            settings = Settings()
            assert settings.port == 9090
        finally:
            del os.environ["BT_HUB_PORT"]

    def test_settings_is_immutable(self) -> None:
        """Settings is a frozen dataclass — mutation must raise FrozenInstanceError."""
        settings = Settings()
        with pytest.raises(AttributeError):
            settings.host = "1.2.3.4"  # type: ignore[misc]

    def test_settings_is_hashable(self) -> None:
        """Frozen dataclasses are hashable; useful as dict keys / set members."""
        settings = Settings()
        assert hash(settings) is not None


class TestBridgeSettings:
    """Test bridge-specific settings."""

    def test_bridge_disabled_by_default(self) -> None:
        settings = Settings()
        assert settings.bridge_enabled is False

    def test_bridge_url_default(self) -> None:
        settings = Settings()
        assert settings.bridge_url == "http://localhost:8081"

    def test_bridge_enabled_from_env(self) -> None:
        os.environ["BT_HUB_BRIDGE_ENABLED"] = "true"
        try:
            settings = Settings()
            assert settings.bridge_enabled is True
        finally:
            del os.environ["BT_HUB_BRIDGE_ENABLED"]

    def test_bridge_url_from_env(self) -> None:
        os.environ["BT_HUB_BRIDGE_URL"] = "http://pi:9999"
        try:
            settings = Settings()
            assert settings.bridge_url == "http://pi:9999"
        finally:
            del os.environ["BT_HUB_BRIDGE_URL"]
