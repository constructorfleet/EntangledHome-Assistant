"""Data update coordinator for EntangledHome."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


class EntangledHomeCoordinator(DataUpdateCoordinator[None]):
    """Trivial coordinator placeholder for configuration updates."""

    def __init__(self, hass: HomeAssistant, entry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="EntangledHome Coordinator",
            update_interval=timedelta(minutes=5),
        )
        self.config_entry = entry

    async def _async_update_data(self) -> None:
        """Perform a no-op refresh for now."""
        return None
