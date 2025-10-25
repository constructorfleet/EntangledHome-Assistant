"""Tests for default options handling in integration setup."""

from __future__ import annotations

from typing import Any, Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


def _override_update_entry(
    hass: HomeAssistant,
    handler: Callable[[ConfigEntry, dict[str, Any]], None],
) -> None:
    original = hass.config_entries.async_update_entry

    def _wrapper(entry: ConfigEntry, *, options: dict[str, Any] | None = None) -> None:
        if options is not None:
            handler(entry, options)
        else:
            original(entry, options=options)

    hass.config_entries.async_update_entry = _wrapper  # type: ignore[method-assign]


def test_ensure_default_options_populates_guardrail_defaults() -> None:
    """Guardrail toggles and thresholds should be seeded with defaults."""

    from custom_components.entangledhome import _ensure_default_options
    from custom_components.entangledhome.const import (
        DEFAULT_CONFIDENCE_THRESHOLD,
        DEFAULT_DEDUPLICATION_WINDOW,
        DEFAULT_NIGHT_MODE_END_HOUR,
        DEFAULT_NIGHT_MODE_ENABLED,
        DEFAULT_NIGHT_MODE_START_HOUR,
        OPT_ADAPTER_SHARED_SECRET,
        OPT_CONFIDENCE_THRESHOLD,
        OPT_DEDUPLICATION_WINDOW,
        OPT_NIGHT_MODE_ENABLED,
        OPT_NIGHT_MODE_END_HOUR,
        OPT_NIGHT_MODE_START_HOUR,
    )

    hass = HomeAssistant()

    def _store_options(entry: ConfigEntry, options: dict[str, Any]) -> None:
        entry.options = dict(options)

    _override_update_entry(hass, _store_options)

    entry = ConfigEntry(entry_id="guardrail-entry", options={})

    _ensure_default_options(hass, entry)

    assert entry.options[OPT_CONFIDENCE_THRESHOLD] == DEFAULT_CONFIDENCE_THRESHOLD
    assert entry.options[OPT_NIGHT_MODE_ENABLED] is DEFAULT_NIGHT_MODE_ENABLED
    assert entry.options[OPT_NIGHT_MODE_START_HOUR] == DEFAULT_NIGHT_MODE_START_HOUR
    assert entry.options[OPT_NIGHT_MODE_END_HOUR] == DEFAULT_NIGHT_MODE_END_HOUR
    assert entry.options[OPT_DEDUPLICATION_WINDOW] == DEFAULT_DEDUPLICATION_WINDOW
    assert entry.options[OPT_ADAPTER_SHARED_SECRET] == ""


def test_ensure_default_options_populates_refresh_and_plex_defaults() -> None:
    """Defaults should include refresh cadence and Plex sync flags."""

    from custom_components.entangledhome import _ensure_default_options
    from custom_components.entangledhome.const import (
        DEFAULT_CATALOG_SYNC,
        DEFAULT_CONFIDENCE_GATE,
        DEFAULT_PLEX_SYNC,
        DEFAULT_REFRESH_INTERVAL_MINUTES,
        OPT_ENABLE_CATALOG_SYNC,
        OPT_ENABLE_CONFIDENCE_GATE,
        OPT_ENABLE_PLEX_SYNC,
        OPT_REFRESH_INTERVAL_MINUTES,
    )

    hass = HomeAssistant()
    updated_options: dict[str, object] = {}

    def _capture_options(entry: ConfigEntry, options: dict[str, Any]) -> None:
        entry.options = dict(options)
        updated_options.update(options)

    _override_update_entry(hass, _capture_options)

    entry = ConfigEntry(entry_id="test-entry", options={})

    _ensure_default_options(hass, entry)

    assert entry.options[OPT_ENABLE_CATALOG_SYNC] is DEFAULT_CATALOG_SYNC
    assert entry.options[OPT_ENABLE_CONFIDENCE_GATE] is DEFAULT_CONFIDENCE_GATE
    assert entry.options[OPT_REFRESH_INTERVAL_MINUTES] == DEFAULT_REFRESH_INTERVAL_MINUTES
    assert entry.options[OPT_ENABLE_PLEX_SYNC] is DEFAULT_PLEX_SYNC
    assert updated_options == entry.options


def test_ensure_default_options_preserves_existing_values() -> None:
    """Existing options should not be overwritten when already set."""

    from custom_components.entangledhome import _ensure_default_options
    from custom_components.entangledhome.const import (
        OPT_CONFIDENCE_THRESHOLD,
        OPT_ENABLE_CATALOG_SYNC,
        OPT_ENABLE_CONFIDENCE_GATE,
        OPT_ENABLE_PLEX_SYNC,
        OPT_NIGHT_MODE_ENABLED,
        OPT_NIGHT_MODE_END_HOUR,
        OPT_NIGHT_MODE_START_HOUR,
        OPT_DEDUPLICATION_WINDOW,
        OPT_REFRESH_INTERVAL_MINUTES,
        OPT_ADAPTER_SHARED_SECRET,
        OPT_ALLOWED_HOURS,
        OPT_DANGEROUS_INTENTS,
        OPT_DISABLED_INTENTS,
        OPT_INTENT_THRESHOLDS,
        OPT_RECENT_COMMAND_WINDOW_OVERRIDES,
        OPT_INTENTS_CONFIG,
        DEFAULT_INTENTS_CONFIG,
    )

    hass = HomeAssistant()

    def _fail_update(entry: ConfigEntry, options: dict[str, Any]) -> None:
        raise AssertionError("Should not update options when all defaults present")

    _override_update_entry(hass, _fail_update)

    entry = ConfigEntry(
        entry_id="test-entry",
        options={
            OPT_ENABLE_CATALOG_SYNC: True,
            OPT_ENABLE_CONFIDENCE_GATE: False,
            OPT_REFRESH_INTERVAL_MINUTES: 15,
            OPT_ENABLE_PLEX_SYNC: False,
            OPT_CONFIDENCE_THRESHOLD: 0.42,
            OPT_NIGHT_MODE_ENABLED: True,
            OPT_NIGHT_MODE_START_HOUR: 21,
            OPT_NIGHT_MODE_END_HOUR: 7,
            OPT_DEDUPLICATION_WINDOW: 1.5,
            OPT_ADAPTER_SHARED_SECRET: "existing-secret",
            OPT_INTENT_THRESHOLDS: {},
            OPT_DISABLED_INTENTS: [],
            OPT_DANGEROUS_INTENTS: [],
            OPT_ALLOWED_HOURS: {},
            OPT_RECENT_COMMAND_WINDOW_OVERRIDES: {},
            OPT_INTENTS_CONFIG: DEFAULT_INTENTS_CONFIG,
        },
    )

    _ensure_default_options(hass, entry)

    assert entry.options[OPT_REFRESH_INTERVAL_MINUTES] == 15
    assert entry.options[OPT_ENABLE_PLEX_SYNC] is False
    assert entry.options[OPT_CONFIDENCE_THRESHOLD] == 0.42
    assert entry.options[OPT_NIGHT_MODE_ENABLED] is True
