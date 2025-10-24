"""Minimal config entries stubs for tests."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class ConfigEntry:
    """Simplified representation of a Home Assistant config entry."""

    def __init__(self, entry_id: str = "test", options: dict[str, Any] | None = None) -> None:
        self.entry_id = entry_id
        self.options: dict[str, Any] = options or {}

    def async_on_unload(self, callback: Callable[[], Any]) -> Callable[[], Any]:
        """Return the callback unchanged (placeholder for HA lifecycle)."""

        return callback

    def add_update_listener(self, listener: Callable[[Any], Any]) -> Callable[[Any], Any]:
        """Return the listener unchanged."""

        return listener
