"""Helpers for collecting secondary signals used to authorize sensitive intents."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any, Mapping
import time

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    DEFAULT_SECONDARY_SIGNAL_VOICE_TTL_SECONDS,
    DOMAIN,
    OPT_SECONDARY_SIGNAL_PRESENCE_ENABLED,
    OPT_SECONDARY_SIGNAL_PRESENCE_ENTITIES,
    OPT_SECONDARY_SIGNAL_VOICE_ENABLED,
    OPT_SECONDARY_SIGNAL_VOICE_TTL_SECONDS,
)

__all__ = [
    "build_secondary_signal_provider",
    "record_voice_identifier",
]


SecondarySignalProvider = Callable[[], Iterable[str]]

_PRESENCE_SIGNAL = "presence"
_VOICE_SIGNAL = "voice"
_STORE_VOICE_IDENTIFIERS = "recent_voice_identifiers"


def build_secondary_signal_provider(
    hass: HomeAssistant,
    entry: ConfigEntry,
    *,
    time_source: Callable[[], float] | None = None,
) -> SecondarySignalProvider:
    """Return a callable that yields currently available secondary signals."""

    def _provider() -> set[str]:
        signals: set[str] = set()

        options: Mapping[str, Any] = getattr(entry, "options", {}) or {}

        if options.get(OPT_SECONDARY_SIGNAL_PRESENCE_ENABLED):
            _collect_presence_signals(hass, options, signals)

        if options.get(OPT_SECONDARY_SIGNAL_VOICE_ENABLED):
            _collect_voice_signals(hass, entry.entry_id, options, signals, time_source)

        return signals

    return _provider


def record_voice_identifier(
    hass: HomeAssistant,
    entry_id: str,
    voice_id: str,
    *,
    timestamp: float | None = None,
) -> None:
    """Record a recognized voice identifier for later secondary signal checks."""

    if not voice_id:
        return

    entry_data = _get_entry_data(hass, entry_id)
    store: dict[str, float] = entry_data.setdefault(_STORE_VOICE_IDENTIFIERS, {})
    store[str(voice_id)] = float(timestamp if timestamp is not None else time.monotonic())


def _collect_presence_signals(
    hass: HomeAssistant, options: Mapping[str, Any], signals: set[str]
) -> None:
    raw = options.get(OPT_SECONDARY_SIGNAL_PRESENCE_ENTITIES) or []
    entities = [str(entity).strip() for entity in raw if str(entity).strip()]
    if not entities:
        return

    try:
        states = hass.states
    except AttributeError:  # pragma: no cover - defensive guard
        return

    found = False
    for entity_id in entities:
        state = states.get(entity_id)
        if state is None:
            continue
        value = getattr(state, "state", None)
        if value is None:
            continue
        if str(value).lower() == "home":
            found = True
            signals.add(f"{_PRESENCE_SIGNAL}:{entity_id}")

    if found:
        signals.add(_PRESENCE_SIGNAL)


def _collect_voice_signals(
    hass: HomeAssistant,
    entry_id: str,
    options: Mapping[str, Any],
    signals: set[str],
    time_source: Callable[[], float] | None,
) -> None:
    entry_data = _get_entry_data(hass, entry_id)
    store: dict[str, float] = entry_data.get(_STORE_VOICE_IDENTIFIERS, {})
    if not store:
        return

    ttl_option = options.get(
        OPT_SECONDARY_SIGNAL_VOICE_TTL_SECONDS,
        DEFAULT_SECONDARY_SIGNAL_VOICE_TTL_SECONDS,
    )
    try:
        ttl = float(ttl_option)
    except (TypeError, ValueError):
        ttl = DEFAULT_SECONDARY_SIGNAL_VOICE_TTL_SECONDS

    now = (time_source or time.monotonic)()

    active_ids: list[str] = []
    if ttl <= 0:
        active_ids.extend(store.keys())
    else:
        for voice_id, ts in list(store.items()):
            if now - ts > ttl:
                store.pop(voice_id, None)
                continue
            active_ids.append(voice_id)

    if not active_ids:
        store.clear()
        return

    signals.add(_VOICE_SIGNAL)
    for voice_id in active_ids:
        signals.add(f"{_VOICE_SIGNAL}:{voice_id}")


def _get_entry_data(hass: HomeAssistant, entry_id: str) -> dict[str, Any]:
    domain_data = hass.data.setdefault(DOMAIN, {})
    return domain_data.setdefault(entry_id, {})
