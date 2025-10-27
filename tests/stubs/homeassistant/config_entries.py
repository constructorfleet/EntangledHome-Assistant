"""Stub implementations of Home Assistant config entries."""

from __future__ import annotations

from typing import Any, Callable


class ConfigEntry:
    """Simple stub mimicking the Home Assistant config entry protocol."""

    def __init__(
        self,
        *,
        entry_id: str = "stub",
        data: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> None:
        self.entry_id = entry_id
        self.data = data or {}
        self.options = options or {}
        self._update_listeners: list[Callable[["HomeAssistant", "ConfigEntry"], None]] = []
        self._unload_callbacks: list[Callable[[], None]] = []

    def add_update_listener(
        self, listener: Callable[["HomeAssistant", "ConfigEntry"], None]
    ) -> Callable[["HomeAssistant", "ConfigEntry"], None]:
        self._update_listeners.append(listener)
        return listener

    def async_on_unload(self, callback: Callable[[], None]) -> Callable[[], None]:
        self._unload_callbacks.append(callback)
        return callback


class ConfigFlow:
    """Base stub for configuration flows."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:  # pragma: no cover - convenience stub
        raise NotImplementedError


class OptionsFlow:
    """Base stub for options flows."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:  # pragma: no cover - convenience stub
        raise NotImplementedError


# Circular import guard for type checking
type HomeAssistant = Any
