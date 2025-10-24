"""Minimal Home Assistant core stub for tests."""

from __future__ import annotations

from typing import Any


class _ConfigEntriesManager:
    """Simplified config entries API surface used in tests."""

    def async_update_entry(self, entry: Any, *, options: dict[str, Any] | None = None) -> None:
        if options is not None:
            entry.options.update(options)


class HomeAssistant:
    """Extremely small subset of the Home Assistant core object."""

    def __init__(self) -> None:
        self.data: dict[str, Any] = {}
        self.config_entries = _ConfigEntriesManager()
