"""Home Assistant integration setup for EntangledHome."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    DEFAULT_CATALOG_SYNC,
    DEFAULT_CONFIDENCE_GATE,
    DEFAULT_PLEX_SYNC,
    DEFAULT_REFRESH_INTERVAL_MINUTES,
    DOMAIN,
    OPT_ENABLE_CATALOG_SYNC,
    OPT_ENABLE_CONFIDENCE_GATE,
    OPT_ENABLE_PLEX_SYNC,
    OPT_REFRESH_INTERVAL_MINUTES,
)
from .coordinator import EntangledHomeCoordinator

PLATFORMS: list[str] = []


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up EntangledHome from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    coordinator = EntangledHomeCoordinator(hass, entry)
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
    }

    await coordinator.async_config_entry_first_refresh()

    _ensure_default_options(hass, entry)
    entry.async_on_unload(entry.add_update_listener(async_update_options))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return True


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update to refresh the coordinator."""
    coordinator = _get_coordinator(hass, entry.entry_id)
    if coordinator is not None:
        await coordinator.async_request_refresh()


def _ensure_default_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Ensure options have defaults populated."""
    options: dict[str, Any] = dict(entry.options)
    updated = False

    for option_key, default_value in (
        (OPT_ENABLE_CATALOG_SYNC, DEFAULT_CATALOG_SYNC),
        (OPT_ENABLE_CONFIDENCE_GATE, DEFAULT_CONFIDENCE_GATE),
        (OPT_REFRESH_INTERVAL_MINUTES, DEFAULT_REFRESH_INTERVAL_MINUTES),
        (OPT_ENABLE_PLEX_SYNC, DEFAULT_PLEX_SYNC),
    ):
        if option_key not in options:
            options[option_key] = default_value
            updated = True

    if updated:
        hass.config_entries.async_update_entry(entry, options=options)


def _get_coordinator(hass: HomeAssistant, entry_id: str) -> EntangledHomeCoordinator | None:
    domain_data = hass.data.get(DOMAIN, {})
    stored = domain_data.get(entry_id)
    if not stored:
        return None
    return stored.get("coordinator")
