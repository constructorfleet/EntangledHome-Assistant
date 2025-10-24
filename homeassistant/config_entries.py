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


class ConfigFlow:
    """Minimal stub for Home Assistant config flow base class."""

    DOMAIN: str | None = None

    def __init_subclass__(cls, *, domain: str | None = None, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls.DOMAIN = domain

    def async_show_form(self, *, step_id: str, data_schema: Any) -> dict[str, Any]:
        return {"type": "form", "step_id": step_id, "data_schema": data_schema}

    async def async_create_entry(self, *, title: str, data: dict[str, Any], options: dict[str, Any]):
        return {"type": "create_entry", "title": title, "data": data, "options": options}


class OptionsFlow:
    """Minimal stub for Home Assistant options flow base class."""

    def async_show_form(self, *, step_id: str, data_schema: Any) -> dict[str, Any]:
        return {"type": "form", "step_id": step_id, "data_schema": data_schema}

    async def async_create_entry(self, *, title: str, data: dict[str, Any]):
        return {"type": "create_entry", "title": title, "data": data}
