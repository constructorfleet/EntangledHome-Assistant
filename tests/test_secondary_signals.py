"""Tests for secondary signal provider helper."""

from __future__ import annotations

from types import SimpleNamespace

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


DOMAIN = "entangledhome"


class _DummyStates:
    def __init__(self, states: dict[str, SimpleNamespace]) -> None:
        self._states = states

    def get(self, entity_id: str) -> SimpleNamespace | None:
        return self._states.get(entity_id)


def _make_entry(options: dict[str, object]) -> ConfigEntry:
    entry = ConfigEntry(entry_id="entry-id", options=dict(options))
    entry.data = {}  # type: ignore[attr-defined]
    return entry


def _make_hass(states: dict[str, SimpleNamespace] | None = None) -> HomeAssistant:
    hass = HomeAssistant()
    hass.states = _DummyStates(states or {})  # type: ignore[attr-defined]
    hass.data[DOMAIN] = {"entry-id": {}}
    return hass


def test_presence_signal_included_when_any_person_home() -> None:
    """Presence signals should be returned for configured home person entities."""

    states = {
        "person.alice": SimpleNamespace(state="home"),
        "person.bob": SimpleNamespace(state="not_home"),
    }
    hass = _make_hass(states)
    entry = _make_entry(
        {
            "secondary_signals_presence_enabled": True,
            "secondary_signals_presence_entities": [
                "person.alice",
                "person.bob",
            ],
        }
    )

    from custom_components.entangledhome import secondary_signals

    provider = secondary_signals.build_secondary_signal_provider(hass, entry)

    assert set(provider()) == {"presence", "presence:person.alice"}


def test_voice_signal_respects_ttl_window() -> None:
    """Voice identifiers should expire outside the configured TTL."""

    hass = _make_hass({})
    entry = _make_entry(
        {
            "secondary_signals_voice_enabled": True,
            "secondary_signals_voice_ttl_seconds": 30.0,
        }
    )

    from custom_components.entangledhome import secondary_signals

    secondary_signals.record_voice_identifier(
        hass,
        entry.entry_id,
        "alice",
        timestamp=15.0,
    )
    provider = secondary_signals.build_secondary_signal_provider(
        hass,
        entry,
        time_source=lambda: 35.0,
    )

    assert set(provider()) == {"voice", "voice:alice"}


def test_voice_signal_omits_expired_entries() -> None:
    """Expired voice identifiers should be pruned before returning signals."""

    hass = _make_hass({})
    entry = _make_entry(
        {
            "secondary_signals_voice_enabled": True,
            "secondary_signals_voice_ttl_seconds": 5.0,
        }
    )

    from custom_components.entangledhome import secondary_signals

    secondary_signals.record_voice_identifier(
        hass,
        entry.entry_id,
        "alice",
        timestamp=10.0,
    )
    provider = secondary_signals.build_secondary_signal_provider(
        hass,
        entry,
        time_source=lambda: 20.5,
    )

    assert set(provider()) == set()
