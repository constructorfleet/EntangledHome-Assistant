"""Tests for default options handling in integration setup."""

from __future__ import annotations

from types import SimpleNamespace


def test_ensure_default_options_populates_guardrail_defaults() -> None:
    """Guardrail toggles and thresholds should be seeded with defaults."""

    from custom_components.entangledhome import _ensure_default_options
    from custom_components.entangledhome.const import (
        DEFAULT_CONFIDENCE_THRESHOLD,
        DEFAULT_DEDUPLICATION_WINDOW,
        DEFAULT_NIGHT_MODE_END_HOUR,
        DEFAULT_NIGHT_MODE_ENABLED,
        DEFAULT_NIGHT_MODE_START_HOUR,
        OPT_CONFIDENCE_THRESHOLD,
        OPT_DEDUPLICATION_WINDOW,
        OPT_NIGHT_MODE_ENABLED,
        OPT_NIGHT_MODE_END_HOUR,
        OPT_NIGHT_MODE_START_HOUR,
    )

    hass = SimpleNamespace()

    class FakeConfigEntries:
        def async_update_entry(self, entry, *, options=None, data=None):
            if options is not None:
                entry.options = options

    hass.config_entries = FakeConfigEntries()

    entry = SimpleNamespace(entry_id="guardrail-entry", options={})

    _ensure_default_options(hass, entry)

    assert entry.options[OPT_CONFIDENCE_THRESHOLD] == DEFAULT_CONFIDENCE_THRESHOLD
    assert entry.options[OPT_NIGHT_MODE_ENABLED] is DEFAULT_NIGHT_MODE_ENABLED
    assert entry.options[OPT_NIGHT_MODE_START_HOUR] == DEFAULT_NIGHT_MODE_START_HOUR
    assert entry.options[OPT_NIGHT_MODE_END_HOUR] == DEFAULT_NIGHT_MODE_END_HOUR
    assert entry.options[OPT_DEDUPLICATION_WINDOW] == DEFAULT_DEDUPLICATION_WINDOW


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

    hass = SimpleNamespace()
    updated_options: dict[str, object] = {}

    class FakeConfigEntries:
        def async_update_entry(self, entry, *, options=None, data=None):
            if options is not None:
                entry.options = options
                updated_options.update(options)

    hass.config_entries = FakeConfigEntries()

    entry = SimpleNamespace(entry_id="test-entry", options={})

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
    )

    hass = SimpleNamespace()

    class FakeConfigEntries:
        def async_update_entry(self, entry, *, options=None, data=None):
            raise AssertionError("Should not update options when all defaults present")

    hass.config_entries = FakeConfigEntries()

    entry = SimpleNamespace(
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
        },
    )

    _ensure_default_options(hass, entry)

    assert entry.options[OPT_REFRESH_INTERVAL_MINUTES] == 15
    assert entry.options[OPT_ENABLE_PLEX_SYNC] is False
    assert entry.options[OPT_CONFIDENCE_THRESHOLD] == 0.42
    assert entry.options[OPT_NIGHT_MODE_ENABLED] is True
