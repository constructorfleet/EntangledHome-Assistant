from datetime import datetime, timedelta, timezone

import pytest

from custom_components.entangledhome.const import DATA_TELEMETRY, DOMAIN
from custom_components.entangledhome.diagnostics import async_get_config_entry_diagnostics
from custom_components.entangledhome.models import InterpretResponse
from custom_components.entangledhome.telemetry import TelemetryRecorder
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

pytestmark = pytest.mark.asyncio


class ClockStub:
    """Deterministic datetime provider for telemetry timestamps."""

    def __init__(self, base: datetime, step: timedelta) -> None:
        self._current = base
        self._step = step

    def __call__(self) -> datetime:
        current = self._current
        self._current = current + self._step
        return current


async def test_diagnostics_returns_recent_commands() -> None:
    """Diagnostics should expose stored telemetry events."""

    recorder = TelemetryRecorder(
        max_events=5,
        clock=ClockStub(datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc), timedelta(milliseconds=10)),
    )
    response = InterpretResponse(
        intent="turn_on",
        area="kitchen",
        targets=["light.kitchen"],
        params={"color": "red"},
        confidence=0.88,
        qdrant_terms=["kitchen", "lights"],
    )
    recorder.record_event(
        utterance="Turn on the kitchen lights",
        qdrant_terms=["kitchen", "lights"],
        response=response,
        duration_ms=145.0,
        outcome="executed",
    )

    hass = HomeAssistant()
    hass.data = {DOMAIN: {"entry-1": {DATA_TELEMETRY: recorder}}}
    entry = ConfigEntry(entry_id="entry-1", options={})

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert result["config_entry_id"] == "entry-1"
    assert result["total_commands"] == 1
    recent = result["recent_commands"]
    assert len(recent) == 1
    payload = recent[0]
    assert payload["utterance"] == "Turn on the kitchen lights"
    assert payload["qdrant_terms"] == ["kitchen", "lights"]
    assert payload["duration_ms"] == pytest.approx(145.0)
    assert payload["response"]["intent"] == "turn_on"
    assert payload["response"]["confidence"] == pytest.approx(0.88)


async def test_diagnostics_returns_empty_when_missing_recorder() -> None:
    """Diagnostics should fallback to empty results when recorder is absent."""

    hass = HomeAssistant()
    hass.data = {DOMAIN: {"entry-2": {}}}
    entry = ConfigEntry(entry_id="entry-2", options={})

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert result["config_entry_id"] == "entry-2"
    assert result["recent_commands"] == []
    assert result["total_commands"] == 0
