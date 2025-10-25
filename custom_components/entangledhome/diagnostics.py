"""Diagnostics support exposing recent command telemetry."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DATA_TELEMETRY, DOMAIN
from .telemetry import TelemetryRecorder


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics data for a config entry."""

    domain_data = hass.data.get(DOMAIN, {})
    entry_data = domain_data.get(entry.entry_id, {})
    recorder = entry_data.get(DATA_TELEMETRY)

    if isinstance(recorder, TelemetryRecorder):
        events = recorder.as_dicts()
    else:
        events = []

    return {
        "config_entry_id": entry.entry_id,
        "total_commands": len(events),
        "recent_commands": events,
    }
