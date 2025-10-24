"""Core stubs for Home Assistant."""

from __future__ import annotations

from typing import Any


class HomeAssistant:
    """Minimal representation of Home Assistant core."""

    def __init__(self) -> None:
        self.data: dict[str, Any] = {}
        self.config_entries: Any = None


def callback(func):  # type: ignore[override]
    """Return the provided function unchanged, mimicking HA's callback decorator."""

    return func
