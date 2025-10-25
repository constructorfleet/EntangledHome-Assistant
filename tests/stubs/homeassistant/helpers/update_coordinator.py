"""Stub DataUpdateCoordinator for unit tests."""

from __future__ import annotations

from typing import Any, Generic, Optional, TypeVar

_T = TypeVar("_T")


class DataUpdateCoordinator(Generic[_T]):
    """Minimal async coordinator stub."""

    def __init__(
        self, hass: Any, logger: Any, *, name: str = "", update_interval: Optional[Any] = None
    ) -> None:
        self.hass = hass
        self.logger = logger
        self.name = name
        self.update_interval = update_interval

    async def async_config_entry_first_refresh(self) -> None:
        return None

    async def async_request_refresh(self) -> None:
        return None
